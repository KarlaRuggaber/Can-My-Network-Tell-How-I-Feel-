# Profile: Insomnia Disorder (moderate)

**Tier:** 2
**Status:** draft
**Baseline reference:** `tier0-healthy/9to5-worker.md`
**Suicidality overlay:** none

## 1. Identity
The `tier0-healthy/9to5-worker` baseline, now presenting moderate insomnia disorder with combined sleep-initiation and sleep-maintenance difficulty. The fixed, alarm-bound weekday wake time stays intact, so the shortened night shows up clearly in the data.

## 2. Diagnostic basis
- Reference criteria: DSM-5 Insomnia Disorder (307.42 / F51.01). ICD-11 equivalent: 7A00 Chronic insomnia. Subtype modeled: **difficulty initiating sleep + difficulty maintaining sleep**. Early-morning awakening is deliberately **absent**, which keeps this profile distinguishable from the MDD early-waking signature (mapping file §3, "Early morning waking").
- Duration window: DSM-5 requires ≥3 nights/week for ≥3 months. The profile assumes the person is already in the chronic state. We generate a **14-day window** (matches the thesis gate window M=14) as a slice of that state, not as the full diagnostic duration.
- Overall severity: moderate (informal grading for synthetic generation only, not a DSM-5 specifier, see mapping file §7).
- Standalone non-MDD Tier-2 diagnosis → section 3 adds the Insomnia Disorder criteria to the MDD table, and section 4 uses the network translation from mapping file §7 "Insomnia Disorder".

## 3. Symptom set
MDD table first (for comparison with the depression profiles), then the Insomnia Disorder criteria from mapping file §7.

| Symptom | Present? | Severity (mild/mod/severe) | Notes |
|---|---|---|---|
| Depressed mood | no | | |
| Anhedonia (loss of interest/pleasure) | no | | |
| Weight/appetite change | no | | |
| Sleep disturbance (general) | yes | moderate | specified by the insomnia rows below |
| Early morning waking (4-5am) | no | | deliberately absent, keeps the profile distinct from MDD |
| Psychomotor agitation/retardation | no | | |
| Fatigue / loss of energy | yes | mild | part of the DSM-5 daytime impairment criterion; weak, optional in the script (off by default) |
| Feelings of worthlessness/guilt | no | | |
| Concentration difficulty | yes | mild | part of daytime impairment; not scripted (no reliable signal at this severity) |
| Suicidal ideation | no | | |
| Hopelessness | no | | |
| Social withdrawal | no | | |
| Rumination | no | | |
| Anxiety — generalized (GAD) | no | | |
| Anxiety — social | no | | |
| **Insomnia Disorder criteria (DSM-5, mapping file §7)** | | | |
| Dissatisfaction with sleep quantity/quality | yes | moderate | core criterion; subjective, not network-observable |
| Difficulty initiating sleep | yes | moderate | +60–120 min later sleep onset on symptomatic nights |
| Difficulty maintaining sleep (frequent awakenings) | yes | moderate | 2–4 (mostly 2–3) short awakenings per symptomatic night |
| Early-morning awakening with inability to return to sleep | no | | |
| Frequency: ≥3 nights/week | yes | | 4 ± 1 symptomatic nights per week |
| Duration: ≥3 months | yes | | assumed; the script generates a 14-day slice |
| Distress / daytime impairment | yes | mild | covered by the fatigue and concentration rows above |

## 4. Behavioral & network translation
Rows from mapping file §7 "Insomnia Disorder" and the §3 rows it reuses. Source in brackets.

| Symptom (from section 3) | Behavior (per mapping file) | Network feature (per mapping file) | Thesis criterion (metrics) |
|---|---|---|---|
| Sleep disturbance (general) [§3] | Irregular bed/wake times, fragmented sleep with night wakings | DNS activity outside the person's normal sleep window; increased night-to-night variance in first/last query time | C4 (`C4_F4`, `C4_F8`, `C4_F1`, `C4_F5`) + C1 (`F8_NightDayRatioPkts`) |
| Difficulty initiating sleep [§7] | Extended pre-sleep device use | DNS activity persisting later into the night than the personal baseline (later "last query" timestamp) | C4 (`C4_F1` onset, `C4_F8`); C1 (`F8_NightDayRatioPkts`) once onset is after midnight |
| Difficulty maintaining sleep [§7] | Frequent awakenings with brief phone use | Several distinct short nocturnal DNS bursts scattered through the night, not one concentrated 04:00–05:30 burst | C4 (`C4_F5` micro-sessions, `C4_F6`, `C4_F4`); C1 (`F8_NightDayRatioPkts`) |
| Fatigue / loss of energy [§3] | Fewer, shorter active sessions across the day | Reduced total session count/duration (here only −10% in the afternoon, optional) | C6 (`C6_F8`). Weekday wake is unchanged, so no C6 signal is expected |

