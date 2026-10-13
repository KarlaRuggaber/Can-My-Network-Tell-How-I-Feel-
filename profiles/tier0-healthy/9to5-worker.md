# Profile: 9-to-5 worker (healthy baseline)

**Tier:** 0
**Status:** draft
**Baseline reference:** N/A (Tier 0)
**Suicidality overlay:** none

## 1. Identity
- **Occupation/schedule type:** office employee, hybrid work. Office on Tue–Thu (away from home 07:30–18:00), home office on Mon and Fri. A fixed alarm on weekdays, no alarm on weekends.
- **Schedule regularity:** fixed hours. Weekday wake and sleep times vary by only ±15–30 min, so the baseline has low day-to-day noise. This makes it the "clean" control that sleep deviations (e.g. [`tier2-clinical/insomnia-moderate.md`](../tier2-clinical/insomnia-moderate.md)) stand out against.
- **Household/device context:** lives alone. Two devices on the home network: **1 smartphone, 1 laptop** (work + private). One person per household keeps attribution simple. With per-device (MAC) splitting this is equivalent to one person.
- **Age range:** adult (roughly 28–40).

## 2. Diagnostic basis
- Reference criteria: none. Healthy control, no DSM-5/ICD-11 criteria met.
- Duration window: 14 days (same as the clinical profiles, so baseline and deviation windows can be compared one to one).
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

| Time | Home office (Mon, Fri) | Office day (Tue–Thu) | Weekend (Sat, Sun) |
|---|---|---|---|
| 00:00–06:15 | silent (sleep) | silent (sleep) | silent until ~08:30 |
| Wake / first query | 06:30 ± 15 min (phone: news, messaging, weather) | 06:30 ± 15 min | 08:30 ± 45 min |
| Morning | 08:00–12:00 laptop work (email, docs, Teams), phone short checks | 07:30 leave → **no home traffic** until ~18:00 | relaxed browsing, news, shopping |
| Midday | 12:00–13:00 lunch break, social/news on phone | away | at home: phone checks (messaging, social, shopping) |
| Afternoon | 13:00–17:30 laptop work, incl. 1–2 video calls (Teams/Zoom) | away | 14:00–18:00 away on one weekend day (friends, sport) |
| Evening | 18:00–22:30 streaming (1–2 h), social, messaging, 1 private video/voice call on ~2 evenings/week | 18:00 return, same evening pattern | streaming, longer sessions |
| Evening out | | | one evening per week, Fri or Sat 20:00–00:30 (no home traffic) |
| Last query / sleep onset | Mon night 23:00 ± 30 min; **Fri night 00:00 ± 45 min** | 23:00 ± 30 min | Sat night 00:00 ± 45 min; Sun night 23:00 ± 30 min |

- **Key properties used by the clinical profiles:**
  - **Night window is silent** from sleep onset to wake (apart from filtered background traffic, see section 7).
  - Wake time is **alarm-bound on weekdays**, so sleep problems mostly shift the *last* query, not the first.
  - Clear **weekday/weekend delta**: +2 h wake shift and one evening out per weekend.
  - Stable domain diversity: ~40–70 *actively visited* sites per day on home-office days, ~25–40 on office days (only mornings and evenings at home). The pipeline's UniqueSLD count will be several times higher, because every page load also contacts third-party domains (catalog §5, item 7).
- **Trajectory:** static (healthy, no change over the window).

## 6. Non-observable symptoms
N/A (healthy control). Note: everything this person does at the office or on mobile data (commute, lunch at work) is not on the home network. "No traffic" on office days means *away*, not *inactive*.

## 7. Confounds / ambiguity notes
Healthy behaviors this baseline must tolerate **without** triggering indicators (false-positive checks for the pipeline). They are **not part of the standard schedule** in section 9; they are candidates for later robustness variants:
- A single late night (social event, series, deadline): last query 01:00–02:00 once in the 14 days.
- One sick day: at home all day, more streaming, fewer work domains.
- Holidays/travel: whole days with no traffic (mapping file §6 "reduced session volume").
- Office days look like "low activity" in volume-based metrics. Daily metrics should be compared per day type (home office vs. office vs. weekend), otherwise office days look like withdrawal.
- **Background traffic:** phone push/keep-alive (APNs 5223, iCloud), laptop updates and NTP at night must be filtered. Otherwise the "silent night" never appears in the data (same issue the thesis hit with Dataset B, C4_F2).

