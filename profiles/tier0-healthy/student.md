# Profile: Student (healthy baseline)

**Tier:** 0
**Status:** draft
**Baseline reference:** N/A (Tier 0)
**Suicidality overlay:** none

## 1. Identity
- **Occupation/schedule type:** bachelor student. Lectures on campus Mon–Thu in varying time blocks (some days from 08:15, some only in the afternoon), self-study at home on Fri. No fixed alarm. Wake time follows the first lecture of the day.
- **Schedule regularity:** variable but healthy. Timing varies ±45–60 min from day to day, more than the [`9to5-worker`](9to5-worker.md), but nights stay consolidated (no wake-ups) and the weekly rhythm repeats. Clinical profiles built on this baseline must therefore show deviations *larger* than this natural noise.
- **Household/device context:** lives in a shared flat with two flatmates. Profile devices: **1 smartphone, 1 laptop**. The flatmates' devices are on the same network and are separated out by MAC (per-device split). This baseline also tests whether that attribution works.
- **Age range:** young adult (roughly 19–25).

## 2. Diagnostic basis
- Reference criteria: none. Healthy control, no DSM-5/ICD-11 criteria met.
- Duration window: 14 days (same as the clinical profiles).
- Overall severity: N/A.

## 3. Symptom set
All symptoms absent. Healthy control.
| Symptom | Present? | Severity (mild/mod/severe) | Notes |
|---|---|---|---|
| Depressed mood | no | | |
| Anhedonia (loss of interest/pleasure) | no | | |
| Weight/appetite change | no | | |
| Sleep disturbance (general) | no | | |
| Early morning waking (4-5am) | no | | |
| Psychomotor agitation/retardation | no | | |
| Fatigue / loss of energy | no | | |
| Feelings of worthlessness/guilt | no | | |
| Concentration difficulty | no | | |
| Suicidal ideation | no | | |
| Hopelessness | no | | |
| Social withdrawal | no | | |
| Rumination | no | | |
| Anxiety — generalized (GAD) | no | | |
| Anxiety — social | no | | |

## 4. Behavioral & network translation
None. No symptoms present. This profile defines the reference values that Tier 1–4 profiles deviate from.

## 5. Baseline deviation spec
For Tier 0 this section defines the baseline itself (there is no deviation).
- **Personal baseline (typical week):**

| Time | Lecture day (Mon–Thu) | Self-study day (Fri) | Weekend (Sat, Sun) |
|---|---|---|---|
| Night | silent from sleep onset to wake | silent | silent |
| Wake / first query | 07:30 (early lecture) to 09:30 (late lecture), ± 30 min; phone: messaging, Instagram, weather | 09:00 ± 45 min | 10:00 ± 60 min |
| Morning / midday | 2–5 h on campus → **no home traffic** in that block (block position varies by day) | laptop study 10:00–12:30: university LMS, docs, library/search, music streaming in the background | slow start: social, YouTube, messaging |
| Afternoon | back home: study 1–3 h (LMS, docs), 1 group-project video call on ~2–3 days/week (Zoom, 30–60 min) | study 13:30–16:30, then free time | 2–4 h away on one day (sport, friends) |
| Evening | 18:00–00:00: gaming 1–2 h with voice chat (Discord) on ~3 evenings/week, streaming, a lot of social media and messaging, posting stories | gaming/streaming, or out | streaming, gaming, one family video call per week (Sunday, ~30 min) |
| Going out | 1–2 evenings per week, Thu–Sat 20:00–01:00 → **no home traffic** | | |
| Last query / sleep onset | 00:30 ± 45 min | Fri night 01:30 ± 30 min (if at home) | Sat night 01:30 ± 30 min; Sun night 00:30 ± 45 min. After going out: return + 15–30 min |

- **Key properties used by the clinical profiles:**
  - **Hobby category = gaming** (with voice chat), plus streaming. This is the category that "anhedonia" drops in [`tier2-clinical/mdd-severe-suicidality.md`](../tier2-clinical/mdd-severe-suicidality.md).
  - **High, active social use:** heavy messaging, regular posting/uploads (high upstream share on social domains), many synchronous calls (group projects, Discord, family). This is the asymmetry that [`tier2-clinical/social-anxiety-moderate.md`](../tier2-clinical/social-anxiety-moderate.md) reduces.
  - **Going out 1–2 evenings/week** (Thu–Sat), the "away" evenings that the social anxiety profile replaces with home traffic.
  - **Nights are late but consolidated:** activity after 02:00 is rare (about once per 14 days, on a Fri/Sat night). No nocturnal bursts, no 04:00–05:30 activity.
  - **High domain diversity:** ~60–100 *actively visited* sites per day at home. The pipeline's UniqueSLD count will be several times higher because of third-party domains (catalog §5, item 7).
- **Trajectory:** static (healthy, no change over the window).

## 6. Non-observable symptoms
N/A (healthy control). Note: time on campus, on mobile data or at friends' places is not on the home network. "No traffic" in those blocks means *away*, not *inactive*.

