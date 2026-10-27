# Thesis Alignment (CareNet scoring)

After the scripted traffic is captured, the master thesis pipeline (`app_pcap_to_dsm5`, Nef 2025) maps the router metadata to DSM-5 criteria. This file states **how the thesis does that**, which parts are active, and what must be true for the profiles' expected results to hold. Every profile's section 9 "Expected thesis output" builds on this file. Symptom-level mapping: [symptom-network-mapping.md](symptom-network-mapping.md) §8. Scripting pitfalls: [activity-catalog.md](activity-catalog.md) §4–5.

Source: code reading of `app/pages/01_Early_Signs_Overview.py`, `app/metrics/*.py` and `app/fasl_config.json`, plus thesis §5.6 and §6.2.

## 1. How the thesis maps metadata to criteria

1. **Metrics per day and dataset** (`metrics/criterion1.py` … `criterion9.py`). One dataset = one person (both profile devices map to one dataset, catalog §1). Days are calendar days.
2. **Membership** μ ∈ [0, 1] per metric: a triangle with `lo`/`mid`/`hi`, optionally inverted. All active metrics except C4_F7 use `mid = hi`: μ rises linearly from `lo` to `hi` (inverted: falls). **Values outside [lo, hi] get μ = 0.** The thesis does this on purpose to ignore outliers (§6.2.1), but it also means a value far beyond `hi` counts as *healthy*.
3. **Daily criterion likelihood** L_k = Σ (w · μ) over the criterion's metrics (weights per criterion sum to 1, cap τ = 1).
4. **Criterion present** if L_k ≥ θ = 0.6 on at least N = 6 of the last M = 14 days.
5. **Episode likely** if ≥ 5 criteria are present **and** at least one core criterion is present (config: core = C2 only).

Criteria = DSM-5 MDD criteria A1–A9: **C1** depressed mood, **C2** anhedonia, **C3** appetite/weight, **C4** sleep, **C5** psychomotor, **C6** fatigue, **C7** worthlessness/guilt, **C8** concentration, **C9** suicidality.

## 2. Active configuration (`fasl_config.json`)

Only **C1, C2, C4 and C8** are configured. All other criteria have L_k = 0 and can never be present. The other criteria's metrics are computed, though, and show up in the app.

| Criterion | Metric key | w | lo / mid / hi (inv.) | μ > 0 when | Likely on real scripted traffic |
|---|---|---|---|---|---|
| C1 | `F1_DistinctSocial` | .25 | 20 / 80 / 80 | 20 < x < 80, **rises with x** | "Social" uses `chat_mask`, which includes all port-443 traffic, so x ≈ distinct HTTPS domains → likely > 80 → μ = 0. **Direction is reversed:** the thesis defines *fewer* social domains as worse (`higher_is_worse=False`), the config rewards more. |
| C1 | `F4_DownUpRatio` | .20 | 3 / 12 / 12 | 3 < x < 12 | Streaming-heavy days can exceed 12 → μ = 0 (a strong passive shift drops *out* of the band). |
| C1 | `F6_Fano` | .10 | 100 / 1000 / 1000 | 100 < x < 1000 | unknown, calibrate |
| C1 | `F7_HourlyCV` | .10 | 0.6 / 3 / 3 | rises with CV | **Direction is reversed:** thesis says a *lower* CV (flatter day) is worse, the config rewards a higher CV. |
| C1 | `F8_NightDayRatioPkts` | .35 | 0.2 / 1 / 1 | night (00–05 h) packets are 20–100 % of day packets | Short night bursts add only a few % → often below `lo`. |
| C2 | `C2_F1_UniqueSLD` | .40 | 0 / 40 / 40 inv. | x < 40, more μ the fewer | Real days ≫ 40 (third-party domains) → μ = 0. |
| C2 | `C2_F3_ChatSessionCount` | .05 | 1 / 3 / 3 inv. | x < 3 | many sessions per day → μ = 0 |
| C2 | `C2_F4_MeanUpstreamRateBps` | .25 | 0 / 100 / 100 inv. | x < 100 B/s | far above → μ = 0 |
| C2 | `C2_F6_ProductivityHits` | .30 | 3 500 / 15 000 / 15 000 inv. | 3 500 ≤ x < 15 000, more μ the fewer | **Below 3 500 → μ = 0.** A day with almost no study/work traffic scores 0, not 1. |
| C4 | `C4_F2_WakeAfter0400Min` | .65 | 120 / 1085 / 1085 | — | **Artifact:** wake detection only looks at hours 22–04 *of the same calendar day*. On a day with activity after midnight and again from 22:00, the "wake" is the first packet after 22:00 (≈ 1 080 min → μ ≈ 1). The value depends on whether evening activity starts before 22:05, not on sleep. It dominates C4 (w = .65). |
| C4 | `C4_F4_SleepDurationZAbs30d` | .20 | 0.25 / 0.8 / 0.8 | — | z-score vs. the dataset's own earlier days (needs ≥ 7) |
| C4 | `C4_F7_DaytimeIdleRatio0818` | .05 | 0 / 0.08 / 0.16 | idle share of 08–18 h is 0–16 % (peak at 8 %) | Away days (≈ 1) and normal home days (> 16 %) → μ = 0. Practically always 0. |
| C4 | `C4_F8_NightDayTrafficRatioBytes` | .15 | 0.2 / 1 / 1 | night bytes are 20–100 % of day (06–22 h) bytes | low-volume night use → often below `lo` |
| C8 | `C8_F2_DNSBurstRatePerHour` | .40 | 25 / 61 / 61 | ≥ 25 minutes per hour with ≥ 3 distinct domains | normal days far lower → μ = 0 |
| C8 | `C8_F4_RepeatedQueryRatio60m` | .40 | 0.8 / 1 / 1 | (queries − unique) / queries ≥ 0.8 | probably already in band on healthy days (polling, re-resolution) → baseline > 0 |
| C8 | `C8_F8_MedianIKSsec` | .20 | 0.12 / 0.22 / 0.22 | median gap (≤ 3 s) between outbound "chat" packets | packet timing, not real keystrokes; calibrate |

