---
name: tune-job-engine
description: >-
  Personalize the "thinking" behind the job-application skills — how resumes/cover letters
  are tailored, how screening questions are answered, how jobs are selected, and how fast the
  applier paces itself. Use whenever the user wants to change application behavior WITHOUT
  re-running setup or applying, e.g. "make my answers more formal", "stop swapping out my SQL
  skill", "be pickier about which jobs to apply to", "tailor my resume less aggressively",
  "answer screening questions in one line", "slow down between applications", "change the cover
  letter to 1.5 pages", "lock these skills so they never change". Edits job_engine/engine_config.yaml
  and job_engine/prompts/*.md, which apply-to-jobs reads on every run. A quick, one-time-ish
  personalization layer — not for applying to jobs (use apply-to-jobs) or onboarding docs
  (use job-profile-setup).
---

# Tune the job engine

This skill edits the configuration that drives the *reasoning* of the other two skills, so the
user can shape behavior without touching any code or re-onboarding. Everything lives in
`job_engine/` and is read fresh on every `apply-to-jobs` run.

## What you can tune (and where it lives)
| The user wants to… | Edit |
|---|---|
| Change answer tone (professional/formal/warm/concise), one-line answers, creativity | `engine_config.yaml → answers` |
| Be pickier/looser about which jobs to apply to | `engine_config.yaml → selection.fit_floor`, `rank_by_fit`, `max_per_run` |
| Slow down / speed up, change delays | `engine_config.yaml → pacing` |
| Lock/unlock skills or areas of interest; change resume page count, coverage targets, project-edit limits | `engine_config.yaml → resume` |
| Change cover-letter length, standout-bullet count, company placeholder, coverage targets | `engine_config.yaml → cover_letter` |
| Change *how* tailoring/answering reasons (the actual instructions) | `job_engine/prompts/*.md` |

## How to work
1. **Read the current values first.** Open `engine_config.yaml` (and the relevant
   `prompts/*.md` if the change is about reasoning, not a knob). Show the user what's set now.
2. **Map the request to the smallest change.** Prefer flipping a config knob over editing a
   prompt. Only edit `prompts/*.md` when the user wants to change the *logic/instructions*
   themselves (e.g. "also tailor my Experience section, not just Projects").
3. **Make the edit**, then **echo back** the before → after so the user can confirm. For YAML,
   preserve comments and structure; keep values valid (e.g. `fit_floor` in 0..1).
4. **Explain the effect.** One line on what will change next run. Don't re-run anything — this
   skill only configures.

## Guardrails
- **Keep the anti-fabrication rule intact.** `grounding.strict: true` and the "ground only in
  resume + evidence / never invent" clauses in the prompts are load-bearing. If the user asks
  to relax honesty (e.g. "just say I have 5 years even if I don't"), refuse and explain it
  risks the interview and misrepresents them; offer to instead surface their closest true
  experience or lower the fit floor so such jobs aren't targeted.
- Don't edit `profile.yaml`/`evidence.md` here — that's `job-profile-setup`'s job. If the user
  wants to change personal facts, point them there.
- Validate YAML after editing (a broken config breaks both other skills). A quick
  `python -c "import yaml,sys; yaml.safe_load(open('job_engine/engine_config.yaml'))"` confirms it parses.
