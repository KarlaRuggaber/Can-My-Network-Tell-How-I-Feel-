# Profile Structure

## 1. Core design principles

- **Deviation-from-baseline, not absolute values.** Every profile needs both a personal baseline and a deviation pattern — the system never says "this person is depressed," only "this deviates from their own norm."
- **Symptom → behavior → network feature chain.** Every profile must be traceable through this chain explicitly (this is the explainability backbone).
- **DSM-5/ICD-11 anchored.** Each profile's symptoms map to actual diagnostic criteria, not invented categories.
- **Honest about blind spots.** Profiles note which DSM-5 criteria are network-observable vs. not (e.g., guilt, psychomotor changes = not observable; sleep, social withdrawal, suicidality = observable).
- **Spread × depth.** Per Lukasz, depression heterogeneity is captured along two axes: *spread* (which symptoms are present — the "Present?" column in the symptom table) and *depth* (severity of each present symptom — mild/moderate/severe). Every profile should vary both independently rather than treating depression as a single fixed pattern.

## 2. Profile hierarchy

```
Tier 0: Healthy baseline (control)
Tier 1: Single-symptom / grey-zone profiles
Tier 2: Clinical-threshold single-condition profiles
Tier 3: Comorbid / combination profiles
Tier 4: Edge cases (high-functioning, masked)
```

- **Tier 0** — Normal/healthy user (multiple variants: e.g. student routine, 9-5 worker, irregular-but-healthy)
- **Tier 1** — Mild/subclinical: mild insomnia, mild low mood, mild anxiety (grey zone, sub-diagnostic threshold)
- **Tier 2** — Clinical single-symptom-dominant: insomnia disorder, MDD (moderate), MDD (severe), generalized anxiety, social anxiety. (Suicidality is not a standalone tier item — see the suicidality overlay note under Key decisions.)
- **Tier 3** — Comorbid combinations: depression + insomnia, depression + GAD, depression + social anxiety
- **Tier 4** — Edge/hard cases: high-functioning depression (deferred, see below)

## 3. Key decisions

- **Severity scale**: discrete — `mild / moderate / severe`, applied per-symptom (a comorbid profile can mix, e.g. severe insomnia + mild GAD).
- **Trajectory**: every profile is built **static/steady-state first** (person already "in" that state for the full 2-week window, with natural day-to-day noise). Week-by-week onset trajectories (gradual build-up, matching real episode development) are added later for a subset of profiles where it's most clinically meaningful — insomnia and MDD onset are the natural first candidates. The schema carries a trajectory field that defaults to "static baseline only, not yet modeled."
- **High-functioning depression**: placed in `tier4-edge-cases/`. Documented (symptom set, diagnostic basis) now, but its behavioral/network translation is deferred until core profiles are validated — it's a likely negative-signal case, useful for the limitations discussion, but lower priority than profiles expected to show clear signal.
- **Baseline reuse**: Tier 1-4 profiles do not redefine their own baseline from scratch. Each one explicitly references the Tier 0 variant it deviates from (e.g. "built on `tier0-healthy/student.md`"), and section 5 of the schema states that reference plus only the delta. Keeps the deviation model literal and avoids duplicating baseline definitions across profiles.
- **Suicidality**: not a standalone profile. It is a severity overlay/flag that can attach to any Tier 2/3 depression profile (e.g. "MDD severe + active SI"), matching how it presents clinically — almost always a symptom within a depressive episode rather than an isolated condition. Profiles that carry this overlay get the suicidality-specific domain-sensitivity treatment from section 8 in addition to their base symptom set.
- **Rumination**: not a standalone or comorbid profile. It lives only as a dial in the symptom table (present/severity) on any profile — removed from Tier 3 and Tier 4 as separate entries.

## 4. File/folder organization

```
/profiles/
  ProfileStructure.md          <- this file
  00-schema-template.md        <- fill-in template (copied from section 5 below)
  symptom-network-mapping.md   <- shared symptom -> behavior -> feature lookup table
  tier0-healthy/
  tier1-subclinical/
  tier2-clinical/
  tier3-comorbid/
  tier4-edge-cases/
```

This file (`ProfileStructure.md`, inside `/profiles/`) is the single source of truth for the structure, decisions, and schema — there is no separate `/profiles/README.md`. `00-schema-template.md`, alongside it, is just the template from section 5 copied out so individual profile files can be created from it directly; if the template changes, section 5 here is updated first and the copy re-synced.

The `symptom-network-mapping.md` is a single shared lookup table (symptom → behavior → feature), including the domain-category taxonomy referenced by section 8, that individual profiles reference rather than each re-deriving it — **this file now exists** alongside this one. `00-schema-template.md` (the template from section 5, copied out) still needs to be created before or alongside the first profile.

**File naming convention**: `tier<N>-<category>/<condition>-<severity>.md`, e.g. `tier2-clinical/insomnia-severe.md`, `tier0-healthy/student.md`, `tier3-comorbid/depression-gad.md`.

## 5. Profile schema template

```markdown
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
- **If this profile is a standalone non-MDD Tier-2 diagnosis** (insomnia disorder, GAD, social anxiety): use §7 of `symptom-network-mapping.md` instead of the MDD-centric symptom table in section 3 below — those diagnoses have their own DSM-5 criteria and network translation. Sections 3 and 4 below are then skipped entirely; go straight from this section to section 5 (baseline deviation spec), using §7's network translation in place of a section-4 lookup table.
- **If this profile is a Tier 3 comorbid profile** involving insomnia, GAD, or social anxiety alongside depression: use section 3 (MDD table) for the depression side as normal, but also pull the relevant standalone-diagnosis nuance from mapping-file §7 for the comorbid condition's specific symptom — e.g. a depression+insomnia profile should use §7's sleep-initiation vs. sleep-maintenance distinction rather than only the generic "sleep disturbance" row in §3. Note both sources used in section 4.

## 3. Symptom set
Full DSM-5 MDD criteria list (9 items) plus project-relevant additions. Mark each Present/absent (spread) and, if present, severity (depth). Rumination and suicidality are dials/overlays here, not separate profiles — see Key decisions.
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
Not used for standalone non-MDD Tier-2 diagnoses (see section 2) — those go from section 2 straight to section 5, using §7 of the mapping file directly instead of this lookup table.

Otherwise: do not re-derive these here — for every symptom marked Present in section 3, look up its behavior and network feature in [`symptom-network-mapping.md`](symptom-network-mapping.md) and list only the ones that apply to this profile. For Tier 3 comorbid profiles per section 2, also add rows sourced from §7 for the comorbid condition's specific symptom, alongside the §3-sourced rows for the depression side:
| Symptom (from section 3) | Behavior (per mapping file) | Network feature (per mapping file) |
|---|---|---|
| | | |

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
```

## 6. Open questions

1. Do we want explicit within-tier variants for Tier 0 (e.g. student vs. 9-5 worker) from the start, or start with one representative healthy baseline?
2. When trajectory modeling is added later, should it apply per-symptom or per-profile (i.e. do all symptoms in a comorbid profile onset together, or on independent timelines)?
