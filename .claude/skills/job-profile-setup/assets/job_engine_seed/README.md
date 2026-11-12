# job_engine/ — data + config for the job-application skill suite

This directory is the shared state for three skills (in `.claude/skills/`):
`job-profile-setup`, `apply-to-jobs`, `tune-job-engine`. It is the runtime home
of your personal application data and the tunable "thinking" ported from
`JobBot.py` (we reuse JobBot's *logic*, not its code or OpenAI key).

## Layout

This whole folder is **gitignored** — it's runtime + personal data. The canonical defaults
(config + ported prompts + this README) are bundled in the skill seed at
`.claude/skills/job-profile-setup/assets/job_engine_seed/` and copied here by `bootstrap.py`
on first run (never overwriting files you've tuned).

| Path | Origin | What it is |
|---|---|---|
| `engine_config.yaml` | seed → tunable | Knobs: selection (incl. daily cap), pacing, answer tone, resume/CL rules, grounding, autorun schedule. Edited by `tune-job-engine`. |
| `prompts/*.md` | seed → tunable | Tailoring/answer prompts ported from JobBot. Edited by `tune-job-engine`. |
| `profile.example.yaml` | seed | Template for the structured profile. |
| `profile.yaml` | built by setup | Your real structured profile. |
| `evidence.md` | built by setup | Distilled TRUE achievements/skills — the grounding source for tailoring. |
| `writing_style.md` | built by setup | A sample of how you write (JobBot input 3). |
| `masters/*.docx` | built by setup | Editable master resume + cover letter, tailored per job. |
| `outputs/` | runtime | Per-job tailored resume/CL PDFs. |
| `screenshots/` | runtime | Submission confirmation screenshots (audit) + `<id>_error.{png,html}` driver-error captures. |
| `applications_log.jsonl` | runtime | One line per application: dedup + audit. |
| `pending_questions.md` | runtime | Questions only you can answer, queued by auto runs; answered at the next interactive run into `profile.yaml:saved_answers`. |
| `reports/` | runtime | One report per run + `autorun.log` (scheduled runs). |
| `.autorun.lock` | runtime | Present while a scheduled run is active. |
| `browser_profile/` | runtime | Persistent Playwright Chrome profile (your LinkedIn session). |
| `.env` | optional | LinkedIn credentials (re-login fallback only). |

## Anti-fabrication

`grounding.strict: true` in `engine_config.yaml` is a hard rule honored by every
prompt: tailoring and answers may only reframe TRUE facts present in your resume +
`evidence.md`. Nothing is ever invented. If a required field can't be answered
honestly, the applier skips that job (full-auto) or queues it (review) — it never
makes something up.

## First run

Run the `job-profile-setup` skill. It interviews you, ingests your resume / cover
letter / writing sample / context docs, builds `profile.yaml`, `evidence.md`, the
`.docx` masters, and captures your LinkedIn login into `browser_profile/`.
