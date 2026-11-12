# 004 — Apply to jobs outside LinkedIn Easy Apply (external ATS, v2)

Status: queued
Lane: chat
Created: 2026-11-12
Priority: P2

## STOP — this task submits real job applications

Same rule as task 002: start in **review** mode, stop before submit, and only submit a specific
job after Kevin explicitly approves it. Max 2–3 live jobs per session. External application sites
create accounts and send emails in Kevin's name — treat each one as irreversible.

## The ask

v1 `apply-to-jobs` only handles LinkedIn Easy Apply. Any job whose apply button redirects off
LinkedIn is dropped: `cmd_apply` in `.claude/skills/apply-to-jobs/scripts/linkedin.py` (~line 417)
returns `{"status":"skip","reason":"no_easy_apply"}` and discards the target URL, and
`SKILL.md:78` / `references/decision-tree.md` ("External-ATS redirect (v1)") tell the orchestrator
to move on. That is likely most of the market.

Extend the suite so those jobs can be applied to:

1. **Capture the redirect.** On `no_easy_apply`, click the external "Apply" button, follow the new
   tab, and return `{"status":"external","ats":"<greenhouse|lever|ashby|workday|unknown>","url":...}`
   instead of a bare skip. Detect the ATS from the hostname / DOM.
2. **Fill the common ATSs first.** Greenhouse, Lever and Ashby have stable public forms with no
   account required — implement those. Reuse the existing pipeline unchanged: fit scoring,
   tailored resume/cover letter (task 001's PDF export), `_answer_for` + the `needs_answers` →
   `answers.json` → re-invoke loop, and the never-fabricate decision tree.
3. **Everything else is review-only.** Workday, iCIMS, Taleo, custom careers pages: require account
   creation or are wildly inconsistent. For these, prepare the materials (tailored PDF, cover
   letter, drafted answers) and hand Kevin the URL + materials; don't auto-fill.
4. Probably split the code: keep `linkedin.py` for LinkedIn, add an `ats.py` driver (or one module
   per ATS if they diverge) sharing the same JSON-stdout contract and persistent browser profile.

Update `SKILL.md` (flow + the "Easy Apply only" line), `decision-tree.md` (replace the v1 external
section), and add an `ats-playbook.md` with verified per-ATS DOM notes like the Easy Apply one.

## Acceptance criteria

- [ ] A non-Easy-Apply LinkedIn job returns `status: external` with the correct ATS and URL.
- [ ] At least one real Greenhouse or Lever application reaches the review stop with a screenshot
      and correctly filled fields; submitted only after Kevin approves it.
- [ ] Unsupported ATSs produce a "manual" outcome with the prepared materials, not a crash or a
      silent skip.
- [ ] Every outcome is logged to `job_engine/applications_log.jsonl` with an `ats` field (coordinate
      with task 003's driver-side logging).
- [ ] SKILL.md, decision-tree.md and the new playbook reflect the new flow.

## Dependencies

- **001 (PDF export)** — external forms need a real uploaded resume file.
- **003 (logging/dedup)** — so external applications aren't re-applied on the next run.

## Out of scope

- Job boards other than LinkedIn as the *source* of jobs (site rotation — separate v2 item).
- Automating account creation / email verification for Workday-style ATSs.
- CAPTCHA solving — stop and hand to Kevin, as v1 does.

## Overrides in force

None.