## 3. What this means for the profiles

| # | Issue | Consequence |
|---|---|---|
| B1 | Only 4 criteria configured | **"Episode likely" is impossible** (needs ≥ 5). This holds for every profile, including severe MDD. |
| B2 | Core = C2 only, and C2 tops out around L ≈ 0.3 on real traffic | The core symptom can't be present. DSM-5 allows depressed mood **or** anhedonia as core, so the core should be C1 + C2. |
| B3 | C4_F2 artifact (w = .65) | C4 can be "present" for healthy baselines and absent for insomnia, for reasons unrelated to sleep. |
| B4 | Bands tuned by hand on Dataset B, which isn't a real person (thesis §6.2, §7.2.2) | Most real values fall outside [lo, hi] → μ = 0, so everything looks "healthy" for the wrong reason. |
| B5 | Early waking isn't a thesis indicator | C4_F2 and C6_F8 treat *later* waking/first activity as worse. A 04:30 wake *lowers* both. Only the night/day ratios (C1_F8, C4_F8) pick it up. |
| B6 | The thesis is MDD-only | Insomnia disorder and social anxiety have no criterion of their own. They can only appear as MDD criteria (insomnia → C4 and C1, because the night/day ratio sits in C1; social anxiety → C1_F4, C2_F4). This misattribution is an expected, reportable result. |
| B7 | History metrics (C4_F3, C4_F4, C6_F9) | Need earlier days of the same dataset → baseline period before each clinical profile (catalog §6). |
| B8 | C9 under the gate rule | Suicidality is episodic (2–4 nights per 14 days). With N = 6 of 14, **C9 can never be present**, even if configured. Only domain hits (`143.ch`, `147.ch`) are visible; method/forum metrics need URLs or search terms (invisible under HTTPS). |
| B9 | Reversed directions | C1_F1 (DistinctSocial) and C1_F7 (HourlyCV) are scored opposite to the thesis's own definition. |
| B10 | C2_F6 counted background traffic (fixed in the app 26.10, `284ff87`) | With `google.com`/`microsoft.com`/`live.com` in the list, Safe Browsing, Chrome/Windows updates, telemetry, logins, ads and STUN counted as productivity: 11 932 hits on a scripted day without any work, and in the thesis ONU datasets not a single real productivity visit. The app now counts only tool hosts there (Deployment.md §7.10). **Consequence for the bands:** a day without work now has ~0 hits, and below 3 500 the current band gives μ = 0, so C2_F6 contributes nothing for exactly the days it should flag (before the fix, background gave e.g. 11 932 → μ ≈ 0.27). Recalibrate C2_F6 on the baseline days (§4), e.g. with `lo` near 0. |
| B11 | Machine background counted as user activity (fixed in the app 26.10, `e3fd6dd`) | The thesis counts every packet, so OS/browser background (updates, telemetry, Safe Browsing, OCSP, push) makes a sleeping device look awake in the sleep and timing features. The app now drops these hosts before all features (Deployment.md §7.11). In the thesis datasets no sleep/timing value changes (5-minute captures), but `C2_F1_UniqueSLD` drops by 1–5 in 32 of 64 datasets. The runner containers now send such background too, so the filter is tested by the simulated data. |
| B12 | First DNS answer per IP for the whole day (fixed in the app 27.10, `4cc8e49`) | Shared CDN/Google IPs serve many names, so later packets kept a day-time name (background counted as `google.com` or a TikTok host). The app now uses the latest answer the client received before the packet (Deployment.md §7.12). In the thesis datasets this changes 0.21 % of hostnames and `F1_DistinctSocial` in 16 of 64 datasets; no other feature. |

