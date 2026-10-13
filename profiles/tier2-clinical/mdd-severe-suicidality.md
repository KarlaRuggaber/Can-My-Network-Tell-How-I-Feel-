# Profile: MDD severe + suicidality overlay

**Tier:** 2
**Status:** draft
**Baseline reference:** `tier0-healthy/student.md`
**Suicidality overlay:** present (see section 8 suicidality note and mapping file §5)

> **Sensitive profile.** This is the most clinically sensitive profile in the project (mapping file §5). Handle it with extra care in any shared or reviewed material, and get it reviewed by Lukasz before use.

## 1. Identity
The `tier0-healthy/student` baseline, now in a severe major depressive episode with active suicidal ideation (no modeled plan or attempt).

## 2. Diagnostic basis
- Reference criteria: DSM-5 Major Depressive Disorder, single episode, severe (296.23 / F32.2). Requires ≥5 of 9 criteria over 2 weeks, including depressed mood or anhedonia. This profile has 9 of 9. Suicidality = DSM-5 MDD Criterion 9 (thesis Appendix B.9). ICD-11 equivalent: 6A70.3 single episode depressive disorder, severe, without psychotic symptoms. ICD-11 additionally lists hopelessness explicitly.
- Duration window: 2 weeks (DSM-5 default; matches the thesis gate window M=14).
- Overall severity: severe (official DSM-5 MDD specifier).
- Suicidality is modeled as an overlay on MDD, not as a standalone condition (ProfileStructure §3 Key decisions).

## 3. Symptom set
| Symptom | Present? | Severity (mild/mod/severe) | Notes |
|---|---|---|---|
| Depressed mood | yes | severe | |
| Anhedonia (loss of interest/pleasure) | yes | severe | drop in the student's hobby (gaming) |
| Weight/appetite change | yes | mild | weak/unreliable signal only, not used for generation (see section 6) |
| Sleep disturbance (general) | yes | severe | irregular onset, fragmented nights |
| Early morning waking (4-5am) | yes | moderate | 3–4 days/week |
| Psychomotor agitation/retardation | yes | moderate | not network-observable |
| Fatigue / loss of energy | yes | severe | |
| Feelings of worthlessness/guilt | yes | severe | not network-observable |
| Concentration difficulty | yes | moderate | scripted as fragmented phone checks (many pages, short dwell) |
| Suicidal ideation | yes | moderate | active ideation, no plan; see section 8 suicidality note |
| Hopelessness | yes | severe | ICD-11-specific; not network-observable |
| Social withdrawal | yes | severe | |
| Rumination | yes | moderate | |
| Anxiety — generalized (GAD) | no | | |
| Anxiety — social | no | | |

## 4. Behavioral & network translation
All rows from [`symptom-network-mapping.md`](../symptom-network-mapping.md) §3, for observable symptoms marked present:
| Symptom (from section 3) | Behavior (per mapping file) | Network feature (per mapping file) | Thesis criterion (metrics) |
|---|---|---|---|
| Depressed mood | Reduced motivation to initiate device use across most activities | Overall reduced session count/volume; flatter usage curve; reduced domain category diversity | C1 (`F7_HourlyCV`, `F8_NightDayRatioPkts`, `F4_DownUpRatio`) |
| Anhedonia | Stops engaging with previously frequent entertainment/hobby activity | Drop in streaming/gaming/hobby-domain volume vs. personal baseline | C2 (`C2_F1_UniqueSLD`, `C2_F5`); the gaming drop has no own metric |
| Sleep disturbance (general) | Irregular bed/wake times, fragmented sleep with night wakings | DNS activity outside the normal sleep window; more night-to-night variance in first/last query time | C4 (`C4_F4`, `C4_F8`, `C4_F1`, `C4_F5`) + C1 (`F8_NightDayRatioPkts`) |
| Early morning waking | Phone checked specifically 4–5am, brief and repeated | Sharp DNS burst 04:00–05:30; short session; low domain diversity | only via `C1_F8` / `C4_F8`; it *lowers* `C4_F2` and `C6_F8` (thesis-alignment B5) |
| Fatigue / loss of energy | Fewer, shorter active sessions | Reduced total session count/duration; shift toward passive (streaming) vs. interactive domains | C6 (`C6_F8_FirstActivityMin`, `C6_F9_ActivationDelayVsBase28d`) |
| Concentration difficulty | Frequent switching, short attention per activity | Shorter inter-query intervals; higher domain-switch rate; fragmented sessions | C8 (`C8_F2_DNSBurstRatePerHour`, `C8_F8_MedianIKSsec`) |
| Suicidal ideation (overlay) | Browsing crisis-adjacent or self-harm-related content, often off-hours | Queries to the crisis/self-harm-adjacent category (mapping §5), mostly late night | C9 flag (`C9_F1_CrisisLineHits`); help-line visits may also hit the thesis's C7 help-line metric |
| Social withdrawal | Fewer/no social interactions during normal social hours | Drop in social/messaging volume, strongest in the evening | C1 (`F1_DistinctSocial`) + C2 (`C2_F3_ChatSessionCount`, `C2_F4_MeanUpstreamRateBps`) |
| Rumination | Repeatedly revisiting the same content/domains | Reduced diversity; high repeat-visit rate on a narrow domain set | C8 (`C8_F4_RepeatedQueryRatio60m`) |

