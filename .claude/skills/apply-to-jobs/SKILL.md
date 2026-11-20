---
name: apply-to-jobs
description: >-
  Autonomously applies to jobs end-to-end on LinkedIn (Easy Apply and external employer
  application sites), tailoring a resume and cover letter per job and answering screening questions from the user's pre-built
  profile — running start-to-finish without stopping unless it hits something only the user
  can resolve (CAPTCHA/2FA/expired login), interactively or on a schedule with no user
  present. Use whenever the user wants to apply for jobs, e.g. "apply to 5 data scientist
  jobs on LinkedIn", "go apply for some ML engineer roles in London under £90k", "apply to
  this job: <url>", "apply to 15 AI engineer jobs, auto", or when a prompt says "scheduled
  run". Supports a full-auto (submit) vs review (stop before submit) mode toggle. Requires
  job-profile-setup to have run first. Reads all tunable behavior from
  job_engine/engine_config.yaml.
---

# Apply to jobs (LinkedIn Easy Apply + external application sites)

You orchestrate an application run. You (main thread, Opus) own the single browser and do
all clicking via the driver; **subagents do text/document work** and return small JSON —
they never drive the LinkedIn browser. (The one exception: an external-application subagent
owns the separate `ats` playwright-cli session, one at a time.) Keep the main thread lean: it never sees change tables or
document text.

Read `references/easy-apply-playbook.md` (driver contract, UI notes) and
`references/decision-tree.md` (skip / queue / pause / self-heal rules) before the first
application in a run. Read `references/ats-playbook.md` before the first external application.

Scripts (in `.claude/skills/apply-to-jobs/scripts/`; run with the repo venv: `.venv\Scripts\python.exe`
on Windows, `.venv/bin/python` on macOS/Linux):
- `linkedin.py <check|login|search|apply>` — browser driver.
- `ats_tools.py <detect|seen|account|inbox|selftest>` — external-site helpers (ATS detect, dedup, accounts, Gmail codes).
- `checks.py <doctor|claims|pdf|quota>` — environment preflight + deterministic gates (grounding, PDF sanity, daily cap).
- `docx_to_pdf.py <docx> <pdf>` — Word COM / LibreOffice export.
- `autorun.py <run|install|uninstall|status>` — scheduler (see Scheduling).

## Parse the request
Extract: role/keywords, count **N**, location (`geoId` in filters; UK = 101165590), work
mode, salary, experience level, companies, date-posted, and/or direct job URLs. Mode
defaults to **review** unless the user says auto / full-auto / "just apply" / "don't stop".
A prompt containing "scheduled run" → **Scheduled mode** (below).

## Preflight
0. `checks.py doctor` (with the venv python; no venv yet → run it with any `python3`, it is
   stdlib-only). `status:"fail"` → stop. Interactive: show each `failed[].fix` and offer to run
   them (or run **job-profile-setup**), then re-run doctor. Scheduled: end the run, report the
   failures. Never work around a failed check. Pass `warnings` on to the user.
1. `job_engine/profile.yaml`, `evidence.md`, `masters/resume_base.docx` exist — else stop and
   tell the user to run **job-profile-setup**.
2. `checks.py quota` — if `remaining == 0`, report and stop.
3. **Pending questions (interactive only):** if `job_engine/pending_questions.md` has unchecked
   `- [ ]` items, ask the user all of them in one batch first. Write each answer to
   `profile.yaml:saved_answers` (key = normalized question: lowercase, collapsed whitespace)
   and tick the item `- [x]`.
4. `linkedin.py check`. If `logged_in:false` → interactive: run `linkedin.py login`, notify,
   wait. Scheduled: end the run (see Scheduled mode).
5. If `external.enabled`: `playwright-cli --version`; failure → external off for this run
   (say so in the report). Then `ats_tools.py inbox --check`; `status:"error"` → pass
   `allow_account_creation:false` for this run and say so in the report.
6. **Parked jobs (interactive only):** if `job_engine/parked.md` has unchecked `- [ ]` items,
   offer to finish them. Per item:
   1. Dispatch the external subagent with the item's url/resume/answers file and `reason`,
      `mode=review`, `gate_retry: true`. It re-drives to the gate (or to the final submit page
      if no gate shows yet), screenshots, and returns `parked` leaving the `ats` session open.
   2. Show the user the screenshot; ask them to clear the challenge (and click Submit if the
      form is on its final page) in the open browser window; wait for their confirmation.
   3. Re-dispatch with `gate_cleared: true`, `mode=auto`, same answers file. It confirms an
      already-submitted form, or continues from the current page and submits; then closes the session.
   4. `submitted`/`submit_unconfirmed` → tick `- [x]` and log a new line (becomes the job's latest
      status). Anything else → leave unticked, log it.

