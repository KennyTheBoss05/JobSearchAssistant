# JobBot

A Streamlit app: paste a job description, get a tailored resume, cover letter, or application answer, grounded in your own PDFs.

> The Claude Code job-applying skills live on the `JobSearchAssistant` branch (also `main`).

## Requirements

- Python 3.11
- An OpenAI API key

## Setup

```bash
python -m venv .venv
# Windows:      .venv\Scripts\python.exe -m pip install -r requirements.txt
# macOS/Linux:  .venv/bin/python -m pip install -r requirements.txt
cp .env.example .env        # then add your OPENAI_API_KEY
```

## Run

```bash
streamlit run JobBot.py     # use the venv's python/streamlit
```

Upload your resume, cover letter, and a writing sample in the sidebar first; they're embedded into a local FAISS index (`faiss_index_job/`, gitignored).
