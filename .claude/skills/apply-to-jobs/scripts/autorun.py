#!/usr/bin/env python3
"""
autorun.py — scheduled, unattended apply runs. Prints one JSON object per command.

  run        lock (job_engine/.autorun.lock, 6 h) -> headless `claude -p "...scheduled run."`
             -> output appended to job_engine/reports/autorun.log
  install    register autorun.schedule from job_engine/engine_config.yaml
             (Windows: schtasks task JobBotAutorun, interactive-only; else: tagged crontab line)
  uninstall  remove it
  status     task/cron entry, lock state, newest report
"""
from __future__ import annotations
import datetime, json, os, shutil, subprocess, sys, time
from pathlib import Path

HERE = Path(__file__).resolve()
REPO = HERE.parents[4]
JE = REPO / "job_engine"
LOCK = JE / ".autorun.lock"
REPORTS = JE / "reports"
TASK = "JobBotAutorun"
WIN = os.name == "nt"
PROMPT = "Use the apply-to-jobs skill: scheduled run."

def out(d):
    print(json.dumps(d)); return d

def schedule() -> dict:
    import yaml
    cfg = yaml.safe_load((JE / "engine_config.yaml").read_text(encoding="utf-8")) or {}
    s = (cfg.get("autorun") or {}).get("schedule") or {}
    return {"time": str(s.get("time", "09:00")), "days": str(s.get("days", "MON,TUE,WED,THU,FRI"))}

def find_claude() -> str:
    c = shutil.which("claude")
    if c: return c
    return str(Path.home() / ".local" / "bin" / ("claude.exe" if WIN else "claude"))

def sh(args):
    r = subprocess.run(args, capture_output=True, text=True, encoding="utf-8", errors="replace")
    return r.returncode, (r.stdout + r.stderr).strip()

def cmd_run():
    if LOCK.exists() and time.time() - LOCK.stat().st_mtime < 6 * 3600:
        return out({"status": "skip", "reason": "locked"})
    REPORTS.mkdir(parents=True, exist_ok=True)
    LOCK.write_text(json.dumps({"pid": os.getpid(), "ts": datetime.datetime.now().isoformat(timespec="seconds")}))
    try:
        # Explicit allowlist: doesn't depend on the user's global permission mode.
        r = subprocess.run([find_claude(), "-p", PROMPT, "--model", "opus",
                            "--allowedTools", "Bash Read Write Edit Glob Grep Agent Skill"],
                           cwd=REPO, capture_output=True, text=True, encoding="utf-8", errors="replace")
        log = REPORTS / "autorun.log"
        with log.open("a", encoding="utf-8") as f:
            f.write(f"\n===== {datetime.datetime.now().isoformat(timespec='seconds')} exit={r.returncode} =====\n")
            f.write(r.stdout + ("\n--- stderr ---\n" + r.stderr if r.stderr else ""))
        return out({"status": "ok" if r.returncode == 0 else "error", "returncode": r.returncode, "log": str(log)})
    finally:
        LOCK.unlink(missing_ok=True)

CRON_DAYS = {"SUN": "0", "MON": "1", "TUE": "2", "WED": "3", "THU": "4", "FRI": "5", "SAT": "6"}

def _crontab() -> list:
    code, txt = sh(["crontab", "-l"])
    return [l for l in txt.splitlines() if l.strip()] if code == 0 else []

def _set_crontab(lines):
    subprocess.run(["crontab", "-"], input="\n".join(lines) + "\n", text=True, check=True)

def cmd_install():
    s = schedule()
    if WIN:
        tr = f'"{sys.executable}" "{HERE}" run'
        code, txt = sh(["schtasks", "/Create", "/F", "/TN", TASK, "/SC", "WEEKLY", "/D", s["days"],
                        "/ST", s["time"], "/IT", "/TR", tr])
    else:
        hh, mm = s["time"].split(":")
        days = ",".join(CRON_DAYS[d.strip().upper()] for d in s["days"].split(","))
        line = f'{int(mm)} {int(hh)} * * {days} cd "{REPO}" && "{sys.executable}" "{HERE}" run # {TASK}'
        try:
            _set_crontab([l for l in _crontab() if f"# {TASK}" not in l] + [line])
            code, txt = 0, line
        except Exception as e:
            code, txt = 1, str(e)
    return out({"status": "ok" if code == 0 else "error", "schedule": s, "detail": txt})

def cmd_uninstall():
    if WIN:
        code, txt = sh(["schtasks", "/Delete", "/TN", TASK, "/F"])
    else:
        try:
            _set_crontab([l for l in _crontab() if f"# {TASK}" not in l]); code, txt = 0, "removed"
        except Exception as e:
            code, txt = 1, str(e)
    return out({"status": "ok" if code == 0 else "error", "detail": txt})

def cmd_status():
    if WIN:
        code, txt = sh(["schtasks", "/Query", "/TN", TASK, "/FO", "LIST"])
        task = txt if code == 0 else None
    else:
        task = next((l for l in _crontab() if f"# {TASK}" in l), None)
    reports = sorted(REPORTS.glob("*.md")) if REPORTS.is_dir() else []
    return out({"installed": task is not None, "task": task, "locked": LOCK.exists(),
                "latest_report": str(reports[-1]) if reports else None})

if __name__ == "__main__":
    cmds = {"run": cmd_run, "install": cmd_install, "uninstall": cmd_uninstall, "status": cmd_status}
    if len(sys.argv) != 2 or sys.argv[1] not in cmds:
        sys.exit(f"usage: autorun.py {{{'|'.join(cmds)}}}")
    cmds[sys.argv[1]]()