## 4. Proposal: evaluate the thesis logic with a calibrated config

The thesis logic (metrics, membership, L_k, gate) stays unchanged. That logic is what we evaluate. We change only the configuration, plus one bug fix, and document both.

1. **New config file `fasl_config_gateway.json`** next to the original (the original is never overwritten):
   - **Re-tune `lo`/`mid`/`hi`** of every active metric on the **Tier 0 runs only**, using the thesis's own procedure (§6.2): distribution view → green band = baseline range → `lo` at the edge of the baseline band, `hi` where the indicator region ends. Never tune on the clinical runs, otherwise the evaluation is circular.
   - **Open the outer end of each band.** With the thesis shape (`mid = hi`), values beyond `hi` score μ = 0, so the strongest deviations would look healthy (e.g. an MDD day with almost no productivity traffic). Calibrate one-sided instead, using the code's own handling of open bounds in `mf_tri`:
     - *higher is worse:* `lo` = upper edge of the baseline band, `mid` = clear-indicator value, `hi` = a very large number (e.g. `1e9`) → μ rises from `lo` to `mid` and stays ≈ 1 beyond.
     - *lower is worse:* `lo` = a very large negative number (e.g. `-1e9`), `mid` = clear-indicator value, `hi` = lower edge of the baseline band, `invert: false` → μ = 1 below `mid`, falling to 0 at the baseline edge.
     - Use large finite numbers rather than `Infinity`, unless the pilot shows the app's config loader accepts `Infinity`.
   - **Fix directions** of C1_F1 and C1_F7 (B9); the one-sided rule above already gives them the correct "lower is worse" shape.
   - **Add C6** (`C6_F8_FirstActivityMin`, `C6_F9_ActivationDelayVsBase28d`). These are already in the thesis's `DEFAULT_CFG`, but its band for `C6_F8` (0 / 45 / 90) doesn't fit the metric, which is minutes since midnight (≈ 400–600 on normal days), so re-tune it like the others. Add **C9** (`C9_F1_CrisisLineHits`) only as a separate **flag** (any hit is shown), outside the N-of-M gate (B8), which matches the "suicidality is an overlay" decision in [ProfileStructure.md](ProfileStructure.md) §3.
   - **Core symptoms = [C1, C2]** (DSM-5, B2).
   - Optional: add the **SAD asymmetry metric** `C2_F7_SocialOutgoingShareUp` (computed, not configured) as a diagnostic view.
2. **C4_F2:** either fix the night window so it crosses midnight (22:00 of day d−1 to 12:00 of day d), or set its weight to 0 and re-weight C4 with metrics that already exist (`C4_F1` onset, `C4_F5` micro-sessions, `C4_F4`, `C4_F8`). This changes thesis code, so decide with the supervisor.
3. **Report every result twice:** original thesis config vs. gateway config. The original shows how Dataset-B tuning transfers to real traffic (expected: almost nothing fires). The gateway config shows whether the logic works once calibrated.

## 5. Expected thesis output per profile (gateway config)

Present = L_k ≥ 0.6 on ≥ 6 of 14 days. Details and reasoning are in each profile's section 9.

| Profile | C1 | C2 | C3 | C4 | C5 | C6 | C7 | C8 | C9 flag | Episode |
|---|---|---|---|---|---|---|---|---|---|---|
| [9to5-worker](tier0-healthy/9to5-worker.md) | – | – | – | – | – | – | – | – | – | no |
| [student](tier0-healthy/student.md) | – | – | – | – | – | – | – | – | – | no |
| [insomnia-moderate](tier2-clinical/insomnia-moderate.md) | ↑ (not present) | – | – | **present** | – | – | – | – | – | no |
| [social-anxiety-moderate](tier2-clinical/social-anxiety-moderate.md) | ↑ (not present) | ↑ (not present) | – | – | – | – | – | – | – | no |
| [mdd-severe-suicidality](tier2-clinical/mdd-severe-suicidality.md) | **present** | **present** | – | **present** | – | borderline | – | **present** | **yes** | **borderline** (4 sure + C6) |

With the **original** thesis config, every row's episode is "no" (B1). The C4 column can't be interpreted because of B3.

**Finding worth reporting:** even a 9-of-9 severe MDD profile reaches only 4–5 present criteria through network data. C3, C5 and C7 aren't observable, C9 is episodic, and C6 is weakened by early waking (B5). So the ≥ 5 rule is barely reachable from the router alone.
