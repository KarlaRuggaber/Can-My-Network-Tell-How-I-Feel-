# Symptom → Behavior → Network Feature Mapping

Shared reference table for all profiles. Individual profile files (section 4 of the schema) should point back here rather than re-deriving these mappings. See [ProfileStructure.md](ProfileStructure.md) for the overall structure this supports.

## 1. Network feature primitives

The vocabulary used throughout this table, so profiles describe deviations in consistent terms:

- **DNS query volume** — count of queries per hour/session
- **DNS query timing distribution** — how queries are spread across the 24h clock
- **Domain category diversity** — entropy/spread of query targets across categories (see taxonomy below)
- **Domain repeat-visit rate** — how concentrated queries are on a narrow set of domains
- **Session count / session duration** — number and length of active-use bursts
- **Inter-query interval** — time gaps between successive queries within a session
- **Routine stability** — day-to-day variance in the above (wake time, session timing) relative to the person's own baseline
- **Weekday/weekend delta** — difference in any of the above between weekdays and weekends

These are the same primitives referenced by schema section 8 ("synthetic generation parameters") — a profile's generation parameters are the input side, this table's "network feature" column is the expected output side.

## 2. Domain category taxonomy

Used for "domain category mix" in schema section 8 and for the mapping rows below.

| Category | Examples | Sensitivity |
|---|---|---|
| Social / messaging | chat apps, social media | standard |
| Streaming / entertainment | video, music, gaming platforms | standard |
| News | news outlets, aggregators | standard |
| Health / medical (general) | symptom lookup, fitness, telehealth | standard |
| Crisis / self-harm-adjacent | crisis lines, suicide-prevention resources, self-harm-related content | **sensitive — see §5** |
| E-commerce / shopping | retail, food delivery, grocery | standard |
| Work / productivity | email, docs, work tools | standard |
| Search / general | general search engines, uncategorized queries | standard |
| Other / uncategorized | anything not fitting above | standard |

This taxonomy is intentionally coarse — fine enough to distinguish the behaviors below, coarse enough to keep the "grey zone" (Tier 1) profiles plausible against a healthy baseline that also touches most categories.

## 3. Symptom → behavior → network feature table

Observability tag: **Good** (clear, fairly specific signal) / **Partial** (signal present but ambiguous or needs baseline comparison) / **Not observable** (no network trace, listed for honesty per schema section 6).

| Symptom | Behavior | Network feature | Observability |
|---|---|---|---|
| Depressed mood | Reduced motivation to initiate device use across most activities | Overall reduced session count/volume; flatter usage curve across the day; reduced domain category diversity | Partial |
| Anhedonia | Stops engaging with previously frequent entertainment/hobby activity | Drop in streaming/gaming/hobby-domain volume vs. personal baseline | Partial (Good if baseline well-established) |
| Weight/appetite change | Altered food-delivery/grocery browsing (can go either direction) | Change in e-commerce/food-delivery domain queries | Not reliable — too ambiguous to use as a signal on its own |
| Psychomotor agitation/retardation | Physical symptom, no digital behavior correlate | — | Not observable |
| Sleep disturbance (general) | Irregular bed/wake times, fragmented sleep with night wakings | DNS activity appearing outside the person's normal sleep window; increased night-to-night variance in first/last query time | Good |
| Early morning waking (4-5am) | Phone checked specifically 4-5am, brief and repeated | Sharp DNS query burst 04:00-05:30; short session; low domain diversity in that burst | Good — diagnostically specific per clinical input |
| Fatigue / loss of energy | Fewer, shorter active sessions across the day | Reduced total session count/duration; shift toward passive (streaming) vs. interactive domain mix | Partial |
| Feelings of worthlessness / guilt | No digital behavior correlate identified | — | Not observable |
| Concentration difficulty | Frequent app/tab switching, shorter attention per activity | Shorter inter-query intervals; higher domain-switch rate; lower per-domain dwell time; fragmented sessions | Partial |
| Suicidal ideation (overlay, not standalone) | Browsing crisis-adjacent or self-harm-related content, often off-hours | Queries to crisis/self-harm-adjacent category (see §5), frequently late-night | Partial — high sensitivity, handle per §5 |
| Hopelessness (ICD-11-specific) | No distinct digital behavior correlate identified beyond what depressed mood/anhedonia already cover | — | Not observable |
| Social withdrawal | Fewer/no social interactions during normal social hours | Drop in social/messaging-domain volume vs. baseline, most pronounced in evening hours | Good |
| Rumination (symptom-table dial, not a standalone profile) | Repeatedly revisiting the same content/domains | Reduced domain diversity; high repeat-visit rate concentrated on a narrow domain set; longer dwell/reload patterns on the same domains | Partial |
| Anxiety — generalized (GAD) | Compulsive checking of news/health/weather-type information | High-frequency, short queries to news/health-domain categories spread through the day, with spikes around trigger times | Partial |
| Anxiety — social | Avoidance of active social engagement, but possible increased passive monitoring | Social-domain queries still present (passive checking) while interaction-associated traffic (messaging sends, uploads) drops — an asymmetric pattern rather than a simple volume change | Partial — needs more than raw DNS to fully distinguish |

