---
name: apply-to-jobs
description: >-
  Autonomously applies to jobs end-to-end on LinkedIn (v1: Easy Apply), tailoring a resume
  and cover letter per job and answering screening questions from the user's pre-built
  profile — running start-to-finish without stopping unless it hits something only the user
  can resolve (CAPTCHA/2FA/expired login) or a required question it genuinely can't answer
  honestly. Use whenever the user wants to apply for jobs, e.g. "apply to 5 data scientist
  jobs on LinkedIn", "go apply for some ML engineer roles in London under £90k", "apply to
  this job: <url>", "find and apply to remote python jobs for me". Supports a full-auto
  (submit) vs review (stop before submit) mode toggle. Requires job-profile-setup to have
  run first. Reads all tunable behavior from job_engine/engine_config.yaml.
---

# Apply to jobs (v1 — LinkedIn Easy Apply)

You orchestrate an autonomous application run. You (main thread, Opus) own the single
browser and do all clicking via the driver script; **subagents do pure text reasoning**
(scrape, score, tailor, answer) and return strings — they cannot drive the browser.

Read `references/easy-apply-playbook.md` for the modal walk-through and selector notes, and
`references/decision-tree.md` for the exact skip-vs-ask-vs-fabricate rules. Read them before
your first application in a run.

Driver: `python .claude/skills/apply-to-jobs/scripts/linkedin.py <check|search|apply>`
(detect the venv interpreter; on Windows use `.venv\Scripts\python.exe`).

## Parse the request
Extract: role/keywords, count **N**, location, work mode (remote/hybrid/onsite), salary,
experience level, company names, date-posted, and/or direct job URLs. Mode defaults to
**review** unless the user says full-auto / "just apply" / "don't stop". If direct URLs are
given, skip search and go straight to those.

## Preflight
1. Confirm `job_engine/profile.yaml`, `evidence.md`, and `masters/resume_base.docx` exist.
   If not, stop and tell the user to run **job-profile-setup**.
2. `linkedin.py check`. If `logged_in:false` → run `linkedin.py login`, fire a desktop
   notification, and wait (session-level block; see decision tree). Don't proceed blind.

## The loop (until N submitted or candidates exhausted)
1. **Search** — subagent (**Haiku**): run `linkedin.py search` with the filters, get
   candidate listings. Drop any job `id` already in `applications_log.jsonl` (dedup).
2. **Fit-score** — subagent (**Sonnet**): apply `job_engine/prompts/fit_score.md` against
   `profile.yaml` + `evidence.md`. Drop jobs below `selection.fit_floor` (log the rationale).
   Order best-first if `selection.rank_by_fit`.
3. **For each candidate, best first:**
   a. **Tailor resume** — subagent (**Opus**): apply `prompts/resume_tailor.md` grounded in
      `evidence.md` + the live docs. Take its change table, apply it to a copy of
      `masters/resume_base.docx` (docx skill), saved as `job_engine/outputs/<id>.docx`. Convert
      with `python .claude/skills/apply-to-jobs/scripts/docx_to_pdf.py job_engine/outputs/<id>.docx
      "job_engine/outputs/<Full Name> Resume - <Company>.pdf"` (recruiters see the file name).
      It prints `{"status":"ok","pdf":...}`; on `"status":"error"` (no Word/LibreOffice) stop the
      run and tell the user what to install — never upload the .docx instead.
   b. **Tailor cover letter** — only if the form offers a slot (and `cover_letter.attach_only_if_slot`):
      subagent applies `prompts/cover_letter.md`, then the same `docx_to_pdf.py` →
      `<Full Name> Cover Letter - <Company>.pdf`.
   c. **Drive the application** — call `linkedin.py apply --job-url <url> --resume <pdf>
      --answers <answers.json> --mode <mode>`. The driver fills everything it can and:
        - returns `needs_answers` → for each question, answer with a subagent (**Sonnet**)
          using `prompts/qa_answer.md` grounded in evidence. If the answer is `CANNOT_ANSWER`,
          follow the decision tree (skip in auto / queue in review). Append answerable ones to
          `answers.json` and re-invoke `apply`. Save reusable answers back to
          `profile.yaml:saved_answers`.
        - returns `submitted` → record success (+ screenshot path).
        - returns `ready_for_review` → present the summary + screenshot to the user; on
          approval re-run with `--mode auto`.
        - returns `blocked`/`not_logged_in` → notify + pause (session-level).
        - returns `skip`/`no_easy_apply`/disqualified → move to the next candidate.
   d. **Log** one JSON line to `applications_log.jsonl`: `{id,title,company,url,ts,mode,
      status,fit,resume_pdf,screenshot,skip_reason}`.
   e. **Pace** — the driver already inserts human-like delays; additionally wait
      `pacing.min/max_job_delay_sec` between jobs. Back off on any friction signal.

## Report
Summarize: N submitted, which were skipped (with reasons), any blocked, and paths to the
tailored PDFs + confirmation screenshots. Be honest about anything not verified.

## Hard guardrails
- **Never fabricate.** Answers/tailoring only reframe true facts from resume + evidence.
  A required field with no honest answer → skip (auto) or queue (review), never invent.
- **Dedup** against the log; never apply to the same job twice.
- **Audit** every application (log line + screenshot).
- This is LinkedIn Easy Apply only. External-ATS redirects are v2 — skip them in v1.
