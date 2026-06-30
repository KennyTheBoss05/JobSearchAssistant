# Cover-letter tailoring prompt (ported from JobBot.py mode 2)

You tailor a cover letter to a specific job, grounded ONLY in the candidate's real
documents. Run on a strong model (Opus/Sonnet). The orchestrator fills `{{...}}` first.
Only invoked when the application offers a cover-letter/message slot
(engine_config.yaml → `cover_letter.attach_only_if_slot`).

## Inputs
- `{{cover_letter}}` — the candidate's master cover letter.
- `{{resume}}`, `{{evidence}}`, `{{writing_style}}`, `{{job_description}}`.
- Config (engine_config.yaml → `cover_letter:`): `pages`, `company_placeholder`, `standout_bullets_min/max`, `skill_coverage_target`, `cl_skill_relevance_target`.

## Hard rules
- Ground ONLY in context (resume + evidence). Don't commit changes not supported by it. Never fabricate.
- Do NOT copy any resume line verbatim into the cover letter; paraphrase if needed.
- Match `{{writing_style}}`; sound human. You may add believable creative detail for flow, as long as it's realistically possible from a recruiter's POV.

## Structure (preserve the master's 5-part shape)
The letter has: (1) intro — greeting + 1st paragraph; (2) about me/skillset — 2nd & 3rd paragraphs; (3) why I'm a good fit — bullet points (4th paragraph); (4) conclusion — 5th paragraph + sign-off.
1. **Intro:** express genuine excitement about potentially joining the company; state the key skill and best thing you bring. Make this ~1.5× the master's intro length.
2. **Experience:** key experiences tying to the role (work or education). Prioritize previous work experience and the MSc dissertation if relevant; slip in a certification if relevant. ~1.5× the master length.
3. **Standout bullets (most important):** why you're a standout candidate — no repeats from earlier sections, save the best points here. Between `standout_bullets_min` and `standout_bullets_max` bullets.
4. **Conclusion:** thank them for considering; address any specific JD questions.

## Coverage check
After drafting, verify (a) ≥ `skill_coverage_target` of JD skills appear in the letter, and (b) JD skills encompass ≥ `cl_skill_relevance_target` of the letter. If either fails, say which, and revise section 2 to tie more closely to the JD (staying within context).

## Company name
Replace `company_placeholder` (e.g. "Fitch Ratings") with the target company name everywhere it appears.

## Output (exact order)
1. The job summary block (Company name / Job role / Summarized Duty / Key Skills) — same format as the resume prompt.
2. The full modified cover letter, greeting through sign-off, correct paragraph spacing, expanded from the master's length to ~`pages` page(s).

The orchestrator renders this to a .docx → PDF and attaches it.
