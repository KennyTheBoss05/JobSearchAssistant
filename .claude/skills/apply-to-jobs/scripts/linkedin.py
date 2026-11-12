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
`apply` errors also carry "screenshot" + "html" (job_engine/screenshots/<id>_error.{png,html})
so the orchestrator can diagnose selector drift. Answers = profile.yaml:saved_answers
overlaid by --answers (per-job wins).
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
    # Easy Apply trigger is now an <a aria-label="Easy Apply to this job"> in LinkedIn's
    # current UI (was button.jobs-apply-button). Keep button variants as fallbacks.
    "easy_apply_btn": "a[aria-label*='Easy Apply'], button[aria-label*='Easy Apply'], button.jobs-apply-button",
    # 2026-11: the modal is a native <dialog open> with hashed classes (no role attr, no
    # artdeco classes). Fields are found by tagging controls in _read_groups, buttons by
    # accessible name (scoped to the modal — page carousels also have a 'Next').
    "modal": "dialog[open], div.jobs-easy-apply-modal, [role='dialog']",
    # Search-result cards: data-occludable-job-id is the stable, complete set (25 vs 7).
    "job_card": "li[data-occludable-job-id], div.job-card-container, li.jobs-search-results__list-item",
    # 2026-11: /jobs/search/ redirects to /jobs/search-results/ (hashed classes, no
    # data-occludable-job-id). Cards carry componentkey="job-card-component-ref-<id>".
    "job_card_id": "[componentkey^='job-card-component-ref-']",
    "job_desc_panel": "div#job-details, article.jobs-description__container, div.jobs-description__content, [componentkey^='JobDetails_AboutTheJob_'], [data-testid='expandable-text-box']",
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

def _has_li_at(ctx) -> bool:
    """Authoritative, navigation-free login check: LinkedIn sets the `li_at` auth
    cookie only on a fully authenticated session. Polling this during login avoids
    yanking the page around mid-flow (critical for Microsoft/Google SSO logins)."""
    try:
        for c in ctx.cookies():
            if c.get("name") == "li_at" and c.get("value"):
                return True
    except Exception:
        pass
    return False

def is_logged_in(page) -> bool:
    # Cookie check first — cheap and doesn't disturb any in-progress navigation.
    try:
        if _has_li_at(page.context):
            return True
    except Exception:
        pass
    try:
        page.goto("https://www.linkedin.com/feed/", wait_until="domcontentloaded", timeout=30000)
    except Exception:
        # PWTimeout, or navigation interrupted by an SSO redirect — fall through and
        # judge by the resulting URL / cookie rather than crashing.
        pass
    if _has_li_at(page.context):
        return True
    if "login" in page.url or "checkpoint" in page.url:
        return False
    try:
        page.wait_for_selector(SEL["logged_in"], timeout=8000)
        return True
    except Exception:
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
        sys.stderr.write("Complete login (and any CAPTCHA/2FA/SSO) in the opened window...\n")
        deadline = time.time() + float(args.timeout)
        while time.time() < deadline:
            # Poll the auth cookie only — do NOT navigate here, or we'd interrupt the
            # user's in-progress SSO redirect (e.g. Microsoft/Google login) every tick.
            if _has_li_at(ctx):
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
    if filters.get("geoId"): params["geoId"] = filters["geoId"]    # survives the search-results redirect; `location` doesn't
    qs = "&".join(f"{k}={str(v).replace(' ', '%20')}" for k, v in params.items())
    url = f"https://www.linkedin.com/jobs/search/?{qs}"
    results = []
    limit = int(args.limit)
    with sync_playwright() as p:
        ctx = launch(p); page = ctx.new_page()
        if not is_logged_in(page):
            ctx.close(); print(json.dumps({"status": "blocked", "reason": "not_logged_in"})); return
        page.goto(url, wait_until="domcontentloaded"); human_delay()
        page.wait_for_timeout(3000)
        # Collect ids from the list (new UI componentkey, legacy data attr), scrolling to load more.
        ids = []
        for _ in range(4):
            keys = page.locator(SEL["job_card_id"]).evaluate_all("els => els.map(e => e.getAttribute('componentkey'))")
            keys += page.locator(SEL["job_card"]).evaluate_all("els => els.map(e => e.getAttribute('data-occludable-job-id') || '')")
            for k in keys:
                m = re.search(r"(\d{8,})$", k or "")
                if m and m.group(1) not in ids: ids.append(m.group(1))
            if len(ids) >= limit: break
            page.mouse.move(300, 450); page.mouse.wheel(0, 2500); human_delay()
        # Visit each job's own page: one code path for title/desc/easy-apply regardless of list UI.
        for jid in ids[:limit]:
            try:
                page.goto(f"https://www.linkedin.com/jobs/view/{jid}/", wait_until="domcontentloaded"); human_delay()
                parts = [norm(x) for x in page.title().split(" | ")]  # "Title | Company | LinkedIn"
                desc = ""
                try: desc = page.locator(SEL["job_desc_panel"]).first.inner_text(timeout=5000)
                except Exception: pass
                results.append({
                    "id": jid, "title": parts[0][:160], "company": parts[1] if len(parts) > 2 else "",
                    "url": f"https://www.linkedin.com/jobs/view/{jid}/",
                    "easy_apply": page.locator(SEL["easy_apply_btn"]).count() > 0, "description": desc[:4000],
                })
            except Exception:
                continue
        ctx.close()
    print(json.dumps({"status": "ok", "count": len(results), "jobs": results}))

