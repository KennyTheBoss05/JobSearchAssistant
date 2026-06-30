# JobBot — JobSearchAssistant

RAG-based job-application assistant. A Streamlit app that tailors resumes & cover letters and answers job-application Q&A, grounded in the user's own PDFs via a FAISS vector store.

## Stack

- **Language:** Python 3.11 (venv at [.venv/](.venv/))
- **UI:** Streamlit (`streamlit run JobBot.py`)
- **LLM:** OpenAI `gpt-4o` (chat + `text-embedding-3-small`); Google Gemini via `langchain_google_genai` / `google.generativeai`
- **Orchestration:** LangChain (`langchain`, `langchain_community`, `langchain_core`, `langchain_openai`)
- **Vector store:** FAISS (`faiss-cpu`), persisted to [faiss_index_job/](faiss_index_job/)
- **PDF parsing:** `pdfplumber` (primary), `PyPDF2`
- **Entry point:** [JobBot.py](JobBot.py)

## Repo-specific notes

- **Single-file app.** All logic lives in [JobBot.py](JobBot.py) — no module split yet.
- **State on disk, not in DB.** Uploaded context is parsed to `resume_text.txt`, `cl_text.txt`, `english_style.txt`, and embedded into `faiss_index_job/`. The app reads these on launch.
- **Secrets via `.env`.** `OPENAI_API_KEY` is loaded with `python-dotenv`. The "Ask" flow fails silently / errors without it. Never commit `.env`.
- **`requirements.txt` is pruned** to exactly what `JobBot.py` imports (plus `faiss-cpu` as the FAISS backend). Transitive deps resolve via pip. If you add an import, add the top-level package here and pin it.
- **Not a git repo yet.** No remote; `gh` workflows don't apply until one is initialized.

## Environment gotchas

- **Python** via `anaconda3` (`C:\Users\Kevin\anaconda3\python.exe`) — pip works. This repo has its own venv; activate/use `.venv\Scripts\python.exe` for isolation.
- **PowerShell exec-policy** (`RemoteSigned`) blocks `.ps1` wrappers — if shell-scripting any Node tooling, call `npm.cmd` / `npx.cmd` directly. (Not currently needed — pure Python project.)

## Workflow (from brain)

- **Plan-mode first.** Never edit before there's a plan, even a small one. Clarifying questions are cheaper than retries.
- **Ask until ≥95% confident.** Use `AskUserQuestion`, citing file paths / line numbers so Kevin can answer fast.
- **Self-check baked into the to-do list.** Verify before moving on. For UI changes, launch `streamlit run JobBot.py` and click through; refresh-on-save is automatic.
- **Be honest about what wasn't tested.** "Can't verify the RAG output without an API key + uploaded PDFs" is acceptable; "looks good" without verification is not.
- **Sub-agents (Haiku)** for read-heavy / scrape / summarize work. Main thread stays on Opus.
- **Communication:** direct, no sycophancy, no trailing summaries when the diff already shows the change.
- **Risk-sensitive actions confirm first** — destructive ops, force-pushes, deleting the FAISS index or the `*_text.txt` state files.
- **File references** use markdown link syntax — `[JobBot.py:345](JobBot.py#L345)`.

## Python-LLM specifics

- **Pin provider SDK versions** in `requirements.txt` (already done for `openai`, `langchain_*`, `google.generativeai`) — LangChain breaks across minor versions.
- **RAG hygiene:** keep the vector store (`faiss_index_job/`) separate from source documents. Gitignore the indexed data and the generated `*_text.txt` state if a git repo is initialized.
- Tunable globals live near the bottom of [JobBot.py](JobBot.py) (`Model`, `temperature0/1`, `score_threshold0/1`, `k`, `chunk_size`, `chunk_overlap`, `max_tokens`).

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
- **[tune-job-engine](.claude/skills/tune-job-engine/SKILL.md)** — edit tailoring/answer/selection/pacing behavior via the runtime `job_engine/engine_config.yaml` + `job_engine/prompts/` (defaults: the seed above).

Hard rule across all three: **never fabricate** — tailoring/answers only reframe true facts
from resume + `evidence.md`. Runtime deps (`playwright`, `python-docx`) install during setup.

## Tools wired into this repo

Copies of brain assets live in [.claude/](.claude/) (snapshot — re-run `/wire-up` to resync):

- **Agents:** `code-reviewer`, `debugger`, `prompt-engineer`
- **Commands:** `/ultra-think`, `/code-review`, `/init-project`
- **Skills:** `brainstorming`, `skill-creator`, `code-reviewer`, `grill-me`, `handoff`, `pdf-processing` (PDF inputs), `docx` (Projects.docx)
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
