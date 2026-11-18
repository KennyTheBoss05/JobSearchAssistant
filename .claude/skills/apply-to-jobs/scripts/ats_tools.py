#!/usr/bin/env python3
"""
ats_tools.py — offline helpers for external-ATS applies. Each subcommand prints ONE JSON object.

  detect  --url U            -> {"ats","host","tenant"}
  seen    --id ID [--url U]  -> {"seen":bool,"reason":str|null}   (reads applications_log.jsonl)
  account --site URL|host    -> {"site","email","password","created":bool}  (job_engine/accounts.json)
  inbox   --from-domain D [...] [--minutes 15] [--wait 90] | --check  -> {"status","code","link"}  (Gmail IMAP)
  selftest
Exit code: 1 when the JSON has status "error", else 0.
"""
from __future__ import annotations
import argparse, datetime, email, email.utils, html, imaplib, json, os, re, secrets, string, sys, time
from pathlib import Path
from urllib.parse import parse_qsl, urlencode, urlsplit

HERE = Path(__file__).resolve()

def find_job_engine() -> Path:  # copy of checks.py's (importing linkedin.py would pull in Playwright)
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

# ----------------------------------------------------------------------------- detect
HOSTS = [("greenhouse.io", "greenhouse"), ("lever.co", "lever"), ("ashbyhq.com", "ashby"),
         ("myworkdayjobs.com", "workday"), ("myworkday.com", "workday"),
         ("smartrecruiters.com", "smartrecruiters"), ("icims.com", "icims"), ("taleo.net", "taleo"),
         ("workable.com", "workable"), ("linkedin.com", "linkedin")]

def detect_ats(url: str) -> dict:
    u = urlsplit(url if "//" in url else "//" + url)
    host = (u.hostname or "").lower()
    first = next((s for s in u.path.split("/") if s), None)
    for d, ats in HOSTS:
        if host == d or host.endswith("." + d):
            tenant = first if ats in ("lever", "ashby") else host.split(".")[0] if ats == "workday" else None
            return {"ats": ats, "host": host, "tenant": tenant}
    return {"ats": "unknown", "host": host, "tenant": None}

TRACKING = ("ref", "source", "src", "trk", "gh_src", "lever-source", "lever-origin")

def norm_url(url: str) -> str:
    """Dedup key: https, lowercase host, no trailing slash/fragment, tracking params dropped,
    job-identifying params (gh_jid, job=...) kept, sorted."""
    u = urlsplit(url if "//" in url else "//" + url)
    q = sorted((k, v) for k, v in parse_qsl(u.query, keep_blank_values=True)
               if not (k.lower().startswith("utm_") or k.lower() in TRACKING))
    return f"https://{(u.hostname or '').lower()}{u.path.rstrip('/')}" + (f"?{urlencode(q)}" if q else "")

def site_key(url_or_host: str) -> str:
    return detect_ats(url_or_host)["host"]

# ----------------------------------------------------------------------------- dedup
DONE = ("submitted", "submit_unconfirmed", "parked")
SEEN_SKIPS = ("disqualified", "fit", "offsite", "driver:")

def is_seen(rows: list, job_id: str, url: str | None = None) -> str | None:
    last = next((r for r in reversed(rows) if str(r.get("id")) == str(job_id)), None)
    if last:
        if last.get("status") in DONE:
            return f"status {last['status']}"
        if str(last.get("skip_reason") or "").startswith(SEEN_SKIPS):
            return f"skip_reason {last['skip_reason']}"
    if url:
        n = norm_url(url)
        if any(r.get("status") in DONE and r.get("external_url") and norm_url(r["external_url"]) == n for r in rows):
            return "external_url already applied"
    return None

def read_log(log: Path | None = None) -> list:
    log = log or JE / "applications_log.jsonl"
    rows = []
    if log.exists():
        for line in log.read_text(encoding="utf-8").splitlines():
            try:
                r = json.loads(line)
            except ValueError:
                continue
            if isinstance(r, dict):  # a stray `null` / list line must not crash dedup
                rows.append(r)
    return rows

# ----------------------------------------------------------------------------- accounts
def gen_password(n: int = 20) -> str:
    sym = "!@#$%^&*-_"
    pools = [string.ascii_uppercase, string.ascii_lowercase, string.digits, sym]
    chars = [secrets.choice(p) for p in pools] + [secrets.choice("".join(pools)) for _ in range(n - 4)]
    secrets.SystemRandom().shuffle(chars)
    return "".join(chars)

def get_or_create(accounts: dict, site: str, email: str) -> tuple:
    key = site_key(site)
    if key in accounts:
        return accounts[key], False
    accounts[key] = {"email": email, "password": gen_password(), "created": datetime.date.today().isoformat()}
    return accounts[key], True

