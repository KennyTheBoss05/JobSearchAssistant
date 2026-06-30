# Decision tree: skip vs ask vs pause (never fabricate)

The core promise: run autonomously to N applications, only stopping when there's genuinely
no other way forward. Use this to decide what to do at every branch. The overriding rule:
**never fabricate** — inventing a fact to get past a gate fails the user in the interview and
violates `grounding.strict`.

## When a required field has no honest answer
You asked the qa_answer subagent and it returned `CANNOT_ANSWER` (the fact isn't in the
resume/evidence and can't be safely derived — e.g. a credential they lack, a specific number
they never stated).

```
Is the value derivable from profile.yaml or evidence.md without inventing?
├── YES → use it, continue.
└── NO  → Is it a hard disqualifier (lacks a required credential/clearance/authorization)?
          ├── YES → skip this job, log skip_reason="disqualified: <field>", next candidate.
          └── NO  → mode == full-auto?
                    ├── full-auto → skip this job, log skip_reason="unknown required: <field>",
                    │               next candidate. (User asked for N jobs, not THIS job.)
                    └── review    → queue: keep the job, surface the question to the user,
                                    continue preparing other candidates meanwhile.
```
Optional/non-required unknown fields → leave blank and continue.

## Session-level blocks (only the user can clear)
CAPTCHA, fresh 2FA, expired login, or a LinkedIn verification interstitial physically halt
the whole session — there's nothing left to "skip to". So:
1. Fire a desktop notification (the `notify-prompt-finished.ps1` hook is registered globally on
   this machine; on other OSes, print a clear, attention-grabbing message).
2. Pause and wait. Keep the run resumable: the log already records completed applications, so
   when the user returns you continue from the next candidate.
3. Do NOT treat these as skippable and do NOT retry in a tight loop (retries accelerate
   account flagging).

## External-ATS redirect (v1)
If a job isn't Easy Apply (driver returns `no_easy_apply`), skip it in v1 and move on. v2 will
handle external ATS.

## Fit floor
A job scored below `selection.fit_floor` is dropped before applying (logged). This protects the
user from low-quality applications and from screening questions they'd be unable to answer
honestly — which is exactly the situation that tempts fabrication.

## Volume
Honor the N the user asked for. If `selection.max_per_run > 0`, never exceed it in one run even
if asked for more — tell the user and suggest splitting across runs (account safety).
