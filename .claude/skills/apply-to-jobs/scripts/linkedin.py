#!/usr/bin/env python3
"""
linkedin.py — Playwright driver for the job-application skills (v1: LinkedIn Easy Apply).

Design contract (why it works the way it does):
  * One persistent Chrome profile (job_engine/browser_profile) holds the logged-in
    LinkedIn session, so login survives across runs. CAPTCHA/2FA are only needed
    when the session is fresh/expired — and only a human can clear them.
  * Each `apply` invocation walks ONE job's Easy Apply modal from the start. Page
    state can't persist across separate process launches, but cookies do — so
    re-invoking re-opens the modal cleanly. When the walker hits a REQUIRED field
    it has no answer for, it stops and emits {"status":"needs_answers", ...}. The
    orchestrator (Claude) answers those (grounded in the candidate's evidence,
    never fabricated), appends them to answers.json, and re-invokes. The loop
    converges in 1-2 extra passes.
  * Selectors target LinkedIn's current Easy Apply DOM but LinkedIn changes often;
    treat the selector constants below as the first thing to tune on a live run.

Commands:
  check                      -> {"logged_in": bool}
  login                      -> opens headed browser; waits until you're logged in
  search  ...                -> scrape job listings as JSON
  apply   ...                -> walk one Easy Apply modal (the core loop)

All commands print a single JSON object to stdout. Errors -> {"status":"error","error":...}.
"""
from __future__ import annotations
import argparse, json, os, random, re, sys, time
from pathlib import Path

try:
    from playwright.sync_api import sync_playwright, TimeoutError as PWTimeout
except Exception as e:  # playwright not installed
    print(json.dumps({"status": "error", "error": f"playwright import failed: {e}",
                      "hint": "pip install playwright && playwright install chromium"}))
    sys.exit(2)

# ----------------------------------------------------------------------------- paths/config
HERE = Path(__file__).resolve()
# repo root = .../JobSearchAssistant ; job_engine sits beside .claude
def find_job_engine() -> Path:
    p = HERE
    for _ in range(8):
        cand = p / "job_engine"
        if cand.is_dir():
            return cand
        p = p.parent
    # fallback: assume <repo>/job_engine three levels up from scripts/
    return HERE.parents[4] / "job_engine"

JOB_ENGINE = find_job_engine()

def load_config() -> dict:
    cfg_path = JOB_ENGINE / "engine_config.yaml"
    try:
        import yaml
        return yaml.safe_load(cfg_path.read_text(encoding="utf-8")) or {}
    except Exception:
        return {}

CFG = load_config()
BROWSER_CFG = CFG.get("browser", {}) or {}
PACING = CFG.get("pacing", {}) or {}
PROFILE_DIR = JOB_ENGINE / BROWSER_CFG.get("profile_dir", "browser_profile")

# ----------------------------------------------------------------------------- selectors (tune on live run)
SEL = {
    "logged_in": "div.scaffold-layout, .global-nav__me, img.global-nav__me-photo",
    "login_user": "input#username",
    "login_pass": "input#password",
    "easy_apply_btn": "button.jobs-apply-button, button[aria-label*='Easy Apply']",
    "modal": "div.jobs-easy-apply-modal",
    "modal_next": "button[aria-label='Continue to next step']",
    "modal_review": "button[aria-label='Review your application']",
    "modal_submit": "button[aria-label='Submit application']",
    "resume_upload": "input[type='file'][name='file'], input[type='file']",
    "form_group": "div.jobs-easy-apply-form-section__grouping, div.fb-dash-form-element",
    "job_card": "div.job-card-container, li.jobs-search-results__list-item",
    "job_title_panel": "h1.job-details-jobs-unified-top-card__job-title, h1",
    "job_desc_panel": "div#job-details, article.jobs-description__container",
}

def human_delay():
    lo = float(PACING.get("min_action_delay_sec", 1.5))
    hi = float(PACING.get("max_action_delay_sec", 5.0))
    time.sleep(random.uniform(lo, hi))

def norm(s: str) -> str:
    return re.sub(r"\s+", " ", (s or "").strip().lower())