## 7. Confounds / ambiguity notes
Healthy behaviors this baseline must tolerate **without** triggering indicators (false-positive checks for the pipeline). They are **not part of the standard schedule** in section 9; they are candidates for later robustness variants:
- **Exam period:** fewer outings, more study domains, later nights for 1–2 weeks. Healthy, but looks like reduced social activity plus a sleep shift.
- **Semester break:** lecture structure disappears, wake times drift later. Healthy, but looks like irregular routine.
- A single gaming night until 03:00, or a party weekend.
- Wake time naturally varies with the lecture timetable. Day-to-day variance is high *by design* and must not be read as routine instability.
- **Flatmates' devices** on the same network must not be counted as this person (per-MAC split). Without the split, a flatmate's late-night traffic looks like a sleep problem.
- **Background traffic:** phone push/keep-alive (APNs 5223, iCloud), game launcher and OS updates at night must be filtered. Otherwise the "silent night" never appears in the data (thesis Dataset B, C4_F2).

## 8. Synthetic generation parameters
| Parameter | Value (distribution) |
|---|---|
| Wake / first query, lecture day | depends on first lecture: N(07:30, SD 30 min) for an 08:15 lecture, N(09:30, SD 30 min) otherwise; ~50% of lecture days early |
| Wake / first query, Fri | N(09:00, SD 45 min) |
| Wake / first query, weekend | N(10:00, SD 60 min) |
| Last query, Sun–Thu night | N(00:30, SD 45 min) |
| Last query, Fri–Sat night | N(01:30, SD 30 min) |
| Away from home | Mon–Thu: one campus block of 2–5 h, start between 08:00 and 14:00; 1–2 going-out evenings per week, Thu–Sat 20:00–01:00; one weekend afternoon of 2–4 h per week |
| DNS query rate curve, 24h | 0 at night; lower, later morning start; gap during the campus block; afternoon study plateau; **main peak 20:00–00:00** |
| Domain category mix, lecture day | social/messaging 30%, streaming/entertainment 25% (incl. gaming), study/productivity 20%, search/general 10%, news 5%, e-commerce 5%, other 5% |
| Domain category mix, self-study day | study/productivity 35%, social/messaging 25%, streaming/entertainment 20%, search/general 15%, other 5% |
| Domain category mix, weekend | streaming/entertainment 35% (incl. gaming), social/messaging 35%, e-commerce 10%, search/general 10%, news 5%, other 5% |
| Domains | per category from [`activity-catalog.md`](../activity-catalog.md) §3 (`study`, `messaging`, `social_passive`, `social_post`, `gaming`, `streaming`, `news`, `search`, `shopping`); group-project calls on `zoom.us`, private calls on `meet.jit.si`, gaming voice on `discord.com` |
| Scheduled activities per day | ≈ 22–38 when at home all day (many short phone checks, 1–2 study blocks, evening streaming/gaming); fewer on campus and going-out days. Fewer *sessions* in the pipeline, because activities less than 5 min apart merge |
| Session length | phone checks 1–5 min; study blocks 45–120 min; gaming 60–120 min; streaming 30–90 min |
| Video/voice calls | group project 2–3 per week (30–60 min); Discord voice during gaming ~3 evenings/week; family video call 1 per week (Sunday) |
| Social upstream share | high: posting stories/photos most days (uploads on social domains) |
| Day-to-day noise | moderate: ±45–60 min on timing, ±25% on volume |
| Weekday vs. weekend modifier | wake +1.5 to +2 h, last query +1 h, study domains → ~0, going out on 1–2 evenings |

## 9. Script specification
Activity IDs, `mix` categories, conventions and notation: [`activity-catalog.md`](../activity-catalog.md). Anything not scheduled = `idle_connected`.