No new profile-specific rows were needed.

## 5. Baseline deviation spec
- **Personal baseline**: inherited from `tier0-healthy/9to5-worker.md`, not redefined here.
- **Deviation pattern**:
  - **Symptomatic nights:** 4 ± 1 of 7 nights per week (DSM-5 minimum is 3), placed randomly. All other nights follow the baseline.
  - **Sleep initiation (symptomatic nights):** last query shifts **+60 to +120 min** later than the baseline last query. The extra time is one continuous, low-intensity session (streaming, social, search) rather than an active work session.
  - **Sleep maintenance (symptomatic nights):** **2–4 (mostly 2–3) short nocturnal bursts** (80% of them 2–5 min, 20% 5–8 min; ≤5 min is what the thesis counts as a nocturnal micro-session, C4_F5) between 01:00 and 04:00, at least 30 min after sleep onset, scattered at random and separated by ≥30 min of silence. Low domain diversity per burst (1–3 domains, mostly social/news).
  - **Weekday wake time:** unchanged (alarm-bound). The weekday signal is therefore *shortened sleep opportunity*, not a later wake.
  - **Weekend wake time:** +60 to +120 min later than the baseline weekend wake (catch-up sleep). This widens the weekday/weekend delta.
  - **Daytime:** close to baseline. Optional weak fatigue effect: −10% session count in the afternoon (14:00–17:00), only on home-office and weekend days (on office days the baseline has no home traffic during the day). Kept small on purpose, so the profile stays "sleep-dominant".
- **Expected effect on thesis criteria:** see section 9, "Expected thesis output".
- **Trajectory**: static steady-state (default). Insomnia is a first candidate for a later onset curve, see ProfileStructure §3.

## 6. Non-observable symptoms
- **Lying awake without the phone.** Any wakeful period without device use leaves no trace. A person with severe insomnia who never touches the phone at night is invisible to this system. This is the main limitation of this profile.
- Subjective dissatisfaction with sleep quality/quantity and the distress it causes (core DSM-5 criterion, purely subjective).
- Most daytime impairment (irritability, reduced performance), apart from the weak fatigue effect in section 5.

## 7. Confounds / ambiguity notes
- Shared confounds from mapping file §6: late-night activity from time-zone-shifted work, night shifts, infant/childcare (nocturnal bursts), travel.
- **Background traffic at night:** push/keep-alive traffic (APNs 5223, iCloud, OS updates) can look like nocturnal bursts. Filtering is required before generation and analysis are compared. This is the same "never silent" artifact the thesis hit with Dataset B (C4_F2).
- **Household-level vantage:** a nocturnal burst might come from another household member's device unless traffic is split per device (MAC).
- One-off late nights (social evening, series binge, deadline) look like sleep-initiation difficulty on a single day. The ≥3 nights/week regularity is what separates them.
- vs. MDD: insomnia alone keeps daytime domain diversity and social traffic near baseline and has no 04:00–05:30 early-waking burst.

## 8. Synthetic generation parameters
| Parameter | Baseline (from 9to5-worker) | This profile |
|---|---|---|
| Last query (sleep onset), symptomatic nights | baseline mean ± baseline SD | baseline + U(60, 120) min |
| Nocturnal bursts per symptomatic night | 0 | 2–4 (Poisson λ≈2.5, clipped to [2, 4]), duration 80% U(2,5) min / 20% U(5,8) min, between 01:00–04:00, ≥30 min after sleep onset |
| Weekday wake / first query | baseline | unchanged |
| Weekend wake / first query | baseline | baseline + U(60, 120) min |
| DNS query rate curve, 24h | baseline curve | baseline + low plateau in the pre-sleep extension + spikes at burst times |
| Domain category mix (night) | n/a | social 40%, streaming 30%, news 15%, search/other 15% |
| Domain category mix (day) | baseline | baseline |
| Session count/length (day) | baseline | −10% count, 14:00–17:00 only (optional) |
| Symptomatic nights per week | 0 | 4 ± 1, random placement |
| Day-to-day noise | baseline | night timing becomes more variable through the random placement of symptomatic nights and the U(60, 120) shift; daytime unchanged |
| Weekday vs. weekend modifier | baseline | weekend catch-up shift as above |