## 8. Synthetic generation parameters
| Parameter | Value (distribution) |
|---|---|
| Wake / first query, weekday | N(06:30, SD 15 min) |
| Wake / first query, weekend | N(08:30, SD 45 min) |
| Last query, Sun–Thu night | N(23:00, SD 30 min) |
| Last query, Fri–Sat night | N(00:00, SD 45 min) |
| Away from home | Tue–Thu 07:30–18:00 (± 20 min); one weekend afternoon 14:00–18:00 per week; one evening per week (Fri or Sat) 20:00–00:30 |
| DNS query rate curve, 24h | 0 at night; morning peak 06:30–07:30; plateau during home-office hours; evening peak 19:00–22:00 |
| Domain category mix, home-office day | work/productivity 40%, social/messaging 20%, streaming/entertainment 15%, news 10%, search/general 10%, e-commerce 5% |
| Domain category mix, office day | social/messaging 30%, streaming/entertainment 30%, news 20%, search/general 10%, e-commerce 10% |
| Domain category mix, weekend | streaming/entertainment 30%, social/messaging 25%, e-commerce 15%, news 15%, search/general 15% |
| Domains | per category from [`activity-catalog.md`](../activity-catalog.md) §3 (`work`, `messaging`, `social_passive`, `streaming`, `news`, `search`, `shopping`); work calls on `teams.microsoft.com`/`zoom.us`, private calls on `meet.jit.si` |
| Scheduled activities per day | home office: 18–27; office day: 7–11; weekend: 12–19 (fewer *sessions* in the pipeline, because activities less than 5 min apart merge) |
| Session length | phone checks 1–5 min; laptop work blocks 60–120 min; streaming 60–150 min |
| Video/voice calls | work: 1–2 per home-office day (30–60 min); private: ~2 per week, evenings (15–45 min) |
| Day-to-day noise | low: ±15–30 min on timing, ±15% on volume |
| Weekday vs. weekend modifier | wake +2 h, last query +1 h, work domains → 0, one evening away |

## 9. Script specification
Activity IDs, `mix` categories, conventions and notation: [`activity-catalog.md`](../activity-catalog.md). Anything not scheduled = `idle_connected`.

