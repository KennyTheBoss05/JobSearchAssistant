# 001 — Build tailored resume PDF export pipeline

Status: queued
Lane: chat
Created: 2026-08-17
Priority: P1

## The ask

In this repo the `apply-to-jobs` skill tells the orchestrator to tailor
`job_engine/masters/resume_base.docx` per job and "export a PDF to `job_engine/outputs/<id>.pdf`",
but nothing implements that step and no docx→PDF converter is installed (checked: `docx2pdf`,
`reportlab`, LibreOffice all absent; `python-docx` is present in `.venv`).

Write a small script under `.claude/skills/apply-to-jobs/scripts/` that takes the base `.docx` plus a
structured change set (section → replacement text/bullets), applies it to a *copy* with
`python-docx`, and renders a PDF — picking a converter that actually works on this Windows machine
and degrading gracefully if it is unavailable. Then update
`.claude/skills/apply-to-jobs/SKILL.md` step 3a/3b to call the script instead of describing the work
in prose, and add the converter to the dependency list in
`.claude/skills/job-profile-setup/SKILL.md` step 2. Prove it by producing one real tailored PDF from
the existing master into `job_engine/outputs/`.

## Acceptance criteria

- [ ] A script exists that converts `masters/resume_base.docx` + a change set into a valid PDF in
      `job_engine/outputs/`, run once for real and the output opened/verified.
- [ ] Formatting of the master (sections, fonts, page count target from `resume.pages`) survives the
      round-trip — confirm visually, don't assume.
- [ ] Missing-converter case returns a clear JSON error the orchestrator can act on, not a traceback.
- [ ] `apply-to-jobs` SKILL.md no longer instructs the model to hand-roll the docx/PDF step.

## Out of scope

- Cover-letter-specific formatting beyond reusing the same script path.
- Changing the tailoring prompts themselves.

## Progress — 2026-11-12

Converter question answered: **Microsoft Word is installed** (LibreOffice is not). Word COM
automation produced 4 real tailored PDFs in `job_engine/outputs/` during task 002's live run, and
the resume LinkedIn received was text-identical to the tailored PDF. The ad-hoc script lived in a
temp dir — reproduced here so it isn't lost:

```powershell
param([string[]]$Paths)
$w = New-Object -ComObject Word.Application; $w.Visible = $false
try { foreach ($p in $Paths) { $d = $w.Documents.Open($p, $false, $true)
  $d.SaveAs([ref]([IO.Path]::ChangeExtension($p, ".pdf")), [ref]17); $d.Close($false) } }
finally { $w.Quit() }
```

The docx edits were done by Opus subagents with python-docx (in-place run edits, length-capped).
None of the acceptance criteria are met yet: no repo script, no visual formatting check, no
missing-converter JSON error, SKILL.md unchanged. Also name output PDFs
`<Full Name> Resume - <Company>.pdf` — recruiters see the file name.

## Overrides in force

None.