## 9. Script specification
Patch on [`tier0-healthy/9to5-worker.md`](../tier0-healthy/9to5-worker.md) §9. Activity IDs and notation: [`activity-catalog.md`](../activity-catalog.md).

```yaml
profile: tier2-clinical/insomnia-moderate
extends: tier0-healthy/9to5-worker

symptomatic_nights:
  per_week: 'N(4, 1) clipped to [3, 5]'     # DSM-5 minimum 3
  placement: random                        # night of day d = day d 22:00 -> day d+1 06:00
  # all other nights: baseline unchanged

on_symptomatic_nights:
  modify:
    anchors.sleep: {shift: 'U(60m, 120m)'}                  # later sleep onset
    bedtime_check: {at: sleep - 15m}                       # follows the shifted anchor
  add:
    - {id: presleep_extension, from: baseline_sleep, to: sleep, device: phone,
       activity: social_passive, mix: {social_passive: .4, streaming: .3, news: .15, search: .15},
       note: "continuous low-intensity use from the baseline sleep time to the shifted one"}
    - {id: night_bursts, count: 'Poisson(2.5) clipped to [2, 4]', within: ["01:00", "04:00"],
       min_gap: 30m, min_after_sleep: 30m, device: phone, activity: phone_check,
       duration: {p: [.8, .2], values: ['U(2m, 5m)', 'U(5m, 8m)']},
       mix: {social_passive: .5, news: .3, messaging: .2}, pages: 1-3}
  forbid:
    - {within: ["04:00", "05:30"], reason: "no early-morning-waking burst; keeps the profile distinct from MDD"}

on_weekdays:
  modify:
    anchors.wake: unchanged                                # alarm-bound, shortened night is the signal

on_weekends:
  modify:
    anchors.wake: {shift: 'U(60m, 120m)'}                    # catch-up sleep (all weekends, not only symptomatic)

daytime_fatigue:                                           # optional, off by default in the first run
  enabled: false
  scale: {day_checks: 0.9, weekend_checks: 0.9}            # only 14:00-17:00 on home-office and weekend days
```

**Expected thesis output** vs. the 9-to-5 baseline, with the calibrated gateway config (scoring rules and issues B1–B9: [`thesis-alignment.md`](../thesis-alignment.md)). A symptomatic night mostly lands in the *next* calendar day (activity after midnight), so the signal shows on the day after.

| Criterion | Thesis metrics this profile moves | Expected | Present? |
|---|---|---|---|
| C1 depressed mood | `F8_NightDayRatioPkts` ↑ after each symptomatic night | ↑, but `F8` has weight 0.35 and can't reach θ = 0.6 alone | **no** (elevated) |
| C2 anhedonia | — | ≈ baseline | no. If C2 rises, the profile is leaking into "depression". |
| C4 sleep | `C4_F1` onset +60–120 min, `C4_F5` ≈ 2–3 micro-sessions (only bursts ≤ 5 min count), `C4_F8` ↑, `C4_F4` ↑ (needs the baseline period, B7) | ↑ on the 8 ± 2 days after symptomatic nights | **present** (≥ 6 of 14 days) |
| C6 fatigue | `C6_F8` | weekdays unchanged (alarm); later only on weekends (catch-up) | no |
| C8 concentration | — | ≈ baseline | no |
| C3, C5, C7, C9 | — | not scripted | no |

**Episode:** no (1 criterion present). That's the correct result: insomnia isn't depression.
**Reportable:** the thesis reads insomnia as "sleep criterion plus some depressed-mood evidence", because the night/day ratio sits in C1. That's a misattribution (B6).
**Original thesis config:** an episode is impossible (B1), and C4 can't be interpreted (B3). After a symptomatic night there is activity after midnight, so `C4_F2` takes the first evening packet as "wake".
