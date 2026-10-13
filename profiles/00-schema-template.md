<!-- Copy of the template in ProfileStructure.md §5. Edit it there first, then re-sync this file. -->

# Profile: [Name]

**Tier:** [0-4]
**Status:** [draft / reviewed-by-Lukasz / validated]
**Baseline reference:** [Tier 0 file this profile deviates from, e.g. `tier0-healthy/student.md` — required for Tier 1-4, N/A for Tier 0]
**Suicidality overlay:** [none | present — see section 8 suicidality note if present]

## 1. Identity
**For Tier 0 baseline profiles:** more than a one-liner — this identity directly justifies the section 8 generation parameters, so specify:
- Occupation/schedule type (e.g. student, 9-5 worker, shift worker, retired) — drives wake/sleep timing and weekday/weekend delta
- Schedule regularity (e.g. fixed hours vs. variable) — drives the baseline's own day-to-day variance/noise
- Household/device context (e.g. lives alone vs. with family, number of devices on the router) — relevant since this project observes household-level traffic, not a single isolated device
- Age range — broad bracket only (e.g. young adult, adult, older adult), relevant to plausible domain-category mix

**For Tier 1-4 profiles:** one-liner only. Identity is inherited from the baseline reference above — just frame the symptom overlay in context (e.g. "the tier0-healthy/student baseline, now presenting moderate MDD").