```yaml
profile: tier0-healthy/9to5-worker
extends: null
timezone: Europe/Zurich
window_days: 14            # + 1 warm-up day, discarded
start_weekday: Mon
devices: [phone, laptop]   # both MACs -> one dataset, e.g. gw_9to5_01

day_types:
  home_office: [Mon, Fri]
  office:      [Tue, Wed, Thu]
  weekend:     [Sat, Sun]

anchors:                    # sampled once per day
  wake:                     # first scripted activity
    home_office: 'N("06:30", 15m)'
    office:      'N("06:30", 15m)'
    weekend:     'N("08:30", 45m)'
  sleep:                    # end of last scripted activity
    nights_sun_to_thu: 'N("23:00", 30m)'
    nights_fri_sat:    'N("00:00", 45m)'

away:                       # Wi-Fi off, both devices
  - {id: office_day,    day_types: [office],  from: 'N("07:30", 20m)', to: 'N("18:00", 20m)'}
  - {id: weekend_out,   day_types: [weekend], per_week: 1, from: "14:00", to: "18:00"}
  - {id: evening_out,   days: [Fri, Sat], per_week: 1, from: "20:00", to: "00:30"}   # replaces evening blocks; sleep anchor = return + 15-30m

blocks:
  # morning
  - {id: wake_check,      day_types: all,           at: wake,            device: phone,  activity: phone_check, duration: 5-15m,  mix: {news: .4, messaging: .4, search: .2}}
  # home-office work day
  - {id: work_am,         day_types: [home_office], from: "08:00", to: "12:00", device: laptop, activity: work_block}
  - {id: work_pm,         day_types: [home_office], from: "13:00", to: "17:30", device: laptop, activity: work_block}
  - {id: work_call,       day_types: [home_office], count: 1-2, within: ["09:00", "17:00"], device: laptop, activity: video_call, platform: teams, duration: 30-60m}
  - {id: day_checks,      day_types: [home_office], count: 6-10, within: ["08:00", "17:30"], device: phone, activity: phone_check, duration: 1-5m, mix: {messaging: .4, news: .3, social_passive: .3}}
  - {id: lunch_checks,    day_types: [home_office], count: 2-3, within: ["12:00", "13:00"], device: phone, activity: phone_check, mix: {social_passive: .5, news: .5}}
  # weekend daytime
  - {id: weekend_browse,  day_types: [weekend], from: wake, duration: 60-120m, device: laptop, activity: browse, mix: {news: .3, shopping: .3, social_passive: .2, search: .2}}
  - {id: weekend_checks,  day_types: [weekend], count: 4-8, within: ["10:00", "19:00"], device: phone, activity: phone_check, mix: {messaging: .4, social_passive: .4, shopping: .2}}
  # evening (all days, unless away)
  - {id: evening_stream,  day_types: [home_office, office], within: ["19:00", "22:30"], device: laptop, activity: video_stream, duration: 60-120m, mix: {streaming: 1}}
  - {id: evening_checks,  day_types: all, count: 3-5, within: ["18:00", sleep], device: phone, activity: phone_check, mix: {social_passive: .5, messaging: .5}}
  - {id: evening_msg,     day_types: all, count: 1-2, within: ["18:00", "22:00"], device: phone, activity: messaging}
  - {id: private_call,    day_types: [home_office, office], per_week: 2, within: ["19:00", "21:30"], device: phone, activity: video_call, platform: jitsi, duration: 15-45m}
  - {id: weekend_stream,  day_types: [weekend], within: ["20:00", sleep], device: laptop, activity: video_stream, duration: 90-150m, mix: {streaming: 1}}
  # bedtime
  - {id: bedtime_check,   day_types: all, at: sleep - 15m, device: phone, activity: phone_check, duration: 5-15m, mix: {social_passive: .6, messaging: .4}}

noise:
  timing: "±15–30 min (already in the anchor SDs)"
  volume: "count ranges above; ±15% on durations"
```

**Expected thesis output** (scoring rules and issues B1–B9: [`thesis-alignment.md`](../thesis-alignment.md)).

This run is also a **calibration source**: the distribution of every active metric over these 14 days defines its green band in `fasl_config_gateway.json` (thesis-alignment §4). Compare per day type (home office / office / weekend), because office days are "away" for most of the day.

| Criterion | Thesis metrics | Expected | Present? |
|---|---|---|---|
| C1 depressed mood | `F8_NightDayRatioPkts`, `F4_DownUpRatio`, `F7_HourlyCV`, `F1_DistinctSocial` | `F8` ≈ 0 after weeknights, small after Fri/Sat nights | no |
| C2 anhedonia | `C2_F1`, `C2_F6`, `C2_F3`, `C2_F4` | stable per day type; productivity high on home-office days, low on office days and weekends | no |
| C4 sleep | `C4_F4`, `C4_F8` (+ `C4_F1`, `C4_F5` if added) | onset ≈ 23:00, silent nights. `C4_F7` μ = 0 (idle share far above the band end of 0.16 on office days) | no |
| C6 fatigue | `C6_F8_FirstActivityMin` | ≈ 06:30 on weekdays, ≈ 08:30 on weekends | no |
| C8 concentration | `C8_F2`, `C8_F4`, `C8_F8` | baseline values; `C8_F4` is probably already > 0.8 (polling), which the re-tuned band must account for | no |
| C3, C5, C7, C9 | — | not scripted | no (no C9 flag) |

**Episode:** no.
**Original thesis config:** an episode is impossible anyway (B1). C4 may show as "present" through the `C4_F2` artifact (B3). That would be a false positive caused by the code, not by the profile.
