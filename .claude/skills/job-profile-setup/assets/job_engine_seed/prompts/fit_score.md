# Fit-scoring prompt (new — supports the selection step)

You score how well the candidate fits a batch of jobs, so the applier applies to the
best ones first and skips poor fits (which waste applications and create pressure to
fabricate). Run on Sonnet. Score a batch in one call for efficiency.

## Inputs
- `{{profile}}` — structured profile (years per skill, seniority, location/remote prefs, salary range, work authorization, etc.).
- `{{evidence}}` — distilled true achievements/skills.
- `{{jobs}}` — a list of candidate jobs, each with id, title, company, location, and job description.
- Config: `selection.fit_floor`.

## How to score
For each job, weigh: skills overlap (resume/evidence vs JD must-haves), seniority match,
location/remote compatibility, salary alignment (if the JD states one), and hard
disqualifiers (e.g. requires a clearance/credential/authorization the candidate lacks, or
a hard years-of-experience gate they don't meet). A hard disqualifier should pull the score
below `fit_floor`.

Do NOT inflate scores to be helpful — a realistic floor protects the candidate from
low-quality applications and from screening questions they can't honestly answer.

## Output
A JSON array, highest fit first:
```json
[
  {"id": "<job id>", "fit": 0.0-1.0, "rationale": "<one line>", "disqualifier": "<reason or null>"}
]
```
The orchestrator drops anything with `fit < fit_floor` (logging the rationale) and applies to
the rest best-first until N applications succeed.