# ---- Easy Apply modal walker ----------------------------------------------
# Tags every fillable control in the modal with data-ja-idx and describes it. Class names are
# hashed, so we rely only on semantic HTML: <label for>, <fieldset>/<legend>, required attrs.
_GROUPS_JS = r"""d => {
  const out = []; let i = 0;
  const vis = e => !!(e.offsetWidth || e.offsetHeight || e.getClientRects().length);
  const labelOf = e => {
    let l = e.id && d.querySelector('label[for="' + CSS.escape(e.id) + '"]');
    if (!l) l = e.closest('label');
    return (l ? l.innerText : (e.getAttribute('aria-label') || '')).trim();
  };
  // Radio option text lives in a sibling div (2026-11), not a <label>: climb to the first
  // ancestor with text.
  const optOf = r => {
    const l = r.id && d.querySelector('label[for="' + CSS.escape(r.id) + '"]');
    if (l && l.innerText.trim()) return l.innerText.trim();
    for (let n = r.parentElement, k = 0; n && k < 4; n = n.parentElement, k++)
      if ((n.innerText || '').trim()) return n.innerText.trim();
    return '';
  };
  for (const fs of d.querySelectorAll('fieldset')) {
    const opts = [...fs.querySelectorAll('input[type=radio], input[type=checkbox]')];
    if (!opts.length) continue;
    fs.dataset.jaIdx = i;
    // No <legend> in the 2026-11 UI: the question is each radio's aria-label, and the '*'
    // required marker sits in a sibling of the fieldset.
    const leg = ((fs.querySelector('legend') || {}).innerText || fs.getAttribute('aria-label')
                 || opts[0].getAttribute('aria-label') || '').trim();
    const around = ((fs.parentElement || fs).innerText || '');
    out.push({idx: i++, kind: opts[0].type === 'radio' ? 'radio' : 'checkbox', label: leg,
      required: opts.some(r => r.required || r.getAttribute('aria-required') === 'true')
                || fs.getAttribute('aria-required') === 'true' || leg.includes('*') || around.includes('*'),
      options: opts.map(optOf), filled: opts.some(r => r.checked)});
  }
  for (const e of d.querySelectorAll('input, select, textarea')) {
    if (e.closest('fieldset') && (e.type === 'radio' || e.type === 'checkbox')) continue;
    if (['hidden', 'file', 'submit', 'button', 'radio'].includes(e.type) || !vis(e)) continue;
    e.dataset.jaIdx = i;
    const label = labelOf(e);
    const kind = e.tagName === 'SELECT' ? 'select' : e.tagName === 'TEXTAREA' ? 'textarea'
               : e.type === 'checkbox' ? 'checkbox' : 'text';
    const options = kind === 'select' ? [...e.options].map(o => o.text.trim()) : [];
    let filled = kind === 'checkbox' ? e.checked : !!(e.value || '').trim();
    if (kind === 'select') filled = filled && !/^select an option$/i.test((e.options[e.selectedIndex] || {}).text || '');
    out.push({idx: i++, kind, label,
      required: e.required || e.getAttribute('aria-required') === 'true' || label.includes('*'),
      options, filled});
  }
  return out;
}"""

def _read_groups(modal):
    """Return [{idx, label, kind, required, options, filled}] for fillable controls on this step."""
    return modal.evaluate(_GROUPS_JS)

def _pick(options, value):
    """Option text matching value: exact (case-insensitive), then substring either way."""
    v = norm(str(value))
    for o in options:
        if norm(o) == v: return o
    for o in options:
        if v and (v in norm(o) or norm(o) in v): return o
    return None

