#!/usr/bin/env python3
"""
checks.py — deterministic gates for unattended apply runs. Each subcommand prints ONE JSON
object; exit code is 0 even on "fail" (callers read the JSON).

  claims  --file <docx|txt|md> | --text "<s>"  [--allow T ...]
          -> {"status":"ok"} | {"status":"fail","unsupported":[...]}
          Flags numbers / tech-like tokens / mid-sentence proper nouns that don't appear in
          the grounding corpus (masters/*.docx + evidence.md + profile.yaml + grounding.allow_terms).
  pdf     --pdf <path> [--pages N]
          -> {"status":"ok","pages":n} | {"status":"fail","problems":[...]}
  quota   -> {"submitted_today":k,"max_per_day":m,"remaining":r|null}
  selftest
"""
from __future__ import annotations
import argparse, datetime, json, re, sys
from pathlib import Path

HERE = Path(__file__).resolve()

def find_job_engine() -> Path:  # copy of linkedin.py's (importing it would pull in Playwright)
    p = HERE
    for _ in range(8):
        if (p / "job_engine").is_dir():
            return p / "job_engine"
        p = p.parent
    return HERE.parents[4] / "job_engine"

JE = find_job_engine()

def load_yaml(path: Path) -> dict:
    try:
        import yaml
        return yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    except Exception:
        return {}

def docx_text(path) -> str:
    import docx
    d = docx.Document(str(path))
    parts = [p.text for p in d.paragraphs]
    for t in d.tables:
        for row in t.rows:
            parts += [c.text for c in row.cells]
    return "\n".join(parts)

# ----------------------------------------------------------------------------- claims
STOP = set("""i dear hiring manager sincerely regards yours faithfully team mr ms mrs dr
january february march april may june july august september october november december
monday tuesday wednesday thursday friday saturday sunday e.g i.e etc""".split())
TOKEN = re.compile(r"[A-Za-z0-9£$€](?:[\w+#.\-/&%]|,(?=\d{3}))*")
NUMBER = re.compile(r"^\d[\d,]*(\.\d+)?(%|\+|k|m|bn)?$", re.I)

def _num_forms(tok: str) -> set:
    t = tok.replace(",", "").rstrip("+").lower()
    forms = {t}
    m = re.fullmatch(r"(\d+(?:\.\d+)?)(k|m|bn)", t)
    if m:
        mult = {"k": 1e3, "m": 1e6, "bn": 1e9}[m.group(2)]
        forms.add(f"{float(m.group(1)) * mult:.0f}")
    return forms

def _num_in(tok: str, corpus: str) -> bool:
    return any(re.search(rf"(?<![\d.]){re.escape(f)}(?![\d])", corpus) for f in _num_forms(tok))

def _supported(tok: str, corpus: str, allow_words: set) -> bool:
    low = tok.lower()
    if low in allow_words or low in STOP:
        return True
    if NUMBER.match(tok):
        return _num_in(tok, corpus)
    if low in corpus:
        return True
    parts = [p for p in re.split(r"[-/&]", tok) if p]
    if len(parts) > 1:  # "2019-2021", "Python/R", "Fine-Tuning": judge each part
        return all(_supported(p, corpus, allow_words) or not _checkable(p, False) for p in parts)
    return False

def _checkable(tok: str, sentence_start: bool) -> bool:
    if NUMBER.match(tok) or re.search(r"\d|[+#]", tok):
        return True                                     # (a) numbers, (b) C++, C#, GPT-4o
    if "." in tok.strip(".") and re.search(r"[A-Za-z]", tok):
        return True                                     # (b) Node.js
    if sum(c.isupper() for c in tok) >= 2:
        return True                                     # (b) AWS, LangGraph, PyTorch
    return tok[0].isupper() and not sentence_start      # (c) mid-sentence proper noun

def unsupported(text: str, corpus: str, allow=()) -> list:
    """Tokens in `text` not traceable to `corpus` (lowercased). Pure: used by selftest.
    # ponytail: token heuristic — catches invented numbers/tools/employers, not reworded soft
    # claims ("led a team"); upgrade path = fresh-context reviewer subagent."""
    corpus = re.sub(r"(?<=\d),(?=\d)", "", corpus.lower())
    allow_words = {w for a in allow for w in [a.lower().strip(" .")] + a.lower().replace(".", " ").split()}
    out = []
    for m in TOKEN.finditer(text):
        tok = m.group().rstrip(".-/&")
        if not tok:
            continue
        tok = tok.lstrip("£$€") if NUMBER.match(tok.lstrip("£$€")) else tok
        prev = text[:m.start()].rstrip(" \t")
        start = not prev or prev[-1] in ".!?:\n\r•\"“–—"
        if _checkable(tok, start) and not _supported(tok, corpus, allow_words) and tok not in out:
            out.append(tok)
    return out