```yaml
profile: tier0-healthy/student
extends: null
timezone: Europe/Zurich
window_days: 14            # + 1 warm-up day, discarded
start_weekday: Mon
devices: [phone, laptop]   # both MACs -> one dataset, e.g. gw_student_01
                           # flatmates' devices on the same network are NOT part of the dataset (per-MAC split test)

day_types:
  lecture:    [Mon, Tue, Wed, Thu]
  self_study: [Fri]
  weekend:    [Sat, Sun]

timetable:                  # fixed per instance (sampled once with the seed), repeats in week 2
  lecture:
    early_lecture_share: 0.5          # 2 of 4 lecture days start 08:15
    campus_block: {start: 'U("08:00", "14:00")', length: 'U(2h, 5h)'}   # early days: start 08:00

anchors:
  wake:
    lecture_early: 'N("07:30", 30m)'
    lecture_late:  'N("09:30", 30m)'
    self_study:    'N("09:00", 45m)'
    weekend:       'N("10:00", 60m)'
  sleep:
    nights_sun_to_thu: 'N("00:30", 45m)'
    nights_fri_sat:    'N("01:30", 30m)'

away:                       # Wi-Fi off, both devices
  - {id: campus,       day_types: [lecture], from: timetable.campus_block.start, length: timetable.campus_block.length}
  - {id: weekend_out,  day_types: [weekend], per_week: 1, from: "14:00", length: 2h-4h}
  - {id: going_out,    days: [Thu, Fri, Sat], per_week: 1-2, from: 'N("20:00", 30m)', to: 'N("01:00", 45m)'}   # replaces evening blocks; sleep anchor = return + 15-30m

blocks:
  # morning
  - {id: wake_check,     day_types: all, at: wake, device: phone, activity: phone_check, duration: 5-15m, mix: {messaging: .4, social_passive: .4, news: .2}}
  # study
  - {id: study_home,     day_types: [lecture], when: "after campus", duration: 1h-3h, device: laptop, activity: study_block, with: music_background}
  - {id: study_am,       day_types: [self_study], from: "10:00", to: "12:30", device: laptop, activity: study_block, with: music_background}
  - {id: study_pm,       day_types: [self_study], from: "13:30", to: "16:30", device: laptop, activity: study_block}
  - {id: group_call,     day_types: [lecture, self_study], per_week: 2-3, within: ["13:00", "18:00"], device: laptop, activity: video_call, platform: zoom, duration: 30-60m}
  # phone checks while at home
  - {id: day_checks,     day_types: all, count: 10-18, within: [wake, "20:00"], device: phone, activity: phone_check, duration: 1-5m, mix: {messaging: .35, social_passive: .45, news: .1, search: .1}}
  - {id: messaging_day,  day_types: all, count: 3-6, within: [wake, sleep], device: phone, activity: messaging}
  - {id: social_post,    day_types: all, per_week: 5-7, within: ["12:00", "23:00"], device: phone, activity: social_post}
  # evening (unless going out)
  - {id: gaming,         day_types: all, per_week: 3, within: ["20:00", "23:30"], device: laptop, activity: gaming_session, duration: 60-120m, voice: true}
  - {id: evening_stream, day_types: all, within: ["19:00", sleep], device: laptop, activity: video_stream, duration: 30-90m, mix: {streaming: 1}}
  - {id: evening_social, day_types: all, count: 4-8, within: ["18:00", sleep], device: phone, activity: social_passive, duration: 5-20m}
  - {id: family_call,    days: [Sun], within: ["17:00", "20:00"], device: phone, activity: video_call, platform: jitsi, duration: 25-35m}
  # weekend daytime
  - {id: weekend_slow,   day_types: [weekend], from: wake, duration: 60-120m, device: phone, activity: social_passive}
  - {id: weekend_shop,   day_types: [weekend], count: 0-1, within: ["11:00", "18:00"], device: laptop, activity: browse, duration: 15-40m, mix: {shopping: .7, search: .3}}
  # bedtime
  - {id: bedtime_check,  day_types: all, at: sleep - 20m, device: phone, activity: social_passive, duration: 10-20m}

noise:
  timing: "±45–60 min (in the anchor SDs); timetable fixed per instance"
  volume: "count ranges above; ±25% on durations"
```

**Expected thesis output** (scoring rules and issues B1–B9: [`thesis-alignment.md`](../thesis-alignment.md)).

Like the 9-to-5 baseline, this run is a **calibration source** for `fasl_config_gateway.json` (thesis-alignment §4). Compare per day type (lecture / self-study / weekend).

| Criterion | Thesis metrics | Expected | Present? |
|---|---|---|---|
| C1 depressed mood | `F8_NightDayRatioPkts`, `F4_DownUpRatio`, `F7_HourlyCV`, `F1_DistinctSocial` | `F8` small but non-zero (sleep onset ≈ 00:30, so 00:00–00:45 counts as night), higher than the 9-to-5. Most likely false positive: days after going-out nights (return ~01:00) and Fri/Sat nights. `F4` moderate (calls, uploads and gaming keep upstream high), the reference for the SAD profile. | no |
| C2 anhedonia | `C2_F1`, `C2_F6`, `C2_F3`, `C2_F4` | UniqueSLD highest of all profiles; productivity moderate on study days (only the `office.com`/`google.com` part of studying counts), low on weekends; upstream high on call/gaming days | no |
| C4 sleep | `C4_F4`, `C4_F8` (+ `C4_F1`, `C4_F5` if added) | consolidated nights, `C4_F5` ≈ 0 (occasionally 1 after a Fri/Sat night); `C4_F7` μ = 0 on campus days (idle share above 0.16) | no |
| C6 fatigue | `C6_F8_FirstActivityMin` | 07:30–10:00, varies with the timetable | no |
| C8 concentration | `C8_F2`, `C8_F4`, `C8_F8` | baseline values | no |
| C3, C5, C7, C9 | — | not scripted | no (no C9 flag) |

**Episode:** no.
**Original thesis config:** an episode is impossible anyway (B1); possible C4 false positive through `C4_F2` (B3).
**Attribution check:** if a flatmate's device leaks into this dataset, the C1/C4 night metrics rise. That's a test of the per-MAC split, not a symptom.
