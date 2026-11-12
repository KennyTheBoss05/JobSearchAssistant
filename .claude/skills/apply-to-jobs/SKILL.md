---
name: apply-to-jobs
description: >-
  Autonomously applies to jobs end-to-end on LinkedIn (v1: Easy Apply), tailoring a resume
  and cover letter per job and answering screening questions from the user's pre-built
  profile — running start-to-finish without stopping unless it hits something only the user
  can resolve (CAPTCHA/2FA/expired login), interactively or on a schedule with no user
  present. Use whenever the user wants to apply for jobs, e.g. "apply to 5 data scientist
  jobs on LinkedIn", "go apply for some ML engineer roles in London under £90k", "apply to
  this job: <url>", "apply to 15 AI engineer jobs, auto", or when a prompt says "scheduled
  run". Supports a full-auto (submit) vs review (stop before submit) mode toggle. Requires
  job-profile-setup to have run first. Reads all tunable behavior from
  job_engine/engine_config.yaml.
---

# Apply to jobs (v1 — LinkedIn Easy Apply)

You orchestrate an application run. You (main thread, Opus) own the single browser and do
all clicking via the driver; **subagents do text/document work** and return small JSON —
they never drive the browser. Keep the main thread lean: it never sees change tables or
document text.

Read `references/easy-apply-playbook.md` (driver contract, UI notes) and
`references/decision-tree.md` (skip / queue / pause / self-heal rules) before the first
application in a run.

Scripts (in `.claude/skills/apply-to-jobs/scripts/`; on Windows run with `.venv\Scripts\python.exe`):
- `linkedin.py <check|login|search|apply>` — browser driver.
- `checks.py <claims|pdf|quota>` — deterministic gates (grounding, PDF sanity, daily cap).
- `docx_to_pdf.py <docx> <pdf>` — Word COM / LibreOffice export.
- `autorun.py <run|install|uninstall|status>` — scheduler (see Scheduling).

## Parse the request
Extract: role/keywords, count **N**, location (`geoId` in filters; UK = 101165590), work
mode, salary, experience level, companies, date-posted, and/or direct job URLs. Mode
defaults to **review** unless the user says auto / full-auto / "just apply" / "don't stop".
A prompt containing "scheduled run" → **Scheduled mode** (below).

## Preflight
1. `job_engine/profile.yaml`, `evidence.md`, `masters/resume_base.docx` exist — else stop and
   tell the user to run **job-profile-setup**.
2. `checks.py quota` — if `remaining == 0`, report and stop.
3. **Pending questions (interactive only):** if `job_engine/pending_questions.md` has unchecked
   `- [ ]` items, ask the user all of them in one batch first. Write each answer to
   `profile.yaml:saved_answers` (key = normalized question: lowercase, collapsed whitespace)
   and tick the item `- [x]`.
4. `linkedin.py check`. If `logged_in:false` → interactive: run `linkedin.py login`, notify,
   wait. Scheduled: end the run (see Scheduled mode).

## The loop (until N submitted, candidates exhausted, or quota hit)
1. **Search** — subagent (**Haiku**): `linkedin.py search --query … --filters '<json>' --limit …`.
   **Dedup:** drop ids whose *latest* log line is `submitted`/`submit_unconfirmed`, or whose
   `skip_reason` starts with `disqualified` or `fit`. A job skipped with
   `unknown required: <q>` is eligible again once `<q>` is in `saved_answers`.
2. **Fit-score** — subagent (**Sonnet**): `prompts/fit_score.md` vs profile + evidence. Below
   `selection.fit_floor` → log `skip_reason="fit: <score> <why>"`. Rank best-first if
   `selection.rank_by_fit`.
3. **For each candidate, best first** — `checks.py quota` first; stop when `remaining` is 0.
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
        `stuck_on_step` / `step_limit_exceeded`; `resume_not_attached` → skip, never heal.
   c. **Persist reusable answers** (every job, not optional): each answer that isn't
      job-specific (no company name, not "why this role/company") → `profile.yaml:saved_answers`
      keyed by normalized label.
   d. **Log** one line to `applications_log.jsonl`: `{id,title,company,url,ts,mode,status,fit,
      resume_pdf,screenshot,skip_reason[,answers]}` (`ts` = local ISO seconds).
   e. **Pace** — wait `pacing.min/max_job_delay_sec` between jobs; back off on friction.

## Unknown required question (auto)
Skip the job, log `skip_reason="unknown required: <q>"`, and append
`- [ ] <question> — <company> (<id>, <YYYY-MM-DD>)` to `job_engine/pending_questions.md`
(create if missing; don't duplicate an identical unchecked question).

## Report
Every run writes `job_engine/reports/<YYYY-MM-DD_HHMM>.md` (create the dir): mode + trigger
(interactive/scheduled), searches used, submitted (title, company, url, resume PDF,
screenshot), skipped + reasons, new pending questions, self-heal patches (files + one-line
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
- **Never fabricate.** Answers/tailoring only reframe true facts from resume + evidence +
  profile, enforced by `checks.py claims`. No honest answer → skip (auto) or queue (review).
- **Dedup** per the rule above; never apply to the same job twice.
- **Audit** every application (log line + screenshot + run report).
- Never commit. Self-heal patches stay uncommitted for the user to review.
- LinkedIn Easy Apply only. External-ATS redirects are v2 — skip them.
