# JobSearchAssistant

Two ways to use it:

1. **Claude Code skills (main path)** — Claude tailors your resume and cover letter per job and applies on LinkedIn (Easy Apply) for you.
2. **JobBot.py (legacy Streamlit app)** — paste a job description, get a tailored resume, cover letter, or answer, grounded in your own PDFs.

## Requirements

- [Claude Code](https://claude.com/claude-code) (for the skills)
- Python 3.11
- A LinkedIn account
- **PDF export of resumes/cover letters:** Microsoft Word (Windows) or [LibreOffice](https://www.libreoffice.org/) (any OS). Used by `.claude/skills/apply-to-jobs/scripts/docx_to_pdf.py`.

## Setup

```bash
python -m venv .venv
# Windows:      .venv\Scripts\python.exe -m pip install -r requirements.txt
# macOS/Linux:  .venv/bin/python -m pip install -r requirements.txt
```

`requirements.txt` covers JobBot.py. The skills' extra deps (Playwright, python-docx, PyYAML, Chromium) are installed by the setup skill.

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

## Using JobBot.py

```bash
cp .env.example .env        # then add your OPENAI_API_KEY
streamlit run JobBot.py     # use the venv's python/streamlit
```

Upload your resume, cover letter, and a writing sample in the sidebar first; they're embedded into a local FAISS index (`faiss_index_job/`, gitignored).
