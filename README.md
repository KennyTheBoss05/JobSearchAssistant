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

Hard rule: the skills never invent experience. Tailoring and answers only reframe facts from your resume and the evidence file built during setup.

## Using JobBot.py

```bash
cp .env.example .env        # then add your OPENAI_API_KEY
streamlit run JobBot.py     # use the venv's python/streamlit
```

Upload your resume, cover letter, and a writing sample in the sidebar first; they're embedded into a local FAISS index (`faiss_index_job/`, gitignored).