# ----------------------------------------------------------------------------- inbox (Gmail IMAP)
def read_env(path: Path) -> dict:
    env = {}
    if path.exists():
        for line in path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                k, v = line.split("=", 1)
                env[k.strip()] = v.strip()
    return env

def gmail_creds(env: dict, identity_email: str) -> dict:
    user, pw = env.get("GMAIL_ADDRESS"), env.get("GMAIL_APP_PASSWORD")
    if not user or not pw:
        return {"error": "gmail_not_configured"}
    if user.lower() != (identity_email or "").lower():
        return {"error": "gmail_mismatch"}
    return {"user": user, "pw": pw}

def host_ok(host: str, domains: list) -> bool:
    host = (host or "").lower()
    return any(host == d.lower() or host.endswith("." + d.lower()) for d in domains)

def sender_matches(from_header: str, domains: list) -> bool:
    addr = email.utils.parseaddr(from_header)[1]
    return "@" in addr and host_ok(addr.rsplit("@", 1)[1], domains)

KEYWORD = re.compile(r"code|verification|verify|one-time|passcode|otp", re.I)
CODE = re.compile(r"\b(\d{4,8}|\d{2,4}[- ]\d{2,4})\b|\b(?=[A-Z0-9]*\d)[A-Z0-9]{6,8}\b")

def extract_code_link(body: str, domains: list) -> dict:
    text = re.sub(r"<(style|script)\b.*?</\1>", " ", body, flags=re.S | re.I)
    text = re.sub(r"<[^>]+>", " ", html.unescape(text))
    text = re.sub(r"https?://\S+", " ", text)  # URL digits (uid=..., ids) are never the code
    cands = []
    for k in KEYWORD.finditer(text):
        for m in CODE.finditer(text[k.end():k.end() + 80]):
            digits = re.sub(r"[- ]", "", m.group(0))
            if m.group(1) is not None and not (4 <= len(digits) <= 8):
                continue
            if re.fullmatch(r"(19|20)\d\d", digits):  # a year, not a code
                continue
            cands.append(digits if m.group(1) else m.group(0))
    code = next((c for c in cands if c.isdigit() and len(c) == 6), cands[0] if cands else None)
    raw = html.unescape(body)
    urls = re.findall(r'href=["\'](https://[^"\']+)', raw, re.I) + re.findall(r'https://[^\s"\'<>]+', raw)
    urls = [u.rstrip(".,;)") for u in urls]
    good = [u for u in urls if host_ok(urlsplit(u).hostname, domains)]
    link = next((u for u in good if re.search(r"verif|confirm|activat", u, re.I)), good[0] if good else None)
    return {"code": code, "link": link}

def msg_body(msg) -> str:
    parts = [p for p in msg.walk() if p.get_content_maintype() == "text"]
    for want in ("text/plain", "text/html"):
        for p in parts:
            if p.get_content_type() == want:
                try:
                    return (p.get_payload(decode=True) or b"").decode(p.get_content_charset() or "utf-8", "replace")
                except LookupError:  # unknown charset
                    return (p.get_payload(decode=True) or b"").decode("utf-8", "replace")
    return ""

def imap_query(domains: list, since: str) -> str:
    """SINCE <date> plus FROM per domain, OR-combined (IMAP OR is binary prefix)."""
    q = [f'FROM "{d}"' for d in domains]
    while len(q) > 1:
        q = [f"OR {q[0]} {q[1]}"] + q[2:]
    return f"SINCE {since} {q[0]}"

def cmd_inbox(a):
    email_id = (load_yaml(JE / "profile.yaml").get("identity") or {}).get("email")
    cred = gmail_creds(read_env(JE / ".env"), email_id)
    if "error" in cred:
        return {"status": "error", "error": cred["error"]}
    doms = [d.strip().lower() for d in (a.from_domain or [])]
    if not a.check and not doms:
        return {"status": "error", "error": "no_from_domain"}
    if any(not re.fullmatch(r"[a-z0-9.-]+", d) for d in doms):  # goes into the IMAP command
        return {"status": "error", "error": "bad_from_domain"}
    deadline = time.monotonic() + a.wait
    try:
        box = imaplib.IMAP4_SSL("imap.gmail.com", 993, timeout=20)
        try:
            box.login(cred["user"], cred["pw"])
            if a.check:
                return {"status": "ok"}
            box.select("INBOX", readonly=True)
            while True:
                now = datetime.datetime.now(datetime.timezone.utc)
                cutoff = now - datetime.timedelta(minutes=a.minutes)
                since = (now - datetime.timedelta(days=1)).strftime("%d-%b-%Y")  # SINCE is date-only, server tz
                ids = box.search(None, imap_query(doms, since))[1][0].split()
                for i in reversed(ids[-30:]):  # newest first
                    if time.monotonic() > deadline:
                        return {"status": "none"}
                    hdr = email.message_from_bytes(box.fetch(i, "(BODY.PEEK[HEADER.FIELDS (FROM DATE)])")[1][0][1])
                    try:
                        when = email.utils.parsedate_to_datetime(hdr["Date"])
                        if when.tzinfo is None:
                            when = when.replace(tzinfo=datetime.timezone.utc)
                    except Exception:
                        continue
                    if when < cutoff or not sender_matches(hdr.get("From", ""), doms):
                        continue
                    msg = email.message_from_bytes(box.fetch(i, "(BODY.PEEK[])")[1][0][1])
                    try:
                        r = extract_code_link(msg_body(msg), doms)
                    except Exception:
                        continue
                    if r["code"] or r["link"]:
                        return {"status": "ok", **r}
                if time.monotonic() + 10 > deadline:
                    return {"status": "none"}
                time.sleep(10)
        finally:
            try:
                box.logout()
            except Exception:
                pass
    except Exception as ex:
        return {"status": "error", "error": f"imap: {type(ex).__name__}"}

