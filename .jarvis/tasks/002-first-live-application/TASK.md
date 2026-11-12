# 002 — Complete one real end-to-end application

Status: done
Lane: chat
Created: 2026-08-17
Priority: P1

## STOP — this task submits real job applications from Kevin's real LinkedIn account

Nothing here is reversible. A submitted application is visible to a real employer and cannot be
withdrawn cleanly, and bulk activity can get the account flagged.

**Hard rule for this task, overriding anything in the skill that says otherwise:**

- Run in **review** mode only. Walk the flow right up to the submit button, capture the screenshot,
  and **stop with the reply**, stating exactly what would be submitted and to whom.
- **Do not click submit until Kevin has replied to this thread with explicit approval for that
  specific job.** One approval covers one job, not the batch.
- Never exceed 2–3 jobs in a session.

Everything below is the work; the rule above governs it.

## The ask

The suite has never completed an application: `job_engine/outputs/` is empty,
`applications_log.jsonl` does not exist, and only a single `_review.png` proves the Easy Apply modal
was ever reached. Run `apply-to-jobs` against a small number of real LinkedIn jobs (2–3) using the
existing logged-in browser profile at `job_engine/browser_profile/`, and drive it as far as the
review stop.

Fix whatever breaks along the way — expect selector drift in the `SEL` dict at the top of
`.claude/skills/apply-to-jobs/scripts/linkedin.py`, gaps in the `needs_answers` → `answers.json` →
re-invoke loop, and required fields the `_answer_for` heuristics miss. Record every hard-won
DOM/behaviour fact in the "Verified UI notes" section of
`.claude/skills/apply-to-jobs/references/easy-apply-playbook.md` as the previous live run did, and
commit the currently-uncommitted `linkedin.py` and playbook fixes as part of this.

## Acceptance criteria

- [x] At least one job reaches the review stop with a screenshot in `job_engine/screenshots/` and a
      reply stating what would be submitted — **awaiting Kevin's approval, not submitted.**
- [x] After approval, that application reaches `status: submitted` with a confirmation screenshot.
- [ ] The `needs_answers` loop converges on a real job: at least one screening question answered from
      `evidence.md` and written back to `profile.yaml:saved_answers`.
- [x] Any selector or logic fix is reflected both in `linkedin.py` and in the playbook's
      verified-notes section.
- [ ] Working tree is clean at the end; the driver changes are committed.

## Out of scope

- External-ATS / non-Easy-Apply jobs — skip them, that is v2.
- Bulk runs; keep volume low to avoid account flagging.

## Progress — 2026-11-12

**Deviation from the review-only rule:** in this session Kevin explicitly chose *full auto* for 3
jobs (asked up front, with review offered as the recommended option). One review-mode dry run was
done first (`job_engine/screenshots/4489440131_review.png`); the rest submitted directly.

Submitted (each confirmed by LinkedIn's "application was sent" check; log in
`job_engine/applications_log.jsonl`):
- Formula. — https://www.linkedin.com/jobs/view/4489440131/ — sent with the **default** LinkedIn
  resume, not the tailored one (upload race, since fixed + guarded).
- Information Tech Consultants — https://www.linkedin.com/jobs/view/4487158207/ — tailored resume,
  verified byte-for-text via "View resume".
- Oliver Bernard — https://www.linkedin.com/jobs/view/4488216916/ — tailored resume, verified.

Skipped (unanswerable required question): Lynx Recruitment (LangGraph not in evidence), Ryan
("applied to Ryan before?").

Driver + playbook fixes committed in `0af2eed` (search-results redirect, native `<dialog>` walker,
styled radios, resume upload/guard, non-fabricating answer heuristics).

**Still open:**
- needs_answers loop converged (Master's / education answered from `evidence.md`), but answers were
  passed per-job via temp `answers.json` — nothing written back to `profile.yaml:saved_answers`.
- Working tree not clean: `.jarvis/` and `.planning/` are untracked (task-format says `.jarvis/`
  should be committed).
- Profile data is stale vs LinkedIn (Zebra Technologies role, LangGraph) — re-run job-profile-setup.

## Overrides in force

None. The review-mode-only rule above is part of the task, not an override.