No new profile-specific rows were needed.

## 5. Baseline deviation spec
- **Personal baseline**: inherited from `tier0-healthy/student.md`, not redefined here.
- **Deviation pattern** (all relative to that baseline, steady over the 14 days):
  - **Overall activity:** total session count **−30 to −40%**, daytime usage curve flatter (lower peaks).
  - **Domain diversity:** unique SLDs/day **−40 to −50%**. The remaining traffic concentrates on a few domains (repeat-visit rate ↑).
  - **Anhedonia:** the baseline's hobby (gaming) **−60 to −80%**. Passive streaming is *not* reduced; it replaces the hobby (next point).
  - **Passive shift:** remaining traffic shifts toward long passive streaming sessions, mostly late evening/night.
  - **Social withdrawal:** social/messaging volume **−50 to −70%**, strongest 18:00–23:00. Outgoing/upstream social traffic drops more than incoming.
  - **Study/productivity domains** (LMS, email, docs): **−50 to −70%**.
  - **Campus attendance:** about half of the lecture days are skipped. The person stays home with low activity (connected but mostly idle) instead of being away.
  - **Concentration:** daytime phone checks become fragmented: 3–6 pages per check with only 5–20 s each, instead of 1–3 pages with 20–90 s.
  - **Sleep:** sleep onset later by 0–150 min and more irregular (variance ×3, i.e. SD ×1.7); 4–6 nights per 14 days with an awakening and passive use 02:00–03:30; early-waking burst 04:00–05:15 on 3–4 days/week; later irregular first daytime activity on remaining days.
  - **Suicidality overlay:** crisis/self-harm-adjacent category queries on **2–4 days of the 14-day window**, clustered **23:00–04:00**, short sessions, often preceded by a rumination-like repeat-visit sequence (see section 8 note).
  - **Weekday/weekend delta:** strongly reduced (days look alike, structure collapses).
- **Expected effect on thesis criteria:** see section 9, "Expected thesis output".
- **Trajectory**: static steady-state (default). MDD onset is a first candidate for a later onset curve, see ProfileStructure §3.

## 6. Non-observable symptoms
- Feelings of worthlessness/guilt, hopelessness, psychomotor agitation/retardation: no network correlate.
- Weight/appetite change: weak and ambiguous correlate via food-delivery domains, not used as a signal.
- **Suicidal ideation without help-seeking or browsing.** Ideation that never leads to a related site visit, or happens on mobile data/another network, is invisible. Absence of crisis-category traffic must never be read as absence of risk.

## 7. Confounds / ambiguity notes
- Shared confounds from mapping file §6: travel or vacation (reduced volume), exam/thesis crunch (night activity, reduced social), introversion.
- **Crisis-category queries have non-risk explanations:** supporting a friend or family member, psychology/medicine coursework, research, journalism, awareness campaigns. Crisis-line visits are also **help-seeking, a protective factor**, not only a risk marker.
- **DoH/encrypted DNS, VPNs, mobile data:** can hide exactly the most sensitive queries. SNI capture helps, but coverage is never complete.
- Early waking burst vs. shift work or childcare (mapping §6).
- **Ethics:** a real deployment that can detect this pattern raises a duty-of-care question (who is informed, how fast, with what consent). This must be settled in the study protocol before any real data is collected. It is out of scope for synthetic generation, but belongs in the limitations discussion.