def corpus_text() -> str:
    parts = [docx_text(p) for p in sorted((JE / "masters").glob("*.docx"))]
    for name in ("evidence.md", "profile.yaml"):
        f = JE / name
        if f.exists():
            parts.append(f.read_text(encoding="utf-8"))
    parts += [str(t) for t in (load_yaml(JE / "engine_config.yaml").get("grounding") or {}).get("allow_terms") or []]
    return "\n".join(parts)

def cmd_claims(a):
    if a.file:
        f = Path(a.file)
        text = docx_text(f) if f.suffix.lower() == ".docx" else f.read_text(encoding="utf-8")
    else:
        text = a.text or ""
    bad = unsupported(text, corpus_text(), a.allow or [])
    return {"status": "fail", "unsupported": bad} if bad else {"status": "ok"}

# ----------------------------------------------------------------------------- pdf
def cmd_pdf(a):
    import pdfplumber
    pages = a.pages or int((load_yaml(JE / "engine_config.yaml").get("resume") or {}).get("pages", 2))
    ident = load_yaml(JE / "profile.yaml").get("identity") or {}
    with pdfplumber.open(a.pdf) as pdf:
        n = len(pdf.pages)
        text = "\n".join(p.extract_text() or "" for p in pdf.pages)
    flat = re.sub(r"\s+", "", text).lower()
    problems = []
    if n != pages:
        problems.append(f"pages: {n} != {pages}")
    for key in ("full_name", "email"):
        v = re.sub(r"\s+", "", str(ident.get(key) or "")).lower()
        if v and v not in flat:
            problems.append(f"missing {key}")
    phone = re.sub(r"\D", "", str(ident.get("phone") or ""))[-7:]
    if phone and phone not in re.sub(r"\D", "", text):
        problems.append("missing phone")
    return {"status": "fail", "problems": problems} if problems else {"status": "ok", "pages": n}

# ----------------------------------------------------------------------------- quota
def cmd_quota(a=None):
    cap = (load_yaml(JE / "engine_config.yaml").get("selection") or {}).get("max_per_day", 30)
    today = datetime.date.today().isoformat()
    k = 0
    log = JE / "applications_log.jsonl"
    if log.exists():
        for line in log.read_text(encoding="utf-8").splitlines():
            try:
                r = json.loads(line)
            except ValueError:
                continue
            if r.get("status") in ("submitted", "submit_unconfirmed") and str(r.get("ts", "")).startswith(today):
                k += 1
    return {"submitted_today": k, "max_per_day": cap, "remaining": None if not cap else max(cap - k, 0)}

# ----------------------------------------------------------------------------- selftest
def cmd_selftest(a=None):
    corpus = "Built RAG pipelines in Python with LangChain at Acme Corp. Improved recall by 12% over 3 years."
    assert unsupported("Improved accuracy by 37% using LangGraph", corpus) == ["37%", "LangGraph"]
    assert unsupported("Built RAG pipelines with LangChain in Python, improving recall 12% at Acme.", corpus) == []
    assert unsupported("I am excited to join Formula. as an engineer", corpus) == ["Formula"]
    assert unsupported("I am excited to join Formula. as an engineer", corpus, ["Formula."]) == []
    assert unsupported("Shipped Node.js and C++ services for 3+ years", corpus) == ["Node.js", "C++"]
    assert unsupported("Grew revenue to £1,200 at Acme", corpus + " 1200") == []
    return {"status": "ok"}

def main():
    ap = argparse.ArgumentParser(description="Deterministic gates for apply-to-jobs")
    sub = ap.add_subparsers(dest="cmd", required=True)
    c = sub.add_parser("claims")
    c.add_argument("--file"); c.add_argument("--text"); c.add_argument("--allow", action="append")
    p = sub.add_parser("pdf"); p.add_argument("--pdf", required=True); p.add_argument("--pages", type=int)
    sub.add_parser("quota"); sub.add_parser("selftest")
    a = ap.parse_args()
    out = {"claims": cmd_claims, "pdf": cmd_pdf, "quota": cmd_quota, "selftest": cmd_selftest}[a.cmd](a)
    print(json.dumps(out, ensure_ascii=False))

if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    main()
