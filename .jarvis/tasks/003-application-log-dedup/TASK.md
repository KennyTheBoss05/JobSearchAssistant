# 003 — Implement logging, dedup, and config cleanup

Status: queued
Lane: chat
Created: 2026-08-17
Priority: P2

## The ask

Dedup and audit are currently promises in prose only — `.claude/skills/apply-to-jobs/SKILL.md` tells
the orchestrator to append JSON lines to `job_engine/applications_log.jsonl` and drop already-seen job
ids, but no code writes or reads that file, so a re-run would re-apply to the same jobs.

Add log-append and seen-id-filter support to `.claude/skills/apply-to-jobs/scripts/linkedin.py` so the
driver itself records each terminal outcome (`submitted` / `skip` / `blocked` / `error`) and `search`
excludes ids already logged, rather than depending on the model to remember.

While in the config, clear the JobBot leftovers in `job_engine/engine_config.yaml` and its seed copy
under `.claude/skills/job-profile-setup/assets/job_engine_seed/` — notably
`cover_letter.company_placeholder: "Fitch Ratings"`, which will paste a wrong company name into every
cover letter. Leave a runnable self-check for the dedup logic.

## Acceptance criteria

- [ ] Re-running `search` with the same query after a logged application no longer returns that job
      id.
- [ ] Every terminal `apply` outcome appends exactly one well-formed JSON line with the fields
      SKILL.md lists (`id, title, company, url, ts, mode, status, fit, resume_pdf, screenshot,
      skip_reason`).
- [ ] `company_placeholder` is derived from the target job rather than hardcoded, in both the live
      config and the seed.
- [ ] One small assert-based self-check covers dedup filtering and runs green.

## Out of scope

- Any database or structured store — a JSONL file is the intended shape.
- Changing the fit-scoring or selection prompts.

## Notes

This is the safest of the three to run unattended — it touches config and driver code, not the live
LinkedIn account. Worth doing **before** task 002, since 002's live run is what first populates the
log this task is meant to write.

## Progress — 2026-11-12

Task 002 ran first after all. `job_engine/applications_log.jsonl` now exists with 5 lines (3
submitted, 2 skipped), but the **orchestrator wrote them by hand** — the driver still neither logs
nor dedups, and the lines carry some extra fields (`answers`, `resume_actually_sent`). Use those 5
ids as the real fixture for the dedup self-check. `company_placeholder` untouched.

## Overrides in force

None.