def _answer_for(label, answers, profile):
    """Heuristic match label -> value from answers map + profile basics."""
    nl = norm(label)
    if nl in answers: return answers[nl]
    for k, v in answers.items():
        if norm(k) and norm(k) in nl: return v
    ident = (profile.get("identity") or {})
    pref = (profile.get("preferences") or {})
    if "email" in nl: return ident.get("email")
    if ("phone" in nl or "mobile" in nl) and "country code" not in nl:
        # LinkedIn has a separate country-code select and rejects '+'/symbols here:
        # "+44 7700900123" -> "7700900123"
        ph = ident.get("phone") or ""
        return re.sub(r"\D", "", ph.split(" ", 1)[-1]) or None
    if "relocat" in nl:  # before the location rule: "relocation" contains "location"
        wr = pref.get("willing_to_relocate")
        return None if wr is None else ("Yes" if wr else "No")
    if "city" in nl or nl.startswith("location"): return ident.get("location")  # not "this job's location"
    if "first name" in nl: return (ident.get("full_name") or "").split(" ")[0]
    if "last name" in nl: return (ident.get("full_name") or "").split(" ")[-1]
    # years-of-experience style numeric questions
    if "years" in nl:  # yes/no "do you have experience with X?" must not get a number
        yps = (profile.get("experience") or {}).get("years_per_skill") or {}
        for skill, yrs in yps.items():
            if norm(skill) in nl: return str(yrs)
        # Only generic experience questions get total_years; an unlisted skill must go to
        # the orchestrator (returning total_years there would fabricate a number).
        tot = (profile.get("experience") or {}).get("total_years")
        if tot is not None and re.search(r"(total|overall|professional|work experience|years of experience do you have\??$)", nl):
            return str(tot)
        return None
    if "sponsor" in nl and "without" in nl:
        return None  # "authorized WITHOUT sponsorship" inverts the meaning — let the orchestrator answer
    if "sponsor" in nl:
        ns = (profile.get("work_authorization") or {}).get("needs_sponsorship")
        if ns is not None: return "Yes" if ns else "No"
    if "authori" in nl or "legally" in nl:
        # "Yes" only when the label names a country the profile lists; anything else
        # (another country, "this country") goes to the orchestrator via needs_answers.
        alias = {"uk": "united kingdom", "united kingdom": "uk"}
        for c in (profile.get("work_authorization") or {}).get("countries_authorized") or []:
            for name in {norm(c), alias.get(norm(c), norm(c))}:
                if re.search(rf"\b{re.escape(name)}\b", nl): return "Yes"
    return None

def _fill_group(modal, group, value):
    """Fill one tagged control. Returns False when the value doesn't fit (e.g. no matching option)."""
    el = modal.locator(f"[data-ja-idx='{group['idx']}']").first
    try:
        if group["kind"] in ("text", "textarea"):
            el.fill(str(value)); return True
        if group["kind"] == "select":
            opt = _pick(group["options"], value)
            if opt is None: return False
            el.select_option(label=opt); return True
        if group["kind"] == "radio":
            opt = _pick(group["options"], value)
            if opt is None: return False
            return _check_radio(el.locator("input[type='radio']").nth(group["options"].index(opt)))
        if group["kind"] == "checkbox":
            if str(value).lower() in ("yes", "true", "1"):
                (el if el.evaluate("e => e.tagName") == "INPUT" else el.locator("input").first).check(force=True)
            return True
    except Exception:
        return False
    return False

def _check_radio(r):
    """LinkedIn's styled radios often ignore check(force=True); fall back to clicking the
    nearest ancestor with visible text (the option/card). Returns the final checked state."""
    try: r.check(force=True, timeout=3000)
    except Exception: pass
    if not r.is_checked():
        r.evaluate("e => { for (let n = e.parentElement, k = 0; n && k < 4; n = n.parentElement, k++)"
                   " if ((n.innerText || '').trim()) { n.click(); return; } }")
        r.page.wait_for_timeout(500)
    return r.is_checked()

def _modal_button(modal, pattern):
    b = modal.get_by_role("button", name=re.compile(pattern, re.I))
    return b.first if b.count() else None

def _attach_resume(page, modal, resume):
    """Select the tailored resume in the modal's resume list, uploading it once if absent.
    Returns True only if the tailored file ends up as the checked choice."""
    # Each resume card is a radio whose aria-label is the file name. Always upload: a fresh
    # upload lands at the top of the list and is auto-selected, whereas an older saved copy
    # can sit in the collapsed part of the list where clicks don't register.
    radio = modal.locator(f"input[type='radio'][aria-label={json.dumps(Path(resume).name)}]")
    before = radio.count()
    up = _modal_button(modal, r"^\s*upload resume\s*$")
    if up is None: return False
    with page.expect_file_chooser() as fc:
        up.click()
    fc.value.set_files(resume)
    try:
        for _ in range(40):  # upload time varies (4s-6s+)
            if radio.count() > before: break
            page.wait_for_timeout(500)
        if any(radio.nth(i).is_checked() for i in range(radio.count())):
            return True
        return _check_radio(radio.first)
    except Exception:
        return False