## 4. Composite / derived indicators

These aren't single-symptom rows but cross-cutting indicators referenced by the project's own framing (see [Notes.md](../Notes.md)) and used across multiple profiles:

- **Activity diversity** — breadth of domain categories touched per day; depression profiles generally trend toward *lower* diversity (narrowing of activity) relative to baseline.
- **Routine stability** — consistency of timing (wake time, session start times) day over day; most symptomatic profiles show *increased* variance/instability relative to baseline, with early-morning-waking as the specific exception (which is a stable, recurring shift rather than instability).

## 5. Suicidality domain-sensitivity note

Per clinical input (see [Experts.md](../Experts.md)), DNS queries reveal which sites a person clicks through to even without visibility into search terms — this is the basis for treating crisis/self-harm-adjacent content as its own domain category rather than folding it into general health. Any profile carrying the suicidality overlay must:

- Draw from the dedicated "Crisis / self-harm-adjacent" category in §2, not generic health domains.
- Model this activity as typically off-hours (late-night/early-morning), consistent with the broader sleep-disturbance pattern this population shows.
- Be treated with extra care in documentation and any shared/reviewed material — this is the most clinically sensitive profile category in the project.

## 6. Confounds shared across symptoms

Behaviors above can be produced by non-clinical causes; profiles should note these explicitly in their own schema section 7, but the common ones are listed once here to avoid repeating them everywhere:

- Early/irregular waking → shift work, infant/childcare, jet lag
- Reduced session volume → travel, device change, digital detox, vacation
- Reduced social-domain volume → genuine introversion / low baseline social app use (this is why deviation-from-*personal*-baseline matters, not population norms)
- Increased late-night activity → time-zone-shifted work or study, not necessarily sleep disturbance

## 7. Standalone Tier-2 diagnostic criteria (non-MDD)

Tier 2 includes clinical diagnoses that are not MDD and have their own DSM-5 criteria, distinct from (though overlapping with) the MDD symptom table in §3. Profiles for these should use the criteria and network translation below in place of — not in addition to — treating them as a generic "symptom present" row in the main table. Reuse §3 rows where noted rather than re-deriving them.

**Note on severity:** unlike MDD, DSM-5 does not define an official mild/moderate/severe specifier for any of the three diagnoses below. Where the schema asks for an "Overall severity," treat it as an informal grading for synthetic-generation purposes only, not a cited diagnostic specifier.

### Insomnia Disorder
- **DSM-5 criteria (distinct from MDD's general sleep-disturbance item):** predominant dissatisfaction with sleep quantity/quality, with at least one of: difficulty initiating sleep, difficulty maintaining sleep (frequent awakenings or trouble returning to sleep), or early-morning awakening with inability to return to sleep. Occurs ≥3 nights/week, present ≥3 months, causes distress/impairment, not better explained by another condition.
- **Network translation:**
  - Difficulty initiating sleep, maintaining sleep, early waking → reuse the "Sleep disturbance (general)" and "Early morning waking (4-5am)" rows in §3.
  - Difficulty initiating sleep specifically → extended pre-sleep device use → DNS activity persisting later into the night than the personal baseline (later "last query" timestamp).
  - Difficulty maintaining sleep specifically (frequent awakenings) → several distinct short nocturnal DNS bursts scattered through the night, rather than the single concentrated 04:00-05:30 burst that characterizes early-morning waking alone.

### Generalized Anxiety Disorder (GAD)
- **DSM-5 criteria:** excessive anxiety/worry, more days than not, for ≥6 months, about multiple events/activities, difficult to control, with ≥3 of: restlessness, fatigue, concentration difficulty, irritability, muscle tension, sleep disturbance.
- **Network translation:**
  - Core worry/checking behavior → reuse the "Anxiety — generalized (GAD)" row in §3.
  - Concentration difficulty, fatigue, sleep disturbance (when present as part of the GAD criteria, not comorbid MDD) → reuse those respective §3 rows.
  - GAD-specific nuance: because worry spans "multiple events/activities" rather than one theme, the signal is the *frequency and spread* of short checking-type queries across several unrelated domain categories (news, health, weather, finance) — not concentration in any single category the way rumination narrows to one.

### Social Anxiety Disorder (SAD)
- **DSM-5 criteria:** marked fear/anxiety about social situations involving possible scrutiny by others; fear of acting in a way that will be negatively evaluated; the situations are avoided or endured with intense fear/anxiety, out of proportion to actual threat; persistent ≥6 months; causes distress/impairment.
- **Network translation:**
  - Core avoidance/passive-monitoring pattern → reuse the "Anxiety — social" row in §3.
  - SAD-specific nuance: avoidance is strongest for *synchronous* social contact — expect a disproportionate drop in video/voice-call-associated domains specifically, while asynchronous messaging may stay closer to baseline or even increase slightly as a lower-threat substitute. This distinguishes SAD from general social withdrawal (§3), which drops broadly across all social/messaging categories.
