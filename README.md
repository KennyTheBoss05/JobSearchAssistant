# JobSearchAssistant

Claude Code skills that tailor your resume and cover letter per job and apply on LinkedIn (Easy Apply) for you.

> The older Streamlit RAG app (JobBot.py) lives on the `JobBot` branch.

## Requirements

- [Claude Code](https://claude.com/claude-code)
- Python 3.11
- A LinkedIn account
- **PDF export of resumes/cover letters:** Microsoft Word (Windows) or [LibreOffice](https://www.libreoffice.org/) (any OS). Used by `.claude/skills/apply-to-jobs/scripts/docx_to_pdf.py`.

## Setup

```bash
python -m venv .venv
# Windows:      .venv\Scripts\python.exe -m pip install -r requirements.txt
# macOS/Linux:  .venv/bin/python -m pip install -r requirements.txt
# then:         <venv python> -m playwright install chromium
```

The setup skill also runs these if you skip them.

## Using the skills

Open the repo in Claude Code, then:

1. **Set up your profile (once):** say *"set up my job bot"*. This runs `job-profile-setup`: it interviews you, ingests your resume/cover letter/writing sample, builds the master `.docx` resume, and captures your LinkedIn login. Everything it writes goes to `job_engine/`, which is gitignored — your data never gets committed.
2. **Apply:** e.g. *"apply to 5 data scientist jobs on LinkedIn, review mode"*. `review` stops before each submit; `auto` submits.
3. **Tune behavior (optional):** e.g. *"make my answers more formal"* or *"be pickier about which jobs to apply to"*. This runs `tune-job-engine`.

Hard rule: the skills never invent experience. Tailoring and answers only reframe facts from your resume and the evidence file built during setup. `checks.py` enforces it: tailored documents and free-text answers with numbers, tools or names not found in your documents are revised or the job is skipped.

### Unattended / scheduled runs

- **Walk away:** *"apply to 15 AI engineer jobs, auto"*. Questions only you can answer are queued in `job_engine/pending_questions.md` (the job is skipped); the next interactive run asks them in one batch and saves your answers for reuse. Each run writes a report to `job_engine/reports/`.
- **On a schedule:** set searches, time and days under `autorun:` in `job_engine/engine_config.yaml`, then run `python .claude/skills/apply-to-jobs/scripts/autorun.py install` (Windows Task Scheduler or cron; `status` / `uninstall` / `run` also available). You must be logged in to your computer at the scheduled time (the browser is visible and Word exports the PDF). If LinkedIn needs a fresh login, the run stops and the report says so.
- `selection.max_per_day` (default 30) caps submitted applications per day across all runs.
