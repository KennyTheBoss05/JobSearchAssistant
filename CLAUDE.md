# JobSearchAssistant (branch `JobSearchAssistant` = `main`)

Claude Code skill suite that applies to jobs autonomously: tailors a resume + cover letter per job, answers screening questions from the user's profile, and submits on LinkedIn (Easy Apply). Claude does all reasoning — no app server, no LLM API key.

> The old Streamlit RAG app (JobBot.py) lives on the separate `JobBot` branch. Nothing here depends on it.

## Stack

- **Language:** Python 3.11 (venv at [.venv/](.venv/)) — skill scripts only
- **Browser automation:** Playwright (Chromium, headed)
- **Docs:** `python-docx` (master/tailored resumes), Word COM or LibreOffice for docx → PDF, `pdfplumber` (PDF gate)
- **Config:** PyYAML (`job_engine/engine_config.yaml`, `profile.yaml`)
- **Deps:** [requirements.txt](requirements.txt) — pinned; if a skill script gains an import, add + pin it here.

## Job-application skill suite (project-native, v1)

Three project-local skills automate job applications, reusing JobBot's *thinking* (ported
prompts) but **not its code or OpenAI key** — Claude does all reasoning. Deliberately kept
in this repo (not promoted to the brain). At runtime, data + config live in `job_engine/`
(gitignored). The canonical defaults (config + ported prompts) are bundled in the skill seed
[job_engine_seed/](.claude/skills/job-profile-setup/assets/job_engine_seed/); `job-profile-setup`'s
[bootstrap.py](.claude/skills/job-profile-setup/scripts/bootstrap.py) recreates `job_engine/` from
the seed on first run (never overwriting tuned files), so the suite is self-contained and portable.

- **[job-profile-setup](.claude/skills/job-profile-setup/SKILL.md)** — run once: interview + doc ingestion → `profile.yaml`, `evidence.md`, `.docx` masters, LinkedIn login. Cross-platform.
- **[apply-to-jobs](.claude/skills/apply-to-jobs/SKILL.md)** — autonomous applier (v1 = LinkedIn Easy Apply). Orchestrator drives the browser ([linkedin.py](.claude/skills/apply-to-jobs/scripts/linkedin.py)); subagents (Haiku=scrape, Sonnet=fit/answers, Opus=resume) do text reasoning. `--mode review|auto`. v2 (external ATS + site rotation) pending.
  - **Unattended/scheduled:** auto mode skips + queues unknown questions to `job_engine/pending_questions.md`, self-heals selector drift (≤2 patches/run, uncommitted), writes `job_engine/reports/`. [autorun.py](.claude/skills/apply-to-jobs/scripts/autorun.py) `install|run|status|uninstall` = schtasks/cron → headless `claude -p "...scheduled run."`.
  - **Gates:** [checks.py](.claude/skills/apply-to-jobs/scripts/checks.py) `claims` (token-level grounding vs masters + evidence + profile), `pdf` (page count + contact info), `quota` (`selection.max_per_day`), `selftest`.
- **[tune-job-engine](.claude/skills/tune-job-engine/SKILL.md)** — edit tailoring/answer/selection/pacing behavior via the runtime `job_engine/engine_config.yaml` + `job_engine/prompts/` (defaults: the seed above).

Hard rule across all three: **never fabricate** — tailoring/answers only reframe true facts
from resume + `evidence.md`.

Task backlog: [.jarvis/TASKS.md](.jarvis/TASKS.md).

## Repo-specific notes

- **State on disk.** All personal/runtime data (profile, evidence, masters, outputs, browser profile, LinkedIn creds in `job_engine/.env`) lives in `job_engine/` — gitignored. Never commit it.
- **Remote:** **public** GitHub repo `KennyTheBoss05/JobSearchAssistant`. User-facing setup lives in [README.md](README.md) — keep it in sync when prerequisites change.
- **Shared working copy.** The `JobBot` branch shares this checkout. Its data dirs (`faiss_index_job/`, `Job Text Files/`, `Job PDFs/`, root `.env`) are listed in `.git/info/exclude` (local-only) so they never show as untracked here.

