# Decision tree: skip vs queue vs pause vs self-heal (never fabricate)

The core promise: run autonomously to N applications, only stopping when there's genuinely
no other way forward. Use this to decide what to do at every branch. The overriding rule:
**never fabricate** — inventing a fact to get past a gate fails the user in the interview and
violates `grounding.strict`.

## When a required field has no honest answer
The qa_answer subagent returned `CANNOT_ANSWER`, or its free-text answer failed
`checks.py claims` (treated the same).

```
Is the value derivable from profile.yaml / saved_answers / evidence.md without inventing?
├── YES → use it, continue.
└── NO  → Is it a hard disqualifier (lacks a required credential/clearance/authorization)?
          ├── YES → skip, log skip_reason="disqualified: <field>", next candidate.
          └── NO  → mode?
                    ├── auto   → skip, log skip_reason="unknown required: <q>", append
                    │            "- [ ] <q> — <company> (<id>, <date>)" to
                    │            job_engine/pending_questions.md, next candidate.
                    └── review → surface the question to the user; keep preparing others.
```
Optional/non-required unknown fields → leave blank and continue.

## Pending-questions queue
`job_engine/pending_questions.md` collects questions only the user can answer. Interactive
runs ask all unchecked items in one batch at preflight, save answers to
`profile.yaml:saved_answers` (normalized question → answer) and tick `- [x]`. Scheduled runs
only append. A job skipped as `unknown required: <q>` becomes eligible again once `<q>` is
answered.

## Grounding / PDF gate failures
The tailoring subagent revises once after a `checks.py claims` or `checks.py pdf` failure. If
either still fails → skip, log `skip_reason="grounding: <terms>"` or `"pdf: <problems>"`. A
term that keeps being flagged but is true belongs in `evidence.md` (or
`grounding.allow_terms` for pure synonyms) — tell the user in the report.

## Fit floor
A job scored below `selection.fit_floor` is dropped before applying, logged as
`skip_reason="fit: <score> <why>"`. This protects the user from low-quality applications and
from screening questions they couldn't answer honestly — the situation that tempts fabrication.

## Self-heal (driver `error` = selector drift)
```
error ∈ {no_modal, no_advance_button, stuck_on_step, step_limit_exceeded}?
├── patches this run < 2 → read screenshots/<id>_error.png + <id>_error.html, diagnose,
│                          patch SEL or the relevant function in linkedin.py, retry THIS job once.
│                          ├── passes → append a dated bullet under
│                          │            "### Verified UI notes (<date>, self-heal)" in the playbook.
│                          └── fails  → skip, log skip_reason="driver: <error>".
└── cap reached          → skip, log, keep the capture for the report.
error == resume_not_attached → skip. Never self-heal (safety guard against sending the wrong resume).
```
Never commit patches; list changed files in the run report for the user to review.

## Session-level blocks (only the user can clear)
CAPTCHA, fresh 2FA, expired login, or a LinkedIn verification interstitial halt the whole
session — there's nothing left to "skip to".
- **Interactive:** fire a desktop notification (the `notify-prompt-finished.ps1` Stop hook is
  registered globally on this machine; elsewhere print a clear message), pause and wait. The
  log records completed applications, so the run resumes from the next candidate.
- **Scheduled:** end the run immediately. The report's first line is the `**BLOCKED:**` login
  instruction (see SKILL.md). Don't wait.
- Never retry in a tight loop (retries accelerate account flagging).

## External-ATS redirect (v1)
`no_easy_apply` → skip and move on. v2 handles external ATS.

## Volume
- Honor the N the user asked for. If `selection.max_per_run > 0`, never exceed it in one run
  — tell the user and suggest splitting across runs.
- `selection.max_per_day` caps submitted applications per local day across all runs
  (`checks.py quota`; 0 = unlimited). Check before each job and stop the loop at 0 remaining.
