---
name: job-profile-setup
description: >-
  One-time (or occasional) setup that builds the candidate's job-application profile
  for the apply-to-jobs skill. Use this whenever the user wants to set up, configure,
  re-run, or update their job-application data — collecting personal/structured fields
  (work authorization, salary, notice period, years-per-skill, links, demographics),
  ingesting their resume / cover letter / writing-sample / supporting documents, building
  the editable .docx master resume, distilling a grounding "evidence" file, and capturing
  their LinkedIn login. ALWAYS use this before apply-to-jobs if job_engine/profile.yaml,
  evidence.md, or the master resume are missing. Trigger on phrases like "set up my job
  bot", "configure job applications", "onboard my resume", "update my job profile",
  "I want to start applying for jobs". Cross-platform (Windows/macOS/Linux).
---

# Job profile setup

Builds everything `apply-to-jobs` needs, in `job_engine/` at the repo root. Inspired by
`JobBot.py`'s inputs but **does not run JobBot or use its OpenAI key** — all reasoning is
done by you (Claude). Re-running is safe and idempotent: only update what's changed; never
clobber existing data without confirming.

## What you produce
| Output | Source |
|---|---|
| `job_engine/profile.yaml` | guided interview (structured fields) |
| `job_engine/evidence.md` | distilled TRUE achievements/skills from context docs |
| `job_engine/writing_style.md` | the user's writing sample (JobBot input 3) |
| `job_engine/masters/resume_base.docx` (+ `cover_letter_base.docx`) | provided .docx, or rebuilt from PDF |
| `job_engine/browser_profile/` | persistent LinkedIn session |
| `job_engine/.env` | LinkedIn creds (optional fallback) |

## Steps

### 1. Bootstrap job_engine/, then check state
`job_engine/` is gitignored runtime data and may not exist yet (fresh clone / new machine).
First recreate it from the skill's bundled defaults — this is safe to run anytime and
**never overwrites** an existing file (a tuned config or edited prompt is preserved):
`python .claude/skills/job-profile-setup/scripts/bootstrap.py`
It copies the seed (`engine_config.yaml`, `prompts/*.md`, `profile.example.yaml`, `README.md`)
into `job_engine/` and creates the runtime subdirs (`masters/`, `outputs/`, `screenshots/`,
`browser_profile/`). Then read what already exists, tell the user what's present, and ask which
parts they want to (re)do. If only the seeded files are present, this is a first run.

### 2. Ensure dependencies (cross-platform)
`apply-to-jobs` needs Playwright. Detect the interpreter (prefer `.venv`), then:
`python -m pip install playwright pyyaml python-docx && python -m playwright install chromium`.
On Windows call the venv python directly (`.venv\Scripts\python.exe`) to avoid the PowerShell
`.ps1` execution-policy block. Resume PDFs are rendered by `apply-to-jobs/scripts/docx_to_pdf.py`,
which needs **Microsoft Word (Windows) or LibreOffice** — check one is present and, if not, tell
the user to install LibreOffice before they try to apply. The **pdf-processing** and **docx** skills are wired into this
repo — use them for PDF text extraction and .docx work rather than hand-rolling parsers.

### 3. Guided interview → profile.yaml
Interview the user for every field in `profile.example.yaml`. Ask in small batches, citing
why each matters for applications. **Demographics are optional and explicitly skippable.**
Critical fields that unblock the most jobs: work authorization, sponsorship need, target
locations, work modes, desired salary, total years + years-per-key-skill. Write
`profile.yaml` (gitignored) — never put real personal data in `profile.example.yaml`.

### 4. Ingest documents
Ask for the resume, cover letter, writing-style sample, and any supporting/context docs
(old resumes, transcripts, project write-ups). Extract text with the pdf-processing skill.
- Save the writing sample → `writing_style.md`.
- The resume/cover-letter text seed the masters (step 5).

### 5. Build the .docx masters
The applier tailors a **.docx master** per job and exports a PDF (clean uploads).
- If the user has an editable `.docx` resume, copy it to `masters/resume_base.docx`.
- If they only have a PDF, reconstruct a clean `.docx` once using the **docx** skill,
  preserving section order (Summary, Skills, Areas of Interest, Highlight Projects,
  Experience, Certifications — matching the structure JobBot's prompt expects). Show the
  user the rebuilt resume and confirm fidelity before saving.
- Same for the cover letter → `masters/cover_letter_base.docx`.

### 6. Distill evidence.md (the grounding file — most important)
Read ALL the context docs and the resume, and write `evidence.md`: a structured, factual
inventory of the user's **real** achievements, skills (with rough years), metrics, tools,
projects, employers, and education. This is the ONLY source the tailoring step may draw new
material from, so it enforces the anti-fabrication rule (`grounding.strict`). Include only
things actually supported by the documents. When unsure whether something is true, ask the
user rather than guessing. Organize by theme (Skills | Projects | Experience | Education |
Certifications | Metrics) so the tailoring subagent can scan it fast.

### 7. Capture LinkedIn login
Run the driver's login command so the user signs in once into the persistent profile:
`python .claude/skills/apply-to-jobs/scripts/linkedin.py login`
A headed Chrome opens; the user logs in and clears any CAPTCHA/2FA themselves. Optionally
offer to store credentials in `job_engine/.env` (`LINKEDIN_EMAIL=`, `LINKEDIN_PASSWORD=`) as a
re-login fallback — explain it's plaintext on disk and that the persistent session usually
makes it unnecessary. Confirm with `... linkedin.py check` → `{"logged_in": true}`.

### 8. Confirm
Summarize what was created and tell the user they can now run `apply-to-jobs`, and
`tune-job-engine` if they want to adjust tailoring behavior.

## Guardrails
- Never write fabricated content into `evidence.md` or the masters. Ask when unsure.
- Personal data stays in gitignored paths (see `job_engine/README.md`).
- This skill and its data are intentionally project-local (not promoted to the brain repo).