## 2. Diagnostic basis
- Reference criteria: [DSM-5 sections; note where ICD-11's depressive episode criteria diverge, e.g. ICD-11 lists "hopelessness" explicitly]
- Duration window: [default 2 weeks, per diagnostic convention; standalone diagnoses below use their own duration requirement instead]
- Overall severity: [mild / moderate / severe — note: this is an official DSM-5 specifier only for MDD; for GAD, Social Anxiety Disorder, and Insomnia Disorder it's an informal grading used for synthetic-generation purposes, not a diagnostic specifier]
- **If this profile is a standalone non-MDD Tier-2 diagnosis** (insomnia disorder, GAD, social anxiety): those diagnoses have their own DSM-5 criteria and network translation in §7 of `symptom-network-mapping.md`. Sections 3 and 4 are still filled in, so every profile is complete in one file: section 3 marks the MDD table (most rows absent) **and** adds the condition's own DSM-5 criteria as extra rows; section 4 lists the §7 translation rows (plus any §3 rows that §7 says to reuse).
- **If this profile is a Tier 3 comorbid profile** involving insomnia, GAD, or social anxiety alongside depression: use section 3 (MDD table) for the depression side as normal, but also pull the relevant standalone-diagnosis nuance from mapping-file §7 for the comorbid condition's specific symptom — e.g. a depression+insomnia profile should use §7's sleep-initiation vs. sleep-maintenance distinction rather than only the generic "sleep disturbance" row in §3. Note both sources used in section 4.

## 3. Symptom set
Full DSM-5 MDD criteria list (9 items) plus project-relevant additions. Standalone non-MDD diagnoses (insomnia, GAD, social anxiety) mark this table too and append their own DSM-5 criteria as extra rows below it. Mark each Present/absent (spread) and, if present, severity (depth). Rumination and suicidality are dials/overlays here, not separate profiles — see Key decisions.
| Symptom | Present? | Severity (mild/mod/severe) | Notes |
|---|---|---|---|
| Depressed mood | | | |
| Anhedonia (loss of interest/pleasure) | | | |
| Weight/appetite change | | | weak/unreliable signal only — see mapping file, not treated as fully non-observable |
| Sleep disturbance (general) | | | |
| Early morning waking (4-5am) | | | diagnostically specific per Lukasz |
| Psychomotor agitation/retardation | | | typically not network-observable |
| Fatigue / loss of energy | | | |
| Feelings of worthlessness/guilt | | | typically not network-observable |
| Concentration difficulty | | | |
| Suicidal ideation | | | see suicidality domain-sensitivity note in section 8 |
| Hopelessness | | | ICD-11-specific (not a distinct DSM-5 criterion); typically not network-observable, see mapping file |
| Social withdrawal | | | not a DSM-5 criterion itself, but a common behavioral correlate |
| Rumination | | | not a DSM-5 criterion itself, but flagged by Lukasz as characteristic |
| Anxiety — generalized (GAD) | | | comorbidity, not an MDD criterion |
| Anxiety — social | | | comorbidity, not an MDD criterion |

## 4. Behavioral & network translation
For standalone non-MDD Tier-2 diagnoses (see section 2), the rows come from §7 of the mapping file (and the §3 rows §7 says to reuse); mark the source in the Symptom column.

Do not re-derive these here — for every symptom marked Present in section 3, look up its behavior and network feature in [`symptom-network-mapping.md`](symptom-network-mapping.md) and list only the ones that apply to this profile. For Tier 3 comorbid profiles per section 2, also add rows sourced from §7 for the comorbid condition's specific symptom, alongside the §3-sourced rows for the depression side:
| Symptom (from section 3) | Behavior (per mapping file) | Network feature (per mapping file) | Thesis criterion (metrics, per mapping file §8) |
|---|---|---|---|
| | | | |

Only add a row here that isn't already in the mapping file if this profile produces a genuinely profile-specific behavior/feature not covered by the shared table — and in that case, add it to the mapping file too so the next profile can reuse it instead of duplicating it here.

## 5. Baseline deviation spec
- **Personal baseline**: inherited from the Tier 0 file named above — do not redefine, only reference it.
- **Deviation pattern**: [what changes vs. that baseline, by how much, over what timeframe]
- **Trajectory**: [static steady-state (default) | onset curve — not yet modeled]

## 6. Non-observable symptoms
Criteria this profile technically has but that produce no reliable network signal (e.g. guilt, psychomotor changes, hopelessness — genuinely no digital correlate; appetite/weight change has a weak, ambiguous correlate via food-delivery/shopping domains, listed here too since it isn't usable as a signal in practice). Listed for honesty/limitations.

## 7. Confounds / ambiguity notes
Behaviors that could be misread as something else (e.g. early waking could be a shift worker, not depression) — relevant for explainability and false-positive discussion.

## 8. Synthetic generation parameters
Each profile is a generator, not a single fixed trace: parameters below are distributions to sample from, so multiple distinct synthetic instances (days/users) can be produced per profile rather than one script replayed verbatim.

The actual knobs for scripting traffic:
- Wake/sleep time (distribution, mean ± variance)
- DNS query rate curve over 24h
- Domain category mix (social, news, streaming, health, etc.) and weights
- Session count/length distribution
- Day-to-day variance / noise
- Weekday vs. weekend modifier

**Suicidality-specific note:** for profiles involving suicidal ideation, the domain category mix needs explicit, sensitive handling — per Lukasz, DNS queries reveal which sites a person clicks through to (e.g. crisis-line resources, self-harm-adjacent content) even without visibility into search terms. This category should be defined deliberately and separately from the generic domain mix, not folded into a generic "health" bucket.

## 9. Script specification
Makes the profile executable by the traffic scheduler. Activity IDs, domain categories (`mix` keys), conventions and distribution notation come from [`activity-catalog.md`](activity-catalog.md) — do not define activities here.
- **Tier 0:** the full weekly schedule as YAML: `day_types`, `anchors` (wake/sleep), `away` periods, `blocks` (activity, device, time window, duration, count, `mix`).
- **Tier 1-4:** a YAML **patch** on the baseline (`extends:` + `modify` / `add` / `remove` / `scale` by block ID), so only the delta from section 5 is scripted.
- **Expected thesis output:** one row per thesis criterion C1–C9: the thesis metrics this profile moves, the expected direction vs. the baseline, and whether the criterion should be *present* (L_k ≥ θ on ≥ N of M days) with the calibrated gateway config. End with the expected episode decision, and note what changes under the original thesis config. Scoring rules and known issues: [`thesis-alignment.md`](thesis-alignment.md). This is the validation target for the run.
