# Profile: Social Anxiety Disorder (moderate)

**Tier:** 2
**Status:** draft
**Baseline reference:** `tier0-healthy/student.md`
**Suicidality overlay:** none

## 1. Identity
The `tier0-healthy/student` baseline, now presenting moderate social anxiety disorder: avoids synchronous social contact (calls, video, going out) but keeps passively following others online.

## 2. Diagnostic basis
- Reference criteria: DSM-5 Social Anxiety Disorder (300.23 / F40.10). ICD-11 equivalent: 6B04 Social anxiety disorder (criteria largely aligned).
- Duration window: DSM-5 requires ≥6 months. The profile assumes the person is already in that state. We generate a **14-day window** as a slice of it.
- Overall severity: moderate (informal grading for synthetic generation only, not a DSM-5 specifier, see mapping file §7).
- Standalone non-MDD Tier-2 diagnosis → section 3 adds the Social Anxiety Disorder criteria to the MDD table, and section 4 uses the network translation from mapping file §7 "Social Anxiety Disorder".

## 3. Symptom set
MDD table first (for comparison with the depression profiles), then the Social Anxiety Disorder criteria from mapping file §7.

| Symptom | Present? | Severity (mild/mod/severe) | Notes |
|---|---|---|---|
| Depressed mood | no | | |
| Anhedonia (loss of interest/pleasure) | no | | hobbies (gaming, streaming) stay at baseline; only the voice chat is dropped |
| Weight/appetite change | no | | |
| Sleep disturbance (general) | no | | |
| Early morning waking (4-5am) | no | | |
| Psychomotor agitation/retardation | no | | |
| Fatigue / loss of energy | no | | |
| Feelings of worthlessness/guilt | no | | |
| Concentration difficulty | no | | |
| Suicidal ideation | no | | |
| Hopelessness | no | | |
| Social withdrawal | no | | not *general* withdrawal: messaging and passive social use stay or rise. The avoidance is specific, see the SAD rows below |
| Rumination | no | | |
| Anxiety — generalized (GAD) | no | | |
| Anxiety — social | yes | moderate | specified by the SAD rows below |
| **Social Anxiety Disorder criteria (DSM-5, mapping file §7)** | | | |
| Fear/anxiety about social situations with possible scrutiny | yes | moderate | core criterion; not network-observable |
| Fear of acting in a way that is negatively evaluated | yes | moderate | not network-observable |
| Avoidance of synchronous contact (calls, video, voice chat) | yes | moderate | calls −60 to −80%, voice chat while gaming dropped, camera off in mandatory calls |
| Avoidance of in-person social situations | yes | moderate | going-out evenings 2–4 → 0–1 per 14 days |
| Reduced active social participation (posting) | yes | moderate | posts/uploads −40 to −60% |
| Passive monitoring / asynchronous substitute | yes | mild | passive social use and text messaging stay at baseline or rise slightly |
| Situations endured with intense distress (instead of avoided) | yes | mild | mandatory calls still happen; the distress itself is not network-observable |
| Duration: ≥6 months | yes | | assumed; the script generates a 14-day slice |

## 4. Behavioral & network translation
Rows from mapping file §7 "Social Anxiety Disorder" and the §3 row it reuses. Source in brackets.