## 8. Synthetic generation parameters
| Parameter | Baseline (from student) | This profile |
|---|---|---|
| Sleep onset (last query) | baseline mean ± baseline SD | baseline + U(0, 150) min, SD ×1.7 (variance ×3) |
| Wake / first query | baseline | early-waking burst starting 04:00–05:00 on 3–4 days/week (only after nights with sleep onset ≤ 02:30); other days baseline + U(30, 150) min |
| Nocturnal activity after 02:00 | rare | 4–6 nights per 14 days, an awakening with passive streaming/social 02:00–03:30 (only after nights with sleep onset ≤ 01:30) |
| DNS query rate curve, 24h | baseline | flatter daytime curve (peaks ×0.6), raised late-night plateau |
| Domain category mix | baseline | streaming (passive) ↑, social ↓, productivity ↓, hobby category ↓, + crisis category (see note) |
| Unique domains/day | baseline | baseline × U(0.5, 0.6) |
| Repeat-visit rate | baseline | ×1.5–2 |
| Session count/length | baseline | count × U(0.6, 0.7); fewer but longer passive sessions at night, shorter fragmented ones by day (3–6 pages, 5–20 s dwell) |
| Day-to-day noise | baseline | ×2 in timing features |
| Weekday vs. weekend modifier | baseline | weekend wake/sleep follow the weekday (lecture_late / Sun–Thu) distributions; no outings → structure collapses |

**Suicidality-specific note (mapping file §5):**
- The crisis/self-harm-adjacent category is generated as its **own stream**, separate from and never mixed into the generic "health" category.
- **Help-seeking domains** for the synthetic set: Swiss crisis and prevention resources (e.g. Die Dargebotene Hand `143.ch`, Pro Juventute `147.ch`, national suicide-prevention information sites).
- **Self-harm-adjacent content** is represented only by **placeholder domain labels** (e.g. `sh-adjacent-01.invalid`). No real harmful domains are written into this repository.
- Timing: 2–4 days per 14-day window, sessions 2–10 min, 23:00–04:00, 1–3 domains per session, often directly after 10+ min of repeat visits to a narrow set of domains (rumination dial).

## 9. Script specification
Patch on [`tier0-healthy/student.md`](../tier0-healthy/student.md) §9. Activity IDs and notation: [`activity-catalog.md`](../activity-catalog.md). Applies to all 14 days (static steady state).