def cmd_detect(a):
    return detect_ats(a.url)

def cmd_seen(a):
    reason = is_seen(read_log(), a.id, a.url)
    return {"seen": reason is not None, "reason": reason}

def cmd_account(a):
    email = (load_yaml(JE / "profile.yaml").get("identity") or {}).get("email")
    if not email:
        return {"status": "error", "error": "no_email"}
    f = JE / "accounts.json"
    try:
        accounts = json.loads(f.read_text(encoding="utf-8")) if f.exists() else {}
    except ValueError:
        return {"status": "error", "error": "accounts_corrupt"}
    entry, created = get_or_create(accounts, a.site, email)
    if created:
        tmp = f.with_suffix(".tmp")
        tmp.write_text(json.dumps(accounts, indent=2), encoding="utf-8")
        os.replace(tmp, f)
    return {"site": site_key(a.site), "email": entry["email"], "password": entry["password"], "created": created}

def cmd_selftest(a=None):
    assert detect_ats("https://job-boards.greenhouse.io/acme/jobs/123")["ats"] == "greenhouse"
    assert detect_ats("https://boards.greenhouse.io/acme/jobs/123")["ats"] == "greenhouse"
    assert detect_ats("https://jobs.lever.co/acme/abc-123/apply") == {"ats": "lever", "host": "jobs.lever.co", "tenant": "acme"}
    assert detect_ats("https://jobs.ashbyhq.com/acme/uuid")["tenant"] == "acme"
    assert detect_ats("https://acme.wd5.myworkdayjobs.com/en-US/careers/job/x") == {"ats": "workday", "host": "acme.wd5.myworkdayjobs.com", "tenant": "acme"}
    assert detect_ats("https://www.linkedin.com/redir/redirect?url=x")["ats"] == "linkedin"
    assert detect_ats("https://greenhouse.io.evil.com/jobs/1")["ats"] == "unknown"
    assert detect_ats("https://careers.acme.com/jobs/1")["ats"] == "unknown"
    assert norm_url("https://Jobs.Lever.co/acme/abc/?utm_source=linkedin#apply") == "https://jobs.lever.co/acme/abc"
    assert norm_url("https://acme.com/careers?gh_jid=111") != norm_url("https://acme.com/careers?gh_jid=222")
    assert norm_url("https://acme.taleo.net/careersection/2/jobdetail.ftl?job=111&src=JB-1") \
           != norm_url("https://acme.taleo.net/careersection/2/jobdetail.ftl?job=222")
    assert norm_url("https://acme.taleo.net/jobdetail.ftl?src=x&job=111&lang=en") == norm_url("https://acme.taleo.net/jobdetail.ftl?lang=en&job=111")
    assert norm_url("http://jobs.lever.co/acme/abc") == norm_url("https://jobs.lever.co/acme/abc") == norm_url("jobs.lever.co/acme/abc")
    assert norm_url("https://jobs.lever.co/acme/abc?lever-source=LinkedIn&ref=x&gh_src=y") == "https://jobs.lever.co/acme/abc"
    import tempfile
    with tempfile.TemporaryDirectory() as td:
        lp = Path(td) / "log.jsonl"
        lp.write_text('null\n[1]\n"x"\n5\nnot json\n{"id": "7", "status": "submitted"}\n', encoding="utf-8")
        log_rows = read_log(lp)
        assert log_rows == [{"id": "7", "status": "submitted"}] and is_seen(log_rows, "7")
    rows = [{"id": "1", "status": "skipped", "skip_reason": "unknown required: q"},
            {"id": "1", "status": "submitted"},
            {"id": "2", "status": "ready_for_review"},
            {"id": "3", "status": "skipped", "skip_reason": "driver: budget"},
            {"id": "4", "status": "parked", "external_url": "https://jobs.lever.co/acme/abc"},
            {"id": "5", "status": "submitted"}, {"id": "5", "status": "skipped", "skip_reason": "unknown required: q"}]
    assert is_seen(rows, "1") and not is_seen(rows, "2") and is_seen(rows, "3")
    assert not is_seen(rows, "5")              # latest row wins
    assert is_seen(rows, "99", "https://jobs.lever.co/acme/abc/?utm_campaign=x")
    assert not is_seen(rows, "99", "https://jobs.lever.co/acme/other")
    p = gen_password()
    assert len(p) == 20 and any(c.isupper() for c in p) and any(c.islower() for c in p) \
           and any(c.isdigit() for c in p) and any(c in "!@#$%^&*-_" for c in p)
    acc = {}
    e1, c1 = get_or_create(acc, "acme.wd5.myworkdayjobs.com", "a@b.com")
    e2, c2 = get_or_create(acc, "acme.wd5.myworkdayjobs.com", "a@b.com")
    assert c1 and not c2 and e1["password"] == e2["password"]
    assert site_key("https://Acme.wd5.myworkdayjobs.com/x") == "acme.wd5.myworkdayjobs.com"
    assert gmail_creds({}, "a@gmail.com") == {"error": "gmail_not_configured"}
    assert gmail_creds({"GMAIL_ADDRESS": "x@gmail.com", "GMAIL_APP_PASSWORD": "p"}, "a@gmail.com") == {"error": "gmail_mismatch"}
    assert gmail_creds({"GMAIL_ADDRESS": "A@Gmail.com", "GMAIL_APP_PASSWORD": "p"}, "a@gmail.com") == {"user": "A@Gmail.com", "pw": "p"}
    assert sender_matches("Acme Careers <no-reply@acme.com>", ["myworkday.com", "acme.com"])
    assert sender_matches("x <notify@mail.greenhouse.io>", ["greenhouse.io"])
    assert not sender_matches("x <a@greenhouse.io.evil.com>", ["greenhouse.io"])
    assert extract_code_link("Your verification code is 123-456.", ["acme.com"])["code"] == "123456"
    assert extract_code_link("Use one-time passcode AB12CD to continue", ["acme.com"])["code"] == "AB12CD"
    assert extract_code_link("Order 99887766 shipped", ["acme.com"])["code"] is None   # no keyword
    r = extract_code_link('<a href="https://evil.com/?r=acme.com">x</a> <a href="https://acme.wd5.myworkday.com/verify?t=1">Verify</a>',
                          ["myworkday.com"])
    assert r["link"] == "https://acme.wd5.myworkday.com/verify?t=1"
    assert extract_code_link("<style>.code{margin:10px 2000}</style><p>Your verification code</p><b>731904</b>", ["acme.com"])["code"] == "731904"
    assert extract_code_link("see https://evil.com/?r=acme.com", ["acme.com"])["link"] is None
    r = extract_code_link("Please verify your email: https://acme.com/verify?uid=12345678", ["acme.com"])
    assert r["code"] is None and r["link"] == "https://acme.com/verify?uid=12345678"
    assert extract_code_link("Your code expires in 2026. Code: 482913", ["acme.com"])["code"] == "482913"
    assert extract_code_link("Verification code 4821, ref 99881", ["acme.com"])["code"] == "4821"   # no 6-digit run: first wins
    assert imap_query(["a.com"], "17-Nov-2026") == 'SINCE 17-Nov-2026 FROM "a.com"'
    assert imap_query(["a.com", "b.io", "c.co"], "17-Nov-2026") == 'SINCE 17-Nov-2026 OR OR FROM "a.com" FROM "b.io" FROM "c.co"'
    return {"status": "ok"}

def main():
    ap = argparse.ArgumentParser(description="ATS helpers for apply-to-jobs")
    sub = ap.add_subparsers(dest="cmd", required=True)
    d = sub.add_parser("detect"); d.add_argument("--url", required=True)
    e = sub.add_parser("seen"); e.add_argument("--id", required=True); e.add_argument("--url")
    c = sub.add_parser("account"); c.add_argument("--site", required=True)
    i = sub.add_parser("inbox"); i.add_argument("--from-domain", action="append"); i.add_argument("--check", action="store_true")
    i.add_argument("--minutes", type=int, default=15); i.add_argument("--wait", type=int, default=90)
    sub.add_parser("selftest")
    a = ap.parse_args()
    cmds = {"detect": cmd_detect, "seen": cmd_seen, "account": cmd_account, "inbox": cmd_inbox, "selftest": cmd_selftest}
    try:
        out = cmds[a.cmd](a)
    except Exception as ex:
        out = {"status": "error", "error": type(ex).__name__, "detail": str(ex)}
    print(json.dumps(out, ensure_ascii=False))
    sys.exit(1 if out.get("status") == "error" else 0)

if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    main()
