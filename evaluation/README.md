# evaluation

Evaluates the live run (25.10–22.11) against the profiles: per persona, the **baseline phase** (tier-0 profile, 26.10–08.11) against the **clinical phase** (09.11–22.11), with the thesis app's own metric and scoring code.

Why not the app: its Early Signs page keeps every loaded day in Streamlit's cache (`st.cache_data`, up to 256 entries). On 13.11, with 20 days of three personas, it was killed for out-of-memory on the gateway (4.9 GB) and twice on a laptop (8 GB, then 24 GB Docker memory). Here a day is computed and released before the next one: 1.5–7 GB per persona, about 76 s per day with ~900 k rows. (Since PR #17, 17.11, the app also computes each day in its own process and no longer runs out of memory: all 61 days of the three personas in 48 min, peak 3.8 GB. The evaluation stays separate because it compares the baseline and clinical phase with the expected directions in `expectations.yaml`.)

```
evaluation/
  expectations.yaml     expected direction per metric and criterion, from the profiles' §9 and thesis-alignment §5
  evaluation/
    daily.py            daily metrics per dataset: the page's compute_all_daily, one day at a time
    scoring.py          L_k, N-of-M gate, episode: the page's functions, taken from its source with `ast`
    compare.py          baseline vs. clinical phase per metric (Cliff's d) and per criterion, report
    cli.py              python -m evaluation {daily,compare}
  tests/
```

