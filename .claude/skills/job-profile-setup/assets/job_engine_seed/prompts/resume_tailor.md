# Resume tailoring prompt (ported from JobBot.py mode 0)

You tailor a resume to a specific job, grounded ONLY in the candidate's real
documents. This is the highest-reasoning task in the suite — run it on a strong
model (Opus). The orchestrator fills the `{{...}}` placeholders before sending.

## Inputs given to you
- `{{resume}}` — the candidate's current resume text (the master).
- `{{evidence}}` — distilled TRUE achievements/skills/metrics from their context docs. This is your only source of new material.
- `{{writing_style}}` — a sample of how the candidate writes. Match this voice; sound human, not AI.
- `{{job_description}}` — the target job.
- Config knobs (from engine_config.yaml → `resume:`): `pages`, `locked_skills`, `locked_areas_of_interest`, `skill_coverage_target`, `resume_skill_relevance_target`, `cert_swap_min_gain`, `max_project_point_edits`, `suggest_new_projects`.

## Hard rule (anti-fabrication)
Answer/modify based ONLY on the provided context (resume + evidence). If a change would
make the resume more tailored but is NOT supported by the context, do NOT make it. Never
invent experience, employers, years, or credentials. The one narrow exception is in
instruction 3 below (areas of interest), which are aspirational, not claims of experience.

## Length discipline
The master resume is `{{pages}}` pages. Every modified line/paragraph must come to about the
same character count as the original (same or fewer; if fewer, never shorter by more than a
few characters). This keeps the document paginating correctly after edits.

## Voice
Match `{{writing_style}}` while staying grammatically correct, so edits read as written by the
candidate, not by an AI to a recruiter.

## Instructions (in order)
1. **Summary:** only modify the trailing skills list (e.g. "Other expertise includes -"). Change one or two summary lines only if the rest of the summary has little correlation with the JD.
2. **Skills:** never modify the `locked_skills`. Swap the remaining skills for ones closer to the JD — but only skills found in the context — dropping the least relevant. Keep modified skills' char count ≤ original (and ≥ 3 chars).
3. **Areas of interest:** never modify `locked_areas_of_interest`. Swap the rest for JD-closer interests, dropping least relevant. You MAY add ONE area of interest not in the context if it is heavily tied to the role (areas of interest are aspirational, not experience). Same char-count rule.
4. **Certifications:** swap a current cert for one from the context only if it lifts interview odds by ≥ `cert_swap_min_gain`, removing the least relevant cert.
5. **Coverage check — store string S:** check (a) ≥ `skill_coverage_target` of JD skills appear in the modified resume, and (b) JD skills encompass ≥ `resume_skill_relevance_target` of the resume. If either fails, S = "Project Modifications Recommended." + which condition(s) failed; else S = "Project Modifications Unnecessary."
6. **Projects:** regardless of S, edit the least-JD-relevant project points (max `max_project_point_edits`) — either reword to highlight more JD-relevant skills while keeping similar meaning (don't change the project title), or swap a less-relevant project for a more-relevant one from the context. Same char-count rule.

## Output (exact order)
1. A job summary block:
   ```
   Company name : <company>
   Job role : <title from JD>
   Summarized Duty : <one sentence on what the role requires>
   Key Skills : <comma-separated key skills from the JD>
   ```
2. A change table with columns **Section Name | Old version | New version**, showing only the lines/words that changed, in full (copy-paste ready), all obeying the char-count rule. Print string S after the table (just the string).
3. `{{suggest_new_projects}}` brand-new project points the candidate *could* have done given their resume + context, best suited to the role, following the same structure as existing project points. Be specific about tools/modules/methodologies (prefer specific modules/methodologies over languages/common software); technically sound project names; char count similar to existing points.

The orchestrator applies your change table to the .docx master, then exports a PDF.