# ----------------------------------------------------------------------------- browser
def launch(p):
    PROFILE_DIR.mkdir(parents=True, exist_ok=True)
    kwargs = dict(
        user_data_dir=str(PROFILE_DIR),
        headless=bool(BROWSER_CFG.get("headless", False)),
        args=["--disable-blink-features=AutomationControlled"],
    )
    channel = BROWSER_CFG.get("channel")
    if channel:
        try:
            return p.chromium.launch_persistent_context(channel=channel, **kwargs)
        except Exception:
            pass  # fall back to bundled chromium
    return p.chromium.launch_persistent_context(**kwargs)

def is_logged_in(page) -> bool:
    try:
        page.goto("https://www.linkedin.com/feed/", wait_until="domcontentloaded", timeout=30000)
    except PWTimeout:
        pass
    if "login" in page.url or "checkpoint" in page.url:
        return False
    try:
        page.wait_for_selector(SEL["logged_in"], timeout=8000)
        return True
    except PWTimeout:
        return False

# ----------------------------------------------------------------------------- commands
def cmd_check(args):
    with sync_playwright() as p:
        ctx = launch(p)
        page = ctx.new_page()
        out = {"logged_in": is_logged_in(page)}
        ctx.close()
    print(json.dumps(out))

def cmd_login(args):
    """Headed login. Tries stored creds for the username/password step; the human
    completes CAPTCHA/2FA. Polls until the feed is reachable, then persists session."""
    with sync_playwright() as p:
        ctx = launch(p)
        page = ctx.new_page()
        if is_logged_in(page):
            ctx.close(); print(json.dumps({"status": "ok", "already": True})); return
        page.goto("https://www.linkedin.com/login", wait_until="domcontentloaded")
        # best-effort autofill from .env fallback
        email = os.environ.get("LINKEDIN_EMAIL"); pw = os.environ.get("LINKEDIN_PASSWORD")
        envf = JOB_ENGINE / ".env"
        if (not email or not pw) and envf.exists():
            for line in envf.read_text(encoding="utf-8").splitlines():
                if line.startswith("LINKEDIN_EMAIL="): email = line.split("=", 1)[1].strip()
                if line.startswith("LINKEDIN_PASSWORD="): pw = line.split("=", 1)[1].strip()
        try:
            if email: page.fill(SEL["login_user"], email)
            if pw: page.fill(SEL["login_pass"], pw)
        except Exception:
            pass
        sys.stderr.write("Complete login (and any CAPTCHA/2FA) in the opened window...\n")
        deadline = time.time() + float(args.timeout)
        while time.time() < deadline:
            if is_logged_in(page):
                ctx.close(); print(json.dumps({"status": "ok", "already": False})); return
            time.sleep(3)
        ctx.close(); print(json.dumps({"status": "blocked", "reason": "login_timeout"}))

def _job_id_from_url(url: str) -> str:
    m = re.search(r"/jobs/view/(\d+)", url) or re.search(r"currentJobId=(\d+)", url)
    return m.group(1) if m else url

def cmd_search(args):
    filters = json.loads(args.filters) if args.filters else {}
    params = {"keywords": args.query or ""}
    if args.location: params["location"] = args.location
    if filters.get("f_WT"): params["f_WT"] = filters["f_WT"]      # 1=onsite,2=remote,3=hybrid
    if filters.get("f_E"): params["f_E"] = filters["f_E"]          # experience level
    if filters.get("f_TPR"): params["f_TPR"] = filters["f_TPR"]    # date posted
    if filters.get("f_AL"): params["f_AL"] = "true"                # easy-apply only
    qs = "&".join(f"{k}={str(v).replace(' ', '%20')}" for k, v in params.items())
    url = f"https://www.linkedin.com/jobs/search/?{qs}"
    results = []
    with sync_playwright() as p:
        ctx = launch(p); page = ctx.new_page()
        if not is_logged_in(page):
            ctx.close(); print(json.dumps({"status": "blocked", "reason": "not_logged_in"})); return
        page.goto(url, wait_until="domcontentloaded"); human_delay()
        cards = page.locator(SEL["job_card"])
        n = min(cards.count(), int(args.limit) * 2)  # over-fetch; some won't be easy-apply
        for i in range(n):
            if len(results) >= int(args.limit): break
            try:
                card = cards.nth(i); card.click(); human_delay()
                cur = page.url; jid = _job_id_from_url(cur)
                title = page.locator(SEL["job_title_panel"]).first.inner_text(timeout=5000)
                desc = ""
                try: desc = page.locator(SEL["job_desc_panel"]).first.inner_text(timeout=5000)
                except Exception: pass
                easy = page.locator(SEL["easy_apply_btn"]).count() > 0
                results.append({
                    "id": jid, "title": norm(title)[:160], "url": f"https://www.linkedin.com/jobs/view/{jid}/",
                    "easy_apply": easy, "description": desc[:4000],
                })
            except Exception:
                continue
        ctx.close()
    print(json.dumps({"status": "ok", "count": len(results), "jobs": results}))