## The loop (until N submitted, candidates exhausted, or quota hit)
1. **Search** — subagent (**Haiku**): `linkedin.py search --query … --filters '<json>' --limit …`.
   **Dedup:** `ats_tools.py seen --id <id>` → `seen:true` drops the id; `status:"error"` →
   skip, log `skip_reason="dedup error"`, never apply (rules in `references/decision-tree.md`).
   External off (config or preflight 5) → skip `easy_apply:false` ids here, log
   `skip_reason="external disabled"`.
2. **Fit-score** — subagent (**Sonnet**): `prompts/fit_score.md` vs profile + evidence. Below
   `selection.fit_floor` → log `skip_reason="fit: <score> <why>"`. Rank best-first if
   `selection.rank_by_fit`.
3. **For each candidate, best first** — `checks.py quota` first; stop when `remaining` is 0.
   `easy_apply:false` → **External branch** (below; it tailors only after its skip checks).
   a. **Tailor** — one subagent (**Opus**) owns the whole document pipeline:
      - apply `prompts/resume_tailor.md` (pass `suggest_new_projects: 0` in auto mode);
      - apply the change table to a copy of `masters/resume_base.docx` → `job_engine/outputs/<id>.docx`
        (python-docx / docx skill);
      - `checks.py claims --file job_engine/outputs/<id>.docx --allow "<company>" --allow "<job title>"`;
      - `docx_to_pdf.py` → `job_engine/outputs/<Full Name> Resume - <Company>.pdf` (recruiters
        see the file name); then `checks.py pdf --pdf <that>`;
      - on a claims/pdf fail: revise once (replace unsupported terms with grounded ones; shorten
        edited lines to restore page count), re-run both checks; still failing →
        `{"status":"skip","reason":"grounding: <terms>"|"pdf: <problems>"}`;
      - cover letter only if the form has a slot (`cover_letter.attach_only_if_slot`): same flow
        with `prompts/cover_letter.md` + `masters/cover_letter_base.docx` + `checks.py claims`
        → `<Full Name> Cover Letter - <Company>.pdf`;
      - return **only** `{"status":"ok","resume_pdf":"…","cover_pdf":null|"…"}` (or the skip).
      `docx_to_pdf.py` error (no Word/LibreOffice) → stop the run; never upload the .docx.
   b. **Drive** — `linkedin.py apply --job-url <url> --resume <pdf> --answers
      job_engine/outputs/<id>_answers.json --mode <mode>`. The driver pre-fills from
      `saved_answers` + profile, then returns:
      - `needs_answers` → answer each via subagent (**Sonnet**, `prompts/qa_answer.md`). Every
        free-text answer goes through `checks.py claims --text "<answer>" --allow "<company>"`;
        `fail` counts as `CANNOT_ANSWER`. (Select/radio/yes-no answers taken from profile facts
        skip the check.) `CANNOT_ANSWER` on a required field → decision tree: **auto** = skip +
        queue to `pending_questions.md`; **review** = surface to user. Otherwise append to
        answers.json and re-invoke.
      - `submitted` / `submit_unconfirmed` → record (+ screenshot).
      - `ready_for_review` → show summary + screenshot; on approval re-run `--mode auto`.
      - `blocked` → session-level block (decision tree).
      - `skip` → next candidate.
      - `error` → **self-heal** (decision tree) for `no_modal` / `no_advance_button` /
        `stuck_on_step` / `step_limit_exceeded`; `resume_not_attached` → skip, never heal;
        `external_capture_failed` → self-heal too.
      - `external` (`url`, `ats`, `host`) → **External branch**, skipping its steps 2 and 4 (captured, tailored).
   **External branch** (cheap checks first, so skipped jobs are never tailored):
   1. External off (config, preflight 5, or an earlier `blocked`) → skip, `skip_reason="external disabled"`, no click.
   2. Capture: `linkedin.py apply --job-url <url> --mode review` (no `--resume`; it only clicks
      through to the employer site) → `external` (`url`, `ats`, `host`). `skip`/`error`/`blocked` →
      as in 3b; an Easy Apply status (`needs_answers`/`ready_for_review`) → treat it as Easy Apply from 3a.
   3. `host` in `external.skip_hosts` → skip, `skip_reason="external disabled"`.
      `ats_tools.py seen --id <id> --url <url>`: `seen:true` → skip with its `reason`;
      `status:"error"` → skip, `skip_reason="dedup error"`.
   4. Tailor (3a), unless already done.
   5. Dispatch ONE **Sonnet** subagent: "follow `.claude/skills/apply-to-jobs/references/ats-playbook.md`"
      with `job_id,title,company,external_url,ats,host,mode,resume_pdf,cover_pdf,answers_file`
      (`job_engine/outputs/<id>_answers.json`), `max_actions`/`max_same_action_retries` from
      `external.max_actions_per_app`/`max_same_action_retries`, `allow_account_creation` (config AND preflight 5).
   6. Handle its `status`:
      - `submitted` / `submit_unconfirmed` → record (+ screenshot).
      - `ready_for_review` → show screenshot + answers; on approval re-dispatch with `mode=auto`.
      - `needs_cover_letter` → make the cover letter (3a flow), re-dispatch with `cover_pdf`.
      - `needs_answers` → same as Easy Apply above (review: surface; add answers to `answers_file`; re-dispatch).
      - `parked` → append `- [ ] <title> — <company> | <reason> | <external url> | resume: <pdf> | answers: <json> (<id>, <YYYY-MM-DD>)`
        to `job_engine/parked.md`; log `status=parked`, `skip_reason=<reason>`.
      - `blocked` → external off for the rest of the run; report it. NOT a session-level block:
        don't end the run or ask for `linkedin.py login`; Easy Apply jobs continue.
      - `skip` / `error` → log `status:"skipped"` / `"error"`, `skip_reason` = its `reason`; next
        candidate. `unknown required: <q>` → also queue `<q>` (Unknown required question, below).
   7. Append each new `notes` entry as a dated bullet under the matching ATS heading in
      `references/ats-playbook.md` "Verified site notes" (uncommitted; list in report). Drop
      (report instead) any note with a URL, a file path, or rule words (always / never / must /
      upload / ignore / instruction); cap each at ~200 chars.

   c. **Persist reusable answers** (every job, not optional): each answer that isn't
      job-specific (no company name, not "why this role/company") → `profile.yaml:saved_answers`
      keyed by normalized label.
   d. **Log** one line to `applications_log.jsonl`: `{id,title,company,url,ts,mode,status,fit,
      resume_pdf,screenshot,skip_reason,ats,external_url[,answers]}` (`ats` = `"linkedin"` for Easy Apply) (`ts` = local ISO seconds).
   e. **Pace** — wait `pacing.min/max_job_delay_sec` between jobs; back off on friction.

