# JobBot (branch `JobBot`)

RAG-based job-application assistant. A Streamlit app that tailors resumes & cover letters and answers job-application Q&A, grounded in the user's own PDFs via a FAISS vector store.

> This branch holds **only** JobBot.py and what it needs. The Claude Code job-applying skill suite lives on the `JobSearchAssistant` branch (= `main`) and has no dependency on JobBot.py.

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
- **State on disk, not in DB.** Uploaded context is parsed to `Job Text Files/` (`resume_text.txt`, `cl_text.txt`, `english_style.txt`) and embedded into `faiss_index_job/`. The app reads these on launch.
- **Secrets via `.env`.** `OPENAI_API_KEY` is loaded with `python-dotenv` (template: [.env.example](.env.example)). The "Ask" flow fails silently / errors without it. Never commit `.env`.
- **`requirements.txt` is pruned** to exactly what `JobBot.py` imports (plus `faiss-cpu` as the FAISS backend). Transitive deps resolve via pip. If you add an import, add the top-level package here and pin it.
- **Remote:** **public** GitHub repo `KennyTheBoss05/JobSearchAssistant`, branch `JobBot`. User-facing setup lives in [README.md](README.md) — keep it in sync when prerequisites change.

## Environment gotchas

- **Python:** anaconda3 was uninstalled (2026-11). `.venv` is built by **uv** (`~\.local\bin\uv.exe`, CPython 3.11): rebuild with `uv venv --python 3.11 --clear .venv` + `uv pip install --python .venv\Scripts\python.exe -r requirements.txt`. No Python on PATH — always call `.venv\Scripts\python.exe`.
- **Shared working copy.** Both branches share one checkout, so `.venv` may also hold the JobSearchAssistant deps — harmless. Personal data dirs of both branches are listed in `.git/info/exclude` (local-only) so neither branch shows the other's data as untracked.

## Workflow (from brain)

- **Plan-mode first.** Never edit before there's a plan, even a small one. Clarifying questions are cheaper than retries.
- **Ask until ≥95% confident.** Use `AskUserQuestion`, citing file paths / line numbers so Kevin can answer fast.
- **Self-check baked into the to-do list.** Verify before moving on. For UI changes, launch `streamlit run JobBot.py` and click through; refresh-on-save is automatic.
- **Be honest about what wasn't tested.** "Can't verify the RAG output without an API key + uploaded PDFs" is acceptable; "looks good" without verification is not.
- **Sub-agents (Haiku)** for read-heavy / scrape / summarize work. Main thread stays on Opus.
- **Communication:** direct, no sycophancy, no trailing summaries when the diff already shows the change.
- **Risk-sensitive actions confirm first** — destructive ops, force-pushes, deleting the FAISS index or the `Job Text Files/` state.
- **File references** use markdown link syntax — `[JobBot.py:345](JobBot.py#L345)`.

## Python-LLM specifics

- **Pin provider SDK versions** in `requirements.txt` (already done for `openai`, `langchain_*`, `google.generativeai`) — LangChain breaks across minor versions.
- **RAG hygiene:** keep the vector store (`faiss_index_job/`) separate from source documents. The indexed data and generated `Job Text Files/` state are gitignored.
- Tunable globals live near the bottom of [JobBot.py](JobBot.py) (`Model`, `temperature0/1`, `score_threshold0/1`, `k`, `chunk_size`, `chunk_overlap`, `max_tokens`).

## Tools wired into this repo

Copies of brain assets live in [.claude/](.claude/) (snapshot — re-run `/wire-up` to resync):

- **Agents:** `code-reviewer`, `debugger`, `prompt-engineer`
- **Commands:** `/ultra-think`, `/code-review`, `/init-project`
- **Skills:** `brainstorming`, `grill-me`, `handoff`
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