# ---- Easy Apply modal walker ----------------------------------------------
def _read_groups(modal):
    """Return [{label, kind, ref_index, required, options}] for fillable fields on the current step."""
    groups = []
    els = modal.locator(SEL["form_group"])
    for i in range(els.count()):
        g = els.nth(i)
        try:
            label = norm(g.inner_text())[:200]
        except Exception:
            label = ""
        kind, options = "text", []
        if g.locator("select").count():
            kind = "select"
            opts = g.locator("select option")
            options = [norm(opts.nth(j).inner_text()) for j in range(opts.count())]
        elif g.locator("textarea").count():
            kind = "textarea"
        elif g.locator("input[type='radio']").count():
            kind = "radio"
            rb = g.locator("label")
            options = [norm(rb.nth(j).inner_text()) for j in range(rb.count())]
        elif g.locator("input[type='checkbox']").count():
            kind = "checkbox"
        required = g.locator("[aria-required='true'], .fb-dash-form-element__error-field").count() > 0 \
                   or "*" in (label[:3])
        groups.append({"label": label, "kind": kind, "required": required,
                       "options": options, "ref_index": i})
    return groups

def _answer_for(label, answers, profile):
    """Heuristic match label -> value from answers map + profile basics."""
    nl = norm(label)
    if nl in answers: return answers[nl]
    for k, v in answers.items():
        if norm(k) and norm(k) in nl: return v
    ident = (profile.get("identity") or {})
    pref = (profile.get("preferences") or {})
    if "email" in nl: return ident.get("email")
    if "phone" in nl or "mobile" in nl: return ident.get("phone")
    if "city" in nl or "location" in nl: return ident.get("location")
    if "first name" in nl: return (ident.get("full_name") or "").split(" ")[0]
    if "last name" in nl: return (ident.get("full_name") or "").split(" ")[-1]
    # years-of-experience style numeric questions
    if "years" in nl or "experience" in nl:
        yps = (profile.get("experience") or {}).get("years_per_skill") or {}
        for skill, yrs in yps.items():
            if norm(skill) in nl: return str(yrs)
        tot = (profile.get("experience") or {}).get("total_years")
        if tot is not None: return str(tot)
    if "sponsor" in nl:
        ns = (profile.get("work_authorization") or {}).get("needs_sponsorship")
        if ns is not None: return "Yes" if ns else "No"
    if "authori" in nl or "legally" in nl:
        return "Yes"  # only set when profile indicates authorization; orchestrator validates
    return None

def _fill_group(g, group, value):
    try:
        if group["kind"] in ("text", "textarea"):
            tgt = g.locator("input, textarea").first
            tgt.fill(str(value)); return True
        if group["kind"] == "select":
            g.locator("select").first.select_option(label=re.compile(re.escape(str(value)), re.I)); return True
        if group["kind"] == "radio":
            g.locator("label", has_text=re.compile(re.escape(str(value)), re.I)).first.click(); return True
        if group["kind"] == "checkbox":
            if str(value).lower() in ("yes", "true", "1"):
                g.locator("input[type='checkbox']").first.check()
            return True
    except Exception:
        return False
    return False

