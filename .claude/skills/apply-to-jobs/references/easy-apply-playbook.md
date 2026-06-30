# LinkedIn Easy Apply playbook

How the `linkedin.py apply` driver walks the modal, and what you (orchestrator) do around it.

## The modal shape
Easy Apply opens a multi-step modal. Steps vary by job but commonly: Contact info →
Resume upload → (Work authorization / screening) → Additional questions → Review → Submit.
Required fields gate the **Next** button, so the driver can't reach later steps until
earlier required fields are filled. That's why the loop is iterative.

## The driver contract (what each return means)
The driver fills every field it can from `answers.json` + `profile.yaml` heuristics, then:

| Return `status` | Meaning | Your action |
|---|---|---|
| `needs_answers` | hit required field(s) with no known answer | answer each via the qa_answer subagent (grounded in evidence); append answerable ones to `answers.json`; re-invoke `apply` |
| `submitted` | full-auto submitted; screenshot saved | log success |
| `ready_for_review` | review-mode stopped at Submit; review screenshot saved | show user the screenshot + planned answers; on approval re-run `--mode auto` |
| `skip` / `no_easy_apply` | not an Easy Apply job (external ATS) | log skip; next candidate (v1 doesn't do external) |
| `blocked` / `not_logged_in` | session-level wall | notify + pause (see decision-tree) |
| `error` (`no_advance_button`, `step_limit_exceeded`) | DOM/selector drift | inspect live, adjust `SEL` in linkedin.py, retry once |

## answers.json format
A flat map of question-label (or fragment) → value. The driver normalizes labels (lowercase,
collapsed whitespace) and matches by exact then substring, then falls back to profile
heuristics (email/phone/city/first/last name, years-per-skill, sponsorship). Example:
```json
{"how many years of experience do you have with python": "5",
 "are you authorized to work in the uk": "Yes",
 "why are you interested in this role": "<tailored answer>"}
```
Reusable answers (tone-stable, not job-specific) should also be saved to
`profile.yaml:saved_answers` so future runs start pre-filled.

## Resume upload
The driver calls `set_input_files` on the first file input with the tailored PDF you pass via
`--resume`. If a job pre-fills the user's stored LinkedIn resume and offers no upload input,
the tailored PDF can't be attached — note this in the log; the application still proceeds
with screening answers tailored.

## Selector drift (expect it)
LinkedIn changes its DOM frequently and runs bot detection. The `SEL` dict at the top of
`linkedin.py` is the single place to fix selectors. On the first live run, if a step errors,
open the page, read the actual DOM/aria labels, update `SEL`, and re-run. The architecture
(persistent profile + iterative needs_answers loop) is stable; only selectors are brittle.

## Pacing & anti-flagging
Headed browser, human-like randomized delays (config `pacing`), and per-job delays. If
LinkedIn shows a verification/friction interstitial, treat it as a session-level block: stop,
notify, let the user clear it. Don't hammer retries — that's the fastest way to a restriction.
