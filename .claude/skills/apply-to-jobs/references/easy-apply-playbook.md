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
| `error` (`no_modal`, `no_advance_button`, `stuck_on_step` + `modal_text`, `step_limit_exceeded`) | DOM/selector drift; payload has `screenshot` + `html` (`screenshots/<id>_error.{png,html}`) | self-heal: read both, patch `SEL`/the function in linkedin.py, retry that job once (see decision-tree) |
| `error` (`resume_not_attached`) | tailored PDF wasn't the selected resume; nothing submitted | skip the job — safety guard, never self-healed |

Every payload also carries `resume_attached` (`true`/`false`/`null` = no resume step or no `--resume`).

## answers.json format
A flat map of question-label (or fragment) → value. The driver starts from
`profile.yaml:saved_answers`, overlays `answers.json` (per-job wins), normalizes labels (lowercase,
collapsed whitespace) and matches by exact then substring, then falls back to profile
heuristics (email/phone/city/first/last name, years-per-skill, sponsorship, and work
authorization — "Yes" only when the label names a country in `countries_authorized`). Example:
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

### Verified UI notes (2026-06, first live run)
Hard-won facts from the first end-to-end validation — start here before re-deriving:
- **The Easy Apply modal renders inside a shadow root.** Raw `page.evaluate(querySelectorAll)`
  CANNOT see modal content (returns empty / null `[role=dialog]`). **Playwright locators
  (`page.locator`, `get_by_role/label/text`) DO pierce it** — always probe with locators, not
  raw JS. Inside the modal the legacy artdeco classes still resolve via locators
  (`div.jobs-easy-apply-modal`, `div.fb-dash-form-element`, `button[aria-label='Continue to
  next step']` all work).
- **Easy Apply trigger is an `<a aria-label="Easy Apply to this job">`**, not a `<button>`.
- **Job-view / search pages use a newer light-DOM build with obfuscated hashed classes**
  (e.g. `e4c6b5f3 _890a5cf2`) and NO `<h1>`. Don't anchor on a bare `h1` — it grabs the
  "LinkedIn respects your privacy" banner. The title top-card class still works; `cmd_search`
  also falls back through the card text and `page.title()` (`_read_title`).
- **Scope modal nav buttons to the modal** — a page-level carousel arrow also has
  `aria-label='Next'`, so an unscoped `button[aria-label='Next']` clicks the wrong thing and
  is blocked by the `#interop-outlet` shadow host. `cmd_apply` uses `modal.locator(...)`.
- **Search cards:** `li[data-occludable-job-id]` is the complete, stable set (vs the partial
  `div.job-card-container`); dedupe by the card's `data-occludable-job-id`.
- **Login can be Microsoft/Google SSO.** `is_logged_in` must catch generic nav-interrupt
  errors (not just timeouts), and the login poll watches the `li_at` cookie WITHOUT navigating
  (navigating mid-SSO breaks the redirect). See `_has_li_at`.

### Verified UI notes (2026-11-12, second live run — supersedes conflicting notes above)
- **Search:** `/jobs/search/` redirects to `/jobs/search-results/`; `location=` is dropped, use
  `geoId` (UK = 101165590) in `--filters`. Cards carry `componentkey="job-card-component-ref-<id>"`;
  `cmd_search` collects ids, then reads each `/jobs/view/<id>/` (title/company from `page.title()`).
- **Modal is a native `<dialog open>`** with hashed classes. `_read_groups` tags controls with
  `data-ja-idx` and reads semantic HTML only (`label[for]`, `fieldset`). Radio groups have no
  `<legend>`: the question is the radio's `aria-label`, option text is in a sibling div, and the
  `*` is outside the fieldset. Buttons are found by accessible name, scoped to the dialog.
- **Styled radios ignore `check(force=True)`** — `_check_radio` falls back to clicking the card.
- **Resume:** "Upload resume" opens a file chooser (no persistent input). Resume radios are
  labelled by file name. Always upload (old saved copies hide in the collapsed list). The resume
  section renders late — wait for it, and auto mode refuses to submit if `--resume` wasn't selected
  (`resume_not_attached`). Name PDFs `<Full Name> Resume - <Company>.pdf` — the
  recruiter sees the file name. Verify after submit via the job page's "View resume" link.
- **answers.json keys match by substring** — use the full/exact label for short keys
  (`"country*"`, not `"country"`, which also matches "the country where the position is based").
- Phone field rejects `+`/country code (digits only; separate country-code select).

## Pacing & anti-flagging
Headed browser, human-like randomized delays (config `pacing`), and per-job delays. If
LinkedIn shows a verification/friction interstitial, treat it as a session-level block: stop,
notify, let the user clear it. Don't hammer retries — that's the fastest way to a restriction.