| Symptom (from section 3) | Behavior (per mapping file) | Network feature (per mapping file) | Thesis criterion (metrics) |
|---|---|---|---|
| Anxiety — social [§3] | Avoidance of active social engagement, but possible increased passive monitoring | Social-domain queries still present while interaction-associated traffic drops — asymmetric pattern, not a simple volume change. In this profile the drop is in uploads and calls; text messaging stays (§7 nuance, next row) | no own criterion (thesis is MDD-only); shows as C1 (`F4_DownUpRatio`) + C2 (`C2_F4_MeanUpstreamRateBps`) |
| Avoidance of synchronous contact [§7] | Fewer video/voice calls; asynchronous messaging as lower-threat substitute | Disproportionate drop in video/voice-call traffic (long bidirectional UDP flows), messaging near baseline or slightly up | C2 (`C2_F4_MeanUpstreamRateBps`), C1 (`F4_DownUpRatio`) |
| Avoidance of in-person social situations [§7] | Stays home during the baseline's usual going-out times | Device on the home network during the baseline's going-out evenings, with solitary activity (streaming, gaming without voice) | none directly; side effect on C1 (`F8_NightDayRatioPkts`) and C4 (`C4_F8`) on former going-out nights |
| Reduced active social participation [§7] | Fewer posts, uploads and stories | Upstream byte share on social domains drops while DNS volume stays flat (needs the up/down direction split) | `C2_F7_SocialOutgoingShareUp` (computed, not configured); C2 (`C2_F4`) |
| Passive monitoring [§3, §7] | Scrolling and reading instead of interacting | Social-domain DNS volume unchanged or slightly up | C1 (`F1_DistinctSocial`), expected unchanged |

No new profile-specific rows were needed (the in-person avoidance and upstream-share rows were added to mapping file §7 earlier).