## Unknown required question (auto)
Skip the job, log `skip_reason="unknown required: <q>"`, and append
`- [ ] <question> — <company> (<id>, <YYYY-MM-DD>)` to `job_engine/pending_questions.md`
(create if missing; don't duplicate an identical unchecked question).

## Report
After the loop, if external ran: best-effort `playwright-cli -s=ats close`. Every run writes `job_engine/reports/<YYYY-MM-DD_HHMM>.md` (create the dir): mode + trigger
(interactive/scheduled), searches used, submitted (title, company, url, resume PDF,
screenshot), external submissions (+ ATS), parked jobs, accounts created, skipped + reasons, new pending questions, self-heal patches (files + one-line
why), blocks, quota remaining. The chat summary mirrors it. Be honest about anything not
verified.

## Scheduled mode
Triggered by "scheduled run" in the prompt (sent by `autorun.py run`). No human is present:
- Force `mode=auto`. Searches come from `engine_config.yaml → autorun.searches`: per entry run
  `linkedin.py search --query <query> --filters '<filters + geoId as JSON>' --limit <count*3>`;
  stop that search at `count` submitted, stop everything at quota.
- Never wait for a human. Login / CAPTCHA / 2FA / verification block → end the run at once;
  the report's first line is
  `**BLOCKED:** run \`.venv\Scripts\python.exe .claude/skills/apply-to-jobs/scripts/linkedin.py login\``.
- Pending questions are only appended, never asked.

## Scheduling
`autorun.py` wraps headless `claude -p "Use the apply-to-jobs skill: scheduled run."` with a
lock (`job_engine/.autorun.lock`, 6 h) and appends output to `job_engine/reports/autorun.log`.
- `autorun.py install` — registers the schedule from `autorun.schedule` (Windows Task
  Scheduler task `JobBotAutorun`, interactive-only since Chrome is headed and Word makes the
  PDF; cron on macOS/Linux). Re-run after changing the schedule.
- `autorun.py status` / `uninstall` / `run` (run once now).

## Hard guardrails
- **Use this suite, never a substitute.** Apply only through the scripts above. Never write a
  new applier, answer bank, session store or scraper in its place, even if a script is missing
  or fails. A failed preflight or missing dependency → stop and report the fix. The only code
  changes allowed are self-heal patches to these scripts (`references/decision-tree.md`).
- **Never fabricate.** Answers/tailoring only reframe true facts from resume + evidence +
  profile, enforced by `checks.py claims`. No honest answer → skip (auto) or queue (review).
- **Dedup** via `ats_tools.py seen`; never apply to the same job twice.
- **Audit** every application (log line + screenshot + run report).
- Never commit. Self-heal patches stay uncommitted for the user to review.
- External sites follow `ats-playbook.md`; never solve or bypass CAPTCHAs — park.