def cmd_apply(args):
    profile = {}
    pf = JOB_ENGINE / "profile.yaml"
    if pf.exists():
        try:
            import yaml; profile = yaml.safe_load(pf.read_text(encoding="utf-8")) or {}
        except Exception: pass
    # Answer bank first, then this job's answers.json (per-job overrides win).
    answers = {norm(k): v for k, v in (profile.get("saved_answers") or {}).items()}
    if args.answers and Path(args.answers).exists():
        answers.update({norm(k): v for k, v in json.loads(Path(args.answers).read_text(encoding="utf-8")).items()})
    mode = args.mode  # auto | review
    with sync_playwright() as p:
        ctx = launch(p); page = ctx.new_page()
        if not is_logged_in(page):
            ctx.close(); print(json.dumps({"status": "blocked", "reason": "not_logged_in"})); return
        page.goto(args.job_url, wait_until="domcontentloaded"); human_delay()
        if page.locator(SEL["easy_apply_btn"]).count() == 0:
            ctx.close(); print(json.dumps({"status": "skip", "reason": "no_easy_apply"})); return
        page.locator(SEL["easy_apply_btn"]).first.click(); human_delay()
        resume = str(Path(args.resume).resolve()) if args.resume and Path(args.resume).exists() else ""
        resume_attached = None  # None = no resume step seen / no --resume given
        unanswered = []
        def done(payload):
            ctx.close(); payload.update(job_url=args.job_url, resume_attached=resume_attached)
            print(json.dumps(payload))
        def shot(suffix=""):
            path = JOB_ENGINE / "screenshots" / f"{_job_id_from_url(args.job_url)}{suffix}.png"
            path.parent.mkdir(parents=True, exist_ok=True)
            try: page.screenshot(path=str(path))
            except Exception: pass
            return str(path)
        def fail(error, **extra):
            """Error payload + screenshot + modal HTML (page HTML if no modal) for self-heal."""
            html = JOB_ENGINE / "screenshots" / f"{_job_id_from_url(args.job_url)}_error.html"
            png = shot("_error")
            try:
                try: src = page.locator(SEL["modal"]).first.inner_html(timeout=3000)
                except Exception: src = page.content()
                html.write_text(src, encoding="utf-8")
            except Exception: pass
            return done({"status": "error", "error": error, "screenshot": png, "html": str(html), **extra})
        for step in range(15):  # safety bound on modal steps
            modal = page.locator(SEL["modal"]).first
            try: modal.wait_for(timeout=8000)
            except Exception: return fail("no_modal")
            if resume and resume_attached is not True:
                # The resume section renders after the contact fields — wait for it, or a fast
                # pass skips the upload and submits the default resume (happened 2026-11-12).
                try:
                    modal.get_by_role("button", name=re.compile(r"^\s*upload resume\s*$", re.I)).first.wait_for(timeout=6000)
                    resume_attached = _attach_resume(page, modal, resume)
                except Exception:
                    pass
            for g in _read_groups(modal):
                if g["filled"]: continue  # keep LinkedIn's prefilled values (contact info, chosen resume)
                val = _answer_for(g["label"], answers, profile)
                if val is None or not _fill_group(modal, g, val):
                    if g["required"]:
                        q = {"label": g["label"], "kind": g["kind"], "options": g["options"]}
                        if val is not None: q["rejected_value"] = val
                        unanswered.append(q)
                    continue
                human_delay()
            if unanswered:
                return done({"status": "needs_answers", "questions": unanswered})
            submit = _modal_button(modal, r"^\s*submit( application)?\s*$")
            if submit:
                if mode != "auto":
                    return done({"status": "ready_for_review", "screenshot": shot("_review"),
                                 "note": "re-run with --mode auto to submit"})
                if resume and resume_attached is not True:  # never submit the wrong resume
                    return fail("resume_not_attached")
                submit.click(); human_delay()
                # Verify LinkedIn's confirmation rather than assuming the click worked.
                try:
                    page.get_by_text(re.compile(r"application was sent|application submitted", re.I)).first.wait_for(timeout=10000)
                    confirmed = True
                except Exception:
                    confirmed = False
                return done({"status": "submitted" if confirmed else "submit_unconfirmed", "screenshot": shot()})
            adv = _modal_button(modal, r"^\s*review( your application)?\s*$") \
                  or _modal_button(modal, r"^\s*(next|continue( to next step)?)\s*$")
            if adv is None:
                return fail("no_advance_button")
            before = modal.inner_text()
            adv.click(); human_delay()
            if page.locator(SEL["modal"]).first.inner_text() == before:  # validation kept us here
                return fail("stuck_on_step", modal_text=norm(before)[:1500])
        return fail("step_limit_exceeded")

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