## 5. Baseline deviation spec
- **Personal baseline**: inherited from `tier0-healthy/student.md`, not redefined here.
- **Deviation pattern**:
  - **Video/voice calls** (e.g. WhatsApp/FaceTime/Teams/Zoom call traffic, long bidirectional UDP flows): **−60 to −80%** in session count. Mandatory calls (e.g. a required online seminar) stay, but are shorter, and the upstream share drops (camera/mic off).
  - **Asynchronous messaging** (chat apps): **0 to +15%** in volume. It works as a lower-threat substitute.
  - **Social media, passive:** DNS volume to social domains **unchanged to +20%** (passive scrolling/monitoring).
  - **Social media, active:** **upstream byte share** on social domains **−40 to −60%** (fewer posts, uploads, stories). Needs the up/down direction split the thesis pipeline already computes, not DNS alone.
  - **Presence at home during going-out times:** the baseline student is away (no home traffic) on 1–2 evenings per week, mostly Thu–Sat 20:00–01:00. This profile is **at home on most of those evenings** (0–1 of the baseline's 2–4 outings per 14 days remain), with solitary activity (streaming, gaming without voice chat).
  - **Weekend:** weekday/weekend delta shrinks. Weekends look like weekdays, without the baseline's social evening peaks.
  - **Sleep, overall domain diversity, study/productivity domains:** baseline (keeps the profile distinct from MDD and general social withdrawal).
- **Expected effect on thesis criteria:** see section 9, "Expected thesis output".
- **Trajectory**: static steady-state (default).

## 6. Non-observable symptoms
- The fear/anxiety itself, physical symptoms (blushing, trembling), anticipatory worry.
- Situations that are **endured with intense distress rather than avoided** (DSM-5 allows both). A person who still attends every call and outing produces no signal.
- Avoidance of in-person contact at university or work (happens outside the home network).

## 7. Confounds / ambiguity notes
- Shared confound from mapping file §6: genuine introversion or a low baseline use of calls. This is why only deviation from the *personal* baseline counts.
- **Mobile data:** calls and outings made on mobile data, outside the home Wi-Fi, are invisible. Less call traffic at home does not mean fewer calls.
- **Other networks/devices:** calls might happen on a laptop at the university or on a roommate's device.
- Exam periods, illness and saving money all reduce going-out evenings without social anxiety.
- **vs. general social withdrawal (MDD):** withdrawal drops *all* social/messaging traffic. SAD drops synchronous and active traffic but keeps or increases passive and asynchronous traffic. This asymmetry is the key separator and the reason this profile needs direction (up/down) and flow-type features, not just DNS counts.

## 8. Synthetic generation parameters
| Parameter | Baseline (from student) | This profile |
|---|---|---|
| Wake/sleep time | baseline | unchanged |
| Video/voice-call sessions per week | baseline | baseline × U(0.2, 0.4); remaining calls −30% duration, upstream share −50% |
| Async messaging volume | baseline | baseline × U(1.0, 1.15) |
| Social-domain DNS volume (passive) | baseline | baseline × U(1.0, 1.2) |
| Social-domain upstream byte share | baseline | baseline × U(0.4, 0.6) |
| Going-out evenings away from home (Thu–Sat) | 1–2 per week | 0–0.4 per week; replaced by home sessions 20:00–01:00 (streaming 50%, gaming without voice 30%, social passive 20%) |
| Domain category mix (overall) | baseline | baseline, with weight moved from calls to social-passive/streaming |
| Session count/length | baseline | baseline (+ extra evening sessions as above) |
| Day-to-day noise | baseline | baseline |
| Weekday vs. weekend modifier | baseline | weekend social peak removed (through the dropped going-out evenings); wake/sleep anchors unchanged |

## 9. Script specification
Patch on [`tier0-healthy/student.md`](../tier0-healthy/student.md) §9. Activity IDs and notation: [`activity-catalog.md`](../activity-catalog.md). Applies to all 14 days (static, no symptomatic/non-symptomatic split).

```yaml
profile: tier2-clinical/social-anxiety-moderate
extends: tier0-healthy/student

modify:
  # synchronous contact: avoided or reduced
  group_call:   {per_week: "baseline × U(0.2, 0.4)",      # ≈ 0-1 per week, only mandatory ones
                 camera: false, mic: "on only 10% of the time", duration: "× 0.7"}
  family_call:  {activity: voice_call, duration: "× 0.7"}  # kept (low-threat), but no camera
  gaming:       {voice: false}                             # same sessions, no voice chat
  # asynchronous / passive: kept or increased
  messaging_day:  {count: "baseline × U(1.0, 1.15)"}
  evening_social: {count: "baseline × U(1.0, 1.2)"}
  day_checks:     {mix: {messaging: .35, social_passive: .55, news: .05, search: .05}}
  # active social use: reduced
  social_post:    {per_week: "baseline × U(0.4, 0.6)"}     # ≈ 2-4 per week

remove_away:
  going_out: {keep_per_window: 0-1}                        # baseline 2-4 per 14 days -> 0-1

add:
  - {id: home_instead_of_out, replaces: going_out, from: 'N("20:00", 30m)', to: 'N("01:00", 45m)',
     device: laptop, split: {video_stream: .5, gaming_session: .3, social_passive: .2},
     gaming_voice: false,
     note: "same evenings the baseline would be out; solitary activity at home"}

unchanged:
  - anchors (wake/sleep), campus away blocks, weekend_out, study blocks, domain diversity
```

**Expected thesis output** vs. the student baseline, with the calibrated gateway config (scoring rules and issues B1–B9: [`thesis-alignment.md`](../thesis-alignment.md)).

| Criterion | Thesis metrics this profile moves | Expected | Present? |
|---|---|---|---|
| C1 depressed mood | `F4_DownUpRatio` ↑ (fewer calls, no voice chat, fewer uploads); `F8_NightDayRatioPkts` slightly ↑ on former going-out nights (home activity 00:00–01:00 counts as night, where the baseline was away) | ↑ | **no** (only 0.20 + a little of 0.35 moves) |
| C2 anhedonia | `C2_F4_MeanUpstreamRateBps` ↓ (inverted → μ ↑); `C2_F1`, `C2_F3`, `C2_F6` ≈ baseline | ↑ | **no** (only 0.25 of the weight moves) |
| C4 sleep | `C4_F8` slightly ↑ on former going-out nights | ≈ baseline | no |
| C6, C8 | — | ≈ baseline | no |
| C3, C5, C7, C9 | — | not scripted | no |
| *(diagnostic, not configured)* | `C2_F7_SocialOutgoingShareUp` ↓ while social downstream stays flat | the actual SAD signature | — |

**Episode:** no.
**Reportable:** the thesis has no way to name social anxiety. The expected result is a **partial C1/C2 elevation without any present criterion**, i.e. SAD read as weak depressed mood/anhedonia (B6). The real asymmetry is only visible in `C2_F7`.
**Original thesis config:** nothing visible at all; the `C2_F4` band (0–100 B/s) is never reached (B4).
