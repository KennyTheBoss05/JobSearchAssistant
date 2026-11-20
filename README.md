# JobSearchAssistant

Claude Code skills that tailor your resume and cover letter per job and apply on LinkedIn (Easy Apply) and on employer sites for you.

> The older Streamlit RAG app (JobBot.py) lives on the `JobBot` branch.

## Requirements

- [Claude Code](https://claude.com/claude-code)
- Python 3.11
- A LinkedIn account
- **External applications:** Node.js and `npm install -g @playwright/cli@0.1.23` (Windows PowerShell: `npm.cmd`).
- **PDF export of resumes/cover letters:** Microsoft Word (Windows) or [LibreOffice](https://www.libreoffice.org/) (any OS; **required on macOS**, e.g. `brew install --cask libreoffice`). Used by `.claude/skills/apply-to-jobs/scripts/docx_to_pdf.py`.

## Setup

**Use this repo as its own project.** Clone it into its own folder and open *that* folder in Claude Code (`cd JobSearchAssistant && claude`, or VS Code → File → Open Folder). Don't copy `.claude/` into another project or open a parent folder: Claude then follows that project's instructions instead of these skills, and the scripts can't find their files.

```bash
git clone https://github.com/KennyTheBoss05/JobSearchAssistant.git
cd JobSearchAssistant
python3.11 -m venv .venv          # Windows: py -3.11 -m venv .venv
# Windows:      .venv\Scripts\python.exe -m pip install -r requirements.txt
# macOS/Linux:  .venv/bin/python -m pip install -r requirements.txt
# then:         <venv python> -m playwright install chromium
<venv python> .claude/skills/apply-to-jobs/scripts/checks.py doctor   # must print "status": "ok"
```

`doctor` checks the repo layout, Python 3.11, the pinned package versions, Chromium, Word/LibreOffice and (optionally) `playwright-cli`, and prints the fix for anything missing. Both the setup and apply skills run it first and stop if it fails.

## Using the skills

Open the repo in Claude Code, then:

1. **Set up your profile (once):** say *"set up my job bot"*. This runs `job-profile-setup`: it interviews you, ingests your resume/cover letter/writing sample, builds the master `.docx` resume, and captures your LinkedIn login. Everything it writes goes to `job_engine/`, which is gitignored — your data never gets committed.
2. **Apply:** e.g. *"apply to 5 data scientist jobs on LinkedIn, review mode"*. `review` stops before each submit; `auto` submits.
3. **Tune behavior (optional):** e.g. *"make my answers more formal"* or *"be pickier about which jobs to apply to"*. This runs `tune-job-engine`.

Hard rule: the skills never invent experience. Tailoring and answers only reframe facts from your resume and the evidence file built during setup. `checks.py` enforces it: tailored documents and free-text answers with numbers, tools or names not found in your documents are revised or the job is skipped.

### External applications

Jobs without Easy Apply are applied for on the employer's site (Greenhouse, Lever, Ashby, Workday, custom pages) by a Claude subagent driving `playwright-cli`. Capturing the external link continues past LinkedIn's "Share your profile?" prompt, switching its share toggle off when one is shown. If `playwright-cli` isn't installed, external applications are turned off for that run. Expect roughly 5-10 minutes and noticeably more Claude usage per external application. Config: `external:` in `job_engine/engine_config.yaml`.

- **Parked jobs:** CAPTCHAs, SMS codes, ID upload, video interviews and assessments are never bypassed. Those jobs go to `job_engine/parked.md`; the next interactive run offers to finish them while you clear the gate (and click Submit if the CAPTCHA sits on the final page).
- **Accounts:** sites that need one get an account (credentials in `job_engine/accounts.json`). Verification emails are read from Gmail: create a Google app password (2-Step Verification on, then myaccount.google.com/apppasswords) and add `GMAIL_ADDRESS` (same as your profile email) and `GMAIL_APP_PASSWORD` to `job_engine/.env`. Check with `ats_tools.py inbox --check`. Without it, those jobs are parked.

### Unattended / scheduled runs

- **Walk away:** *"apply to 15 AI engineer jobs, auto"*. Questions only you can answer are queued in `job_engine/pending_questions.md` (the job is skipped); the next interactive run asks them in one batch and saves your answers for reuse. Each run writes a report to `job_engine/reports/`.
- **On a schedule:** set searches, time and days under `autorun:` in `job_engine/engine_config.yaml`, then run `python .claude/skills/apply-to-jobs/scripts/autorun.py install` (Windows Task Scheduler or cron; `status` / `uninstall` / `run` also available). You must be logged in to your computer at the scheduled time (the browser is visible and Word exports the PDF). If LinkedIn needs a fresh login, the run stops and the report says so.
- `selection.max_per_day` (default 30) caps submitted applications per day across all runs.