Needs pandas, pyarrow, numpy and PyYAML (the app's metric code is imported from `app_pcap_to_dsm5/app/metrics/`, unchanged).

## Usage

The data stays outside git and outside cloud folders (it contains the visited domains): `~/cmn-data/` (copied from the gateway with `rsync`, see the README of the run setup).

```bash
cd evaluation
python3 -m pytest -q
# daily metrics, one CSV per persona (6–15 min per persona for all 29 days since PR #17; the three can run in parallel)
python3 -m evaluation daily --first 2026-10-25 --last 2026-11-22             # all three personas
python3 -m evaluation daily --dataset gw_mdd_suicidality_a --day 2026-11-12  # one day
# comparison and scoring with the original thesis config
python3 -m evaluation compare                                  # -> ~/cmn-data/eval/report.md (+ .metrics.csv)
python3 -m evaluation compare --config path/to/fasl_config_gateway.json --out ~/cmn-data/eval/report-gateway.md
python3 -m evaluation compare --all-metrics                    # also every other metric that changed
# variant: calls and games to the peer stack (10.43.0.0/24) counted as internet up/download
python3 -m evaluation daily --peer-external --first 2026-10-25 --last 2026-11-22 --out ~/cmn-data/eval-peer
python3 -m evaluation compare --eval ~/cmn-data/eval-peer --out ~/cmn-data/eval-peer/report.md
```

`daily` writes `~/cmn-data/eval/<dataset>.daily.csv`: one row per day with the page's base record, every criterion metric under its `dist_col`, and `phase`/`profile` from the scheduler plan (`~/cmn-data/run/<dataset>.csv`). A criterion that raises is skipped for that day, as on the page, but counted and printed.

## Method

- **Same numbers as the app.** `daily.py` repeats the page's `load_day_dataframe` (partitions by start day, `enrich_with_hostnames`, `drop_background`) and `compute_all_daily` (base record, then each criterion with the earlier days as history), per dataset. `scoring.py` executes the page's `mf_tri`, `mf_exp_ramp`, `mf_clip01`, `mf_value`, `fasl_score` and `gate_present` from the page source, so a change on the page is picked up automatically.
- **Per persona, per phase.** The warm-up Sunday is left out. Each phase is scored on its own days (the page scores the last M days of a selection).
- **Change of a metric:** Cliff's d = P(clinical > baseline) − P(clinical < baseline); |d| ≥ 0.33 (medium effect) counts as a change. It is rank-based, so outliers and skewed metrics (packet counts) don't dominate, and it works with 14 vs. 14 days. The run of 13.11 had only 4 clinical days and was preliminary; the final result (27.11) is below.
- **Verdict** against `expectations.yaml`: *as expected*, *opposite*, *no change*, and for metrics that should stay put *unchanged (ok)* or *changed (expected none)*.
- **Two configs** (thesis-alignment §4): the original thesis config (`fasl_config.json`) shows how the Dataset-B tuning transfers; a calibrated gateway config (tuned on the baseline days only) shows whether the logic works once calibrated. The calibration is a separate decision.
- **Peer variant** (`--peer-external`): the app counts upload/download only between a private and a public address. The runner's calls and games go to the peer stack on the gateway (10.43.0.0/24, private), so the app ignores them in every up/down metric (`up_bytes_today`, `F4_DownUpRatio`, `C6_F4`, …); with real Zoom/Discord servers they would count. The variant treats that network as public in the evaluation process only (the app is unchanged). Over the whole run (25.10–22.11) it changes the up/down metrics, not the criteria: `F4_DownUpRatio` goes from *opposite* to *no change* (MDD) and *as expected* (SAD).

## Results (live run 25.10–22.11, run of 27.11)

All 29 days recomputed per persona with the current metric code: 14 baseline days against 14 clinical days, original thesis config (`fasl_config.json`). The days up to 12.11 are identical to the run of 13.11 (85 metrics, both variants), so the speed-up of PR #17 did not change any value. Reports on the laptop: `~/cmn-data/eval/report.md`, `report-all.md` (every metric that changed), `report.metrics.csv`, and `~/cmn-data/eval-peer/report.md`.

**Criteria and episode.** With the thesis config no criterion reaches the gate (L_k ≥ θ on 6 of 14 days) for any persona, and no episode is detected. That is correct for insomnia and SAD (expected: no episode), but not for MDD (expected: borderline). C4 is over θ on more baseline than clinical days (MDD 6 vs. 2, SAD 7 vs. 3, insomnia 1 vs. 0), so the Dataset-B tuning does not transfer to the gateway data. C9 has no rule in the thesis config (`"C9": {}`), so its L is always 0, although MDD has crisis-line hits on 4 clinical days (11., 14., 18. and 22.11) and on no baseline day. For a flag (any hit) that is the expected signal; Cliff's d stays at 0.29 because 10 of the 14 days have none.

**Metrics** (medians per phase):

| Persona | As expected | Opposite | No change | Stable metrics (expected unchanged) |
|---|---|---|---|---|
| Insomnia | 2 of 5 | 0 | 3 | 6 of 6 unchanged |
| MDD | 7 of 16 (+1 without values) | 4 | 5 | – |
| SAD | 0 of 5 | 2 | 3 | 4 of 6 unchanged |

Insomnia (9to5-worker → insomnia-moderate):

| Metric | Expected | Baseline | Clinical | Cliff's d | Verdict |
|---|---|---|---|---|---|
| `F8_NightDayRatioPkts` | up | 0 | 0.0269 | 0.245 | no change |
| `C4_F1_OnsetDelayFrom2200Min` | up | 145.7 | 176.4 | 0.48 | as expected |
| `C4_F5_NocturnalMicroSessionCount0106` | up | 0 | 1.5 | 0.571 | as expected |
| `C4_F8_NightDayTrafficRatioBytes` | up | 0 | 0.0294 | 0.265 | no change |
| `C4_F4_SleepDurationZAbs30d` | up | 0.937 | 1.12 | 0.161 | no change |
| `C2_F1_UniqueSLD`, `C2_F3_ChatSessionCount`, `C2_F4_MeanUpstreamRateBps`, `C2_F6_ProductivityHits`, `C8_F2_DNSBurstRatePerHour`, `C8_F4_RepeatedQueryRatio60m` | unchanged | | | \|d\| < 0.1 | unchanged (ok) |

MDD (student → mdd-severe-suicidality):

| Metric | Expected | Baseline | Clinical | Cliff's d | Verdict |
|---|---|---|---|---|---|
| `F8_NightDayRatioPkts` | up | 0.232 | 0.898 | 0.673 | as expected |
| `F7_HourlyCV` | down | 1.57 | 1.73 | 0.235 | no change |
| `F1_DistinctSocial` | down | 161.0 | 137.5 | -0.357 | as expected |
| `F4_DownUpRatio` | up | 44.2 | 34.3 | -0.592 | opposite (peer variant: no change) |
| `C2_F1_UniqueSLD` | down | 161.5 | 140.0 | -0.332 | as expected |
| `C2_F3_ChatSessionCount` | down | 16.5 | 15.5 | -0.209 | no change |
| `C2_F4_MeanUpstreamRateBps` | down | 9,933 | 13,869 | 0.633 | opposite |
| `C2_F6_ProductivityHits` | down | 4,014 | 245.0 | -0.367 | as expected |
| `C4_F1_OnsetDelayFrom2200Min` | up | 157.9 | 181.3 | 0.786 | as expected |
| `C4_F4_SleepDurationZAbs30d` | up | 0.613 | 0.52 | -0.0714 | no change |
| `C4_F5_NocturnalMicroSessionCount0106` | up | 0 | 1 | 0.571 | as expected |
| `C4_F8_NightDayTrafficRatioBytes` | up | 0.277 | 1.02 | 0.653 | as expected |
| `C6_F8_FirstActivityMin` | up | 556.0 | 288.0 | -0.388 | opposite |
| `C6_F9_ActivationDelayVsBase28d` | up | – | – | – | no values |
| `C8_F2_DNSBurstRatePerHour` | up | 13.1 | 10.0 | -0.582 | opposite |
| `C8_F4_RepeatedQueryRatio60m` | up | 0.941 | 0.942 | 0.0816 | no change |
| `C9_F1_CrisisLineHits` | up | 0 | 0 | 0.286 | no change (hits on 4 clinical days, see above) |

SAD (student → social-anxiety-moderate):

| Metric | Expected | Baseline | Clinical | Cliff's d | Verdict |
|---|---|---|---|---|---|
| `F4_DownUpRatio` | up | 44.5 | 37.1 | -0.51 | opposite (peer variant: as expected) |
| `F8_NightDayRatioPkts` | up | 0.137 | 0.144 | -0.0204 | no change |
| `C2_F4_MeanUpstreamRateBps` | down | 9,667 | 9,425 | 0.0306 | no change |
| `C2_F7_SocialOutgoingShareUp` | down | 0.0218 | 0.0257 | 0.48 | opposite |
| `C4_F8_NightDayTrafficRatioBytes` | up | 0.178 | 0.146 | -0.0612 | no change |
| `C2_F1_UniqueSLD` | unchanged | 159.0 | 149.0 | -0.418 | changed down (expected none) |
| `C4_F1_OnsetDelayFrom2200Min` | unchanged | 157.1 | 181.0 | 0.341 | changed up (expected none) |
| `C2_F3_ChatSessionCount`, `C2_F6_ProductivityHits`, `C8_F2_DNSBurstRatePerHour`, `C8_F4_RepeatedQueryRatio60m` | unchanged | | | \|d\| ≤ 0.30 | unchanged (ok) |

**Compared with the preliminary run of 13.11** (4 clinical days), several verdicts moved: MDD `F7_HourlyCV` and `C8_F4` from *opposite* to *no change*, `C2_F3` from *as expected* to *no change*, `C6_F8` from *no change* to *opposite*; SAD `F8` and `C4_F8` from *opposite* to *no change*, `C4_F1` from *changed down* to *changed up*; insomnia `C4_F1` from *no change* to *as expected*, `C4_F4` from *as expected* to *no change*, and `C8_F2` is now unchanged as expected.