def cmd_apply(args):
    answers = {}
    if args.answers and Path(args.answers).exists():
        answers = {norm(k): v for k, v in json.loads(Path(args.answers).read_text(encoding="utf-8")).items()}
    profile = {}
    pf = JOB_ENGINE / "profile.yaml"
    if pf.exists():
        try:
            import yaml; profile = yaml.safe_load(pf.read_text(encoding="utf-8")) or {}
        except Exception: pass
    mode = args.mode  # auto | review
    result = {"status": "error", "job_url": args.job_url, "mode": mode}
    with sync_playwright() as p:
        ctx = launch(p); page = ctx.new_page()
        if not is_logged_in(page):
            ctx.close(); print(json.dumps({"status": "blocked", "reason": "not_logged_in"})); return
        page.goto(args.job_url, wait_until="domcontentloaded"); human_delay()
        if page.locator(SEL["easy_apply_btn"]).count() == 0:
            ctx.close(); print(json.dumps({"status": "skip", "reason": "no_easy_apply"})); return
        page.locator(SEL["easy_apply_btn"]).first.click(); human_delay()
        # upload tailored resume if a file input is present
        if args.resume and Path(args.resume).exists():
            try:
                page.locator(SEL["resume_upload"]).first.set_input_files(args.resume, timeout=4000)
                human_delay()
            except Exception: pass

        unanswered = []
        for step in range(15):  # safety bound on modal steps
            modal = page.locator(SEL["modal"]).first
            groups = _read_groups(modal)
            for g_meta in groups:
                gi = modal.locator(SEL["form_group"]).nth(g_meta["ref_index"])
                val = _answer_for(g_meta["label"], answers, profile)
                if val is None:
                    if g_meta["required"]:
                        unanswered.append({"label": g_meta["label"], "kind": g_meta["kind"],
                                           "options": g_meta["options"]})
                    continue
                _fill_group(gi, g_meta, val)
                human_delay()
            if unanswered:
                ctx.close()
                print(json.dumps({"status": "needs_answers", "job_url": args.job_url,
                                  "questions": unanswered}))
                return
            # advance: submit > review > next
            if page.locator(SEL["modal_submit"]).count():
                if mode == "auto":
                    page.locator(SEL["modal_submit"]).first.click(); human_delay()
                    shot = JOB_ENGINE / "screenshots" / f"{_job_id_from_url(args.job_url)}.png"
                    shot.parent.mkdir(parents=True, exist_ok=True)
                    try: page.screenshot(path=str(shot))
                    except Exception: pass
                    ctx.close()
                    print(json.dumps({"status": "submitted", "job_url": args.job_url,
                                      "screenshot": str(shot)})); return
                else:  # review: stop at submit, screenshot the review state
                    shot = JOB_ENGINE / "screenshots" / f"{_job_id_from_url(args.job_url)}_review.png"
                    shot.parent.mkdir(parents=True, exist_ok=True)
                    try: page.screenshot(path=str(shot))
                    except Exception: pass
                    ctx.close()
                    print(json.dumps({"status": "ready_for_review", "job_url": args.job_url,
                                      "screenshot": str(shot),
                                      "note": "re-run with --mode auto to submit"})); return
            elif page.locator(SEL["modal_review"]).count():
                page.locator(SEL["modal_review"]).first.click(); human_delay()
            elif page.locator(SEL["modal_next"]).count():
                page.locator(SEL["modal_next"]).first.click(); human_delay()
            else:
                ctx.close()
                print(json.dumps({"status": "error", "error": "no_advance_button",
                                  "job_url": args.job_url})); return
        ctx.close()
        print(json.dumps({"status": "error", "error": "step_limit_exceeded"}))

# ----------------------------------------------------------------------------- cli
def main():
    ap = argparse.ArgumentParser(description="LinkedIn Easy Apply driver")
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("check")
    lp = sub.add_parser("login"); lp.add_argument("--timeout", default=300)
    sp = sub.add_parser("search")
    sp.add_argument("--query", required=True); sp.add_argument("--location", default="")
    sp.add_argument("--filters", default=""); sp.add_argument("--limit", default=10)
    ap2 = sub.add_parser("apply")
    ap2.add_argument("--job-url", dest="job_url", required=True)
    ap2.add_argument("--answers", default=""); ap2.add_argument("--resume", default="")
    ap2.add_argument("--mode", choices=["auto", "review"], default="review")
    args = ap.parse_args()
    {"check": cmd_check, "login": cmd_login, "search": cmd_search, "apply": cmd_apply}[args.cmd](args)

if __name__ == "__main__":
    main()