```yaml
profile: tier2-clinical/mdd-severe-suicidality
extends: tier0-healthy/student

modify:
  # sleep
  anchors.sleep:  {shift: 'U(0m, 150m)', sd: "× 1.7"}           # variance × 3
  anchors.wake:   {shift: 'U(30m, 150m)'}                      # on days without early waking
  # activity collapse
  day_checks:     {count: "baseline × U(0.6, 0.7)", mix: {social_passive: .5, streaming: .3, messaging: .1, news: .1},
                   pages: 3-6, dwell: 5-20s}                  # concentration: fragmented checks
  messaging_day:  {count: "baseline × U(0.3, 0.5)"}          # social withdrawal
  evening_social: {count: "baseline × U(0.3, 0.5)"}
  social_post:    {per_window: 0-1}                          # active social use almost gone
  family_call:    {duration: "× 0.6"}                        # usually kept, shorter
  group_call:     {per_week: "baseline × 0.3"}
  study_home:     {duration: "× U(0.3, 0.5)"}                # productivity −50 to −70 %
  study_am:       {duration: "× U(0.3, 0.5)"}
  study_pm:       {duration: "× U(0.3, 0.5)"}
  gaming:         {per_week: "baseline × U(0.2, 0.4)", voice: false}   # anhedonia: hobby −60 to −80 %
  evening_stream: {duration: 90-180m, may_cross_midnight: true}         # passive shift
  weekend_slow:   {duration: "× 1.5"}

remove_away:
  going_out:   {keep_per_window: 0}
  weekend_out: {keep_per_window: 0-1}
  campus:      {attend_share: 0.5}                           # skipped days: at home, idle_connected + day_checks only

add:
  - {id: early_waking, days_per_week: 3-4, at: 'U("04:00", "05:00")', device: phone,
     only_if: "sleep onset of that night <= 02:30",
     activity: phone_check, duration: 3-15m, pages: 1-2, mix: {social_passive: .6, news: .4},
     then: "idle_connected until wake (no return to normal sleep in the data)"}
  - {id: night_passive, nights_per_window: 4-6, within: ["02:00", "03:30"], device: phone,
     only_if: "sleep onset of that night <= 01:30",
     activity: social_passive, duration: 20-60m, mix: {social_passive: .5, streaming: .5}}
  - {id: rumination, count_per_day: 1-2, within: ["14:00", "02:00"], device: phone,
     activity: repeat_visit_loop, duration: 10-30m, mix: {social_passive: .6, news: .4}}

suicidality_overlay:                                          # see section 8 note and mapping file §5
  episodes_per_window: 2-4                                    # on different days
  within: ["23:00", "04:00"]
  sequence:
    - {activity: repeat_visit_loop, duration: 10-20m, probability: 0.7}   # "often" preceded by rumination
    - {activity: crisis_resource_visit, duration: 2-10m, mix: {crisis_help: 1}, pages: 1-3}
    - {activity: sh_adjacent_lookup, probability: 0.5, lookups: 1-3}   # DNS-only placeholders, never real domains
  log_flag: sensitive                                         # mark these rows in the ground-truth log

weekend_anchors: "same distributions as lecture_late wake / nights_sun_to_thu sleep, after the modifications above"   # structure collapses: weekends look like weekdays
```

**Expected thesis output** vs. the student baseline, with the calibrated gateway config (scoring rules and issues B1–B9: [`thesis-alignment.md`](../thesis-alignment.md)).

| Criterion | Thesis metrics this profile moves | Expected | Present? |
|---|---|---|---|
| C1 depressed mood | `F8_NightDayRatioPkts` ↑↑; `F7_HourlyCV` ↓ (flatter day) and `F1_DistinctSocial` ↓, both scored correctly only after the direction fix (B9); `F4_DownUpRatio` ↑ (check that it stays below `hi`: heavy passive streaming can push it out of the band, B4) | ↑↑ | **present** |
| C2 anhedonia (core) | `C2_F1` ↓, `C2_F6` ↓, `C2_F3` ↓, `C2_F4` ↓ (all inverted → μ ↑) | ↑↑ | **present** |
| C3 appetite | — (mild, not scripted) | ≈ baseline | no |
| C4 sleep | `C4_F1` later, `C4_F5` ↑, `C4_F8` ↑, `C4_F4` ↑ (needs the baseline period, B7) | ↑↑ | **present** |
| C5 psychomotor | — (not observable, not scripted) | ≈ baseline | no |
| C6 fatigue | `C6_F8_FirstActivityMin` +30–150 min on days without early waking; `C6_F9` ↑ (needs the baseline period). Early-waking days (6–8 of 14) *lower* `C6_F8` (B5). | ↑ on ~6–8 days | **borderline** (N = 6) |
| C7 worthlessness | — (not observable). Help-line visits may raise the thesis's C7 help-line metric (unintended). | ≈ baseline | no |
| C8 concentration | `C8_F2` ↑ (fragmented checks), `C8_F4` ↑ (rumination loops) | ↑ | **present**, if the re-tuned bands sit above the baseline |
| C9 suicidality | `C9_F1_CrisisLineHits` > 0 on 2–4 days | episodic | **flag** (outside the gate, B8) |

**Episode:** **borderline.** C1, C2, C4 and C8 are present (4, including the core C2), so a 5th criterion is needed, and only C6 can supply it. If C6 doesn't make it, that's a **sensitivity finding** (thesis-alignment §5), not a profile error. Don't strengthen the profile just to make the gate fire.
**Original thesis config:** no episode (B1); C2 can't reach θ, so the core is never present (B2).
