# Portal v3: Karla's sessions (K1–K5)

The full plan is [Feedback-v3-Plan.md](Feedback-v3-Plan.md). This file has the setup and one prompt
per session to paste into Claude Code. The five sessions own different files and can run at the same
time.

## Setup (once, by hand)

1. Wait until Thierry has pushed `frontend-v3` (it has this file and the plan in `process/`).
2. In your clone of the repo: `git fetch origin`.
3. Data: `~/cmn-data` with `processed_parquet/`, `run/` and ideally `eval/` from the gateway, as for the
   local Streamlit run. Then fill the cache once, as in `frontend/README.md` → "Run it"
   (`python -m cmn_frontend.export`). All sessions share it read-only.
4. Start each session in its own worktree (Claude Code "worktree" option, or
   `git worktree add ../cmn-v3-k1 -b v3/k1-reference-ranges origin/frontend-v3`, and likewise for the
   others) and paste its prompt below.
5. Ports: one API per session that runs the portal: 8600, 8602, 8603, 8604, 8605 (8601 is Whisper);
   Vite 5173, 5174, ….

Rules that apply to every session (already in each prompt): only edit the files the session owns
(plan §5.3); base on `origin/frontend-v3`; open a PR into `frontend-v3`, never into `main`; rebase on
`frontend-v3` once T0 (Thierry's visual foundation) is merged.

---

## K1: reference ranges and new flags

```text
You work on the v3 portal of our bachelor project "Can My Network Tell How I Feel?" (router-level
network metrics → DSM-5 criterion likelihoods; results portal in frontend/). Read
process/Feedback-v3-Plan.md first: §2 (visual rules and shared contract), §3 (norm data), §5.2 (API
contract), §5.3 (file ownership) and your session K1 in §5.5.

Your task (K1, backend):
- D2: verify every figure in the §3 table against the full text of its source (fetch the papers; note
  page/table). Only verified values go into a new frontend/backend/cmn_frontend/norms.json: value(s),
  age band, school vs. free day, population, citation, proxy_note (why the network metric is only a
  proxy). Values you cannot verify stay out; list them in the PR description.
- new norms.py: percentiles from a published mean ± SD under a normal assumption (marked as such).
- observed.py: the healthy reference becomes a "typical" reference with P16/P50/P84 per track,
  empirical percentiles for the pooled days, a switchable source ("pooled" | "external"), and per day
  percentile_ref; exactly the fields in §5.2.
- D1: "healthy people" → "typical" / "reference group" in all texts observed.py produces.
- D5: new track quiet_start_sd7 (SD of the went-quiet time over the last 7 nights) and risk
  irregular_nights against the baseline's rolling SD.
- E1: flags with kind "change" in the improving direction (neutral, "to discuss"); every flag gets
  kind and icon (icon names in §2).
- attention {flags, alert} per profile in the /api/profiles list (profiles.py / api.py, additive).
- api.ts: add the new types only (additive, never rename).

Only edit files K1 owns (§5.3) plus additive edits in api.py / api.ts. Do not touch the UI
components; Thierry's T1 renders your fields. The gate and the evaluation numbers must not change.

Work on branch v3/k1-reference-ranges from origin/frontend-v3. Tests: cd frontend/backend &&
.venv/bin/python -m pytest; cd frontend/web && npm test && npm run typecheck. Extend
tests/test_observed.py for percentiles, both reference sources, irregular nights and change flags.
Commit messages in the repo's style ("Portal v3: …"). Open a PR into frontend-v3 and describe the
new fields and the verified sources.
```

## K2: assistant behaviour and reliability

```text
You work on the v3 portal of our bachelor project (results portal in frontend/). Read
process/Feedback-v3-Plan.md first: §2, §4 B and §8, §5.3 (file ownership) and your session K2 in §5.5.

Your task (K2):
- A1: PRODUCT_NAME = "Rhythm" in frontend/backend/cmn_frontend/settings.py; the assistant prompt and
  the FastAPI title use it instead of "Can My Network Tell How I Feel?".
- B1: prompts in assistant.py: answer the question first in 1–3 sentences, from the week overview
  where it fits; no unrequested "what it can / cannot imply" part; person replies about 80 words at
  most unless the user asks for more detail.
- B2 (backend side): the UI will send "Shorter" and "More detail" as follow-up messages; make the
  prompt handle them (shorten / expand the previous answer, nothing new invented).
- B3: person guardrail: only describe what was observed (less quiet time, more use), no reasons,
  meanings, symptoms or diagnoses, also when asked repeatedly; suggest talking to the care team.
- D1: "typical" instead of "healthy people" in prompts and context.
- B5: eval/assistant_eval.py (new, in frontend/backend): about 20 questions per role (person,
  clinician) on the three scripted personas, with checks: every number in an answer exists in the
  context sent, no clinical terms for the person (forbidden-term list), no diagnosis. Writes a
  Markdown results table for the report. Needs the Claude key from Settings or ANTHROPIC_API_KEY.
- tests/test_assistant_rules.py: offline checks of the prompt rules and the eval's checkers.

Only edit: assistant.py (prompts and build_context; not stream_answer / stream_claude / the settings
class, those belong to K3), settings.py, the new eval and test files. Branch v3/k2-assistant from
origin/frontend-v3. Tests: cd frontend/backend && .venv/bin/python -m pytest. Commit messages
"Portal v3: …". PR into frontend-v3 with the eval results table in the description.
```

## K3: local model

```text
You work on the v3 portal of our bachelor project (results portal in frontend/). Read
process/Feedback-v3-Plan.md first: §2 (visual rules), §5.3 (file ownership), §7 and your session K3
in §5.5.

Your task (K3, B6): show that the assistant can run on a local model instead of Anthropic.
- new frontend/backend/cmn_frontend/llm.py: provider layer with "anthropic" (current behaviour) and
  "local" (OpenAI-compatible endpoint: Ollama, llama.cpp server or LM Studio), streaming text and
  JSON output with a schema (JSON mode / grammar for the local path).
- assistant.py: only stream_answer, stream_claude and the settings class call llm.py (the prompts
  belong to K2); setup_assist.complete_json calls llm.py.
- AssistantSettings.tsx: provider choice (Anthropic / local endpoint URL + model name); follow the
  visual rules in §2 (no red except alerts, labels, icons).
- Setup notes (in the PR description; T5 moves them to the README): which model runs well on a
  laptop for this task, how to start it, how the mini-PC reaches it over Tailscale.
- When K2's eval exists (eval/assistant_eval.py), run it on the local model and add the table.

Only edit the files listed (and deploy/ if the LLM host needs a config). Branch v3/k3-local-llm from
origin/frontend-v3; rebase on frontend-v3 after K2 is merged (both touch assistant.py, different
functions). Tests: cd frontend/backend && .venv/bin/python -m pytest; cd frontend/web && npm test &&
npm run typecheck. Commit messages "Portal v3: …". PR into frontend-v3.
```

## K4: onboarding asks for what is missing

```text
You work on the v3 portal of our bachelor project (results portal in frontend/). Read
process/Feedback-v3-Plan.md first: §2 (visual rules and shared contract: Icon.tsx, theme tokens),
§5.3 (file ownership) and your session K4 in §5.5.

Your task (K4, C1): after the person describes their week (typed or dictated), the onboarding asks
specifically for what is still missing, so the routine form ends up complete.
- setup_assist.py (routine part only; complete_json belongs to K3): missing_fields(routine) decides
  deterministically what is missing (times null, weekdays still at the default, no devices, no
  free-day times) and returns template questions in plain language ("When do you usually go to bed on
  weekends?"). No LLM for the detection; the LLM only fills the form from the answers.
- Onboarding.tsx / RoutineForm.tsx / Dictate.tsx: show the questions one at a time, each answerable by
  typing or dictation; the answer runs through suggest_routine again and is merged into the form;
  "skip" is always possible.
- Visual rules (§2) on these screens: icons for away / home / free (names in the contract; if
  Icon.tsx is not merged yet, use the contract's names and rebase later), no red except the recording
  indicator, every control labelled.

Only edit these files (+ new tests). Branch v3/k4-onboarding from origin/frontend-v3. Tests: cd
frontend/backend && .venv/bin/python -m pytest; cd frontend/web && npm test && npm run typecheck
(RoutineForm.test.tsx, Dictate.test.tsx, plus tests for missing_fields). Commit messages
"Portal v3: …". PR into frontend-v3.
```

## K5: care plan purpose and visuals

```text
You work on the v3 portal of our bachelor project (results portal in frontend/). Read
process/Feedback-v3-Plan.md first: §1 (Lukasz' points), §2 (visual rules and shared contract), §5.2
(care.purpose), §5.3 (file ownership) and your session K5 in §5.5.

Your task (K5):
- E2: care.purpose = "assessment" | "treatment" in care.py and CarePlan.tsx. Assessment: the
  overview shows the comparison with the typical range first. Treatment monitoring: change over time
  first, and "notable change" flags (improvements, kind "change") on by default. Store it, expose it
  in the timeline response (additive in api.py / api.ts); Thierry's T1 reads it in the overview.
- Visual rules (§2) on the care plan: risk icons identical to the flag icons (contract names), no red
  except the crisis/self-harm risk, every field labelled, nothing without a purpose.
- Draft the question list for the LiFE clinicians (in the PR description): which red flags, positive
  and negative, they look for; whether they have norm data (sleep times of their adolescents from
  questionnaires / EMA); which care-plan fields they would fill in and which are missing.

Only edit care.py, CarePlan.tsx, tests/test_care.py (+ additive api.py / api.ts). Branch
v3/k5-care-plan from origin/frontend-v3. Tests: cd frontend/backend && .venv/bin/python -m pytest;
cd frontend/web && npm test && npm run typecheck. Commit messages "Portal v3: …". PR into frontend-v3.
```