## Environment gotchas

- **Python:** anaconda3 was uninstalled (2026-11). `.venv` is built by **uv** (`~\.local\bin\uv.exe`, CPython 3.11): rebuild with `uv venv --python 3.11 --clear .venv` + `uv pip install --python .venv\Scripts\python.exe -r requirements.txt` + `.venv\Scripts\python.exe -m playwright install chromium`. No Python on PATH — always call `.venv\Scripts\python.exe`.
- **docx → PDF:** use Word COM automation (Word is installed; LibreOffice isn't).
- **PowerShell exec-policy** (`RemoteSigned`) blocks `.ps1` wrappers — if shell-scripting any Node tooling, call `npm.cmd` / `npx.cmd` directly. (Not currently needed — pure Python project.)

## Workflow (from brain)

- **Plan-mode first.** Never edit before there's a plan, even a small one. Clarifying questions are cheaper than retries.
- **Ask until ≥95% confident.** Use `AskUserQuestion`, citing file paths / line numbers so Kevin can answer fast.
- **Self-check baked into the to-do list.** Verify before moving on. For script changes, run `checks.py selftest` at minimum.
- **Be honest about what wasn't tested.** "Can't verify the apply flow without a live LinkedIn session" is acceptable; "looks good" without verification is not.
- **Sub-agents (Haiku)** for read-heavy / scrape / summarize work. Main thread stays on Opus.
- **Communication:** direct, no sycophancy, no trailing summaries when the diff already shows the change.
- **Risk-sensitive actions confirm first** — destructive ops, force-pushes, deleting `job_engine/` data, real (auto-mode) submissions.
- **File references** use markdown link syntax — `[linkedin.py:166](.claude/skills/apply-to-jobs/scripts/linkedin.py#L166)`.

## Tools wired into this repo

Copies of brain assets live in [.claude/](.claude/) (snapshot — re-run `/wire-up` to resync):

- **Agents:** `code-reviewer`, `debugger`, `prompt-engineer`
- **Commands:** `/ultra-think`, `/code-review`, `/init-project`
- **Skills:** `brainstorming`, `skill-creator`, `code-reviewer`, `grill-me`, `handoff`, `pdf-processing` (PDF inputs), `docx` (resume masters)
- **Hooks:** `notify-prompt-finished.ps1` (already wired globally on Kevin's machine; copy here is for teammates)

## Recommended plugins

These three plugins are part of Kevin's default workflow and should be activated in every working repo. Activation is one-time per machine — they persist across sessions once installed.

### On Kevin's machine (run from inside the brain repo)

```
/plugin marketplace add ./plugins/superpowers
/plugin install superpowers@superpowers-dev

/plugin marketplace add ./plugins/claude-mem
/plugin install claude-mem@thedotmack
# After install, run once in PowerShell: npx claude-mem install

/plugin marketplace add ./plugins/context-mode
/plugin install context-mode@context-mode
```

### For teammates (no brain repo)

Clone each plugin's upstream first, then point `/plugin marketplace add` at the local clone path:

- superpowers — https://github.com/obra/superpowers
- claude-mem — https://github.com/thedotmack/claude-mem
- context-mode — https://github.com/mksglu/context-mode

**Caveats:**
- claude-mem needs the extra `npx claude-mem install` step after `/plugin install` — don't skip it.
- Marketplace names (`@superpowers-dev`, `@thedotmack`, `@context-mode`) assume the marketplace folder name matches. If a plugin's `.claude-plugin/marketplace.json` declares a different name, adjust before running.

### Optional plugins

- **gsd** (`/plugin install gsd@gsd-plugin`) — Get-Shit-Done framework: spec-driven, meta-prompting, large per-turn token reduction. Install at local scope (this repo only) if you want it.
