# evaluation

Evaluates the live run (25.10–22.11) against the profiles: per persona, the **baseline phase** (tier-0 profile, 26.10–08.11) against the **clinical phase** (09.11–22.11), with the thesis app's own metric and scoring code.

Why not the app: its Early Signs page keeps every loaded day in Streamlit's cache (`st.cache_data`, up to 256 entries). On 13.11, with 20 days of three personas, it was killed for out-of-memory on the gateway (4.9 GB) and twice on a laptop (8 GB, then 24 GB Docker memory). Here a day is computed and released before the next one: 1.5–7 GB per persona, about 76 s per day with ~900 k rows.

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
# daily metrics, one CSV per persona (~25 min for 20 days; the three can run in parallel)
python3 -m evaluation daily --first 2026-10-25 --last 2026-11-22             # all three personas
python3 -m evaluation daily --dataset gw_mdd_suicidality_a --day 2026-11-12  # one day
# comparison and scoring with the original thesis config
python3 -m evaluation compare                                  # -> ~/cmn-data/eval/report.md (+ .metrics.csv)
python3 -m evaluation compare --config path/to/fasl_config_gateway.json --out ~/cmn-data/eval/report-gateway.md
python3 -m evaluation compare --all-metrics                    # also every other metric that changed
```

`daily` writes `~/cmn-data/eval/<dataset>.daily.csv`: one row per day with the page's base record, every criterion metric under its `dist_col`, and `phase`/`profile` from the scheduler plan (`~/cmn-data/run/<dataset>.csv`). A criterion that raises is skipped for that day, as on the page, but counted and printed.

## Method

- **Same numbers as the app.** `daily.py` repeats the page's `load_day_dataframe` (partitions by start day, `enrich_with_hostnames`, `drop_background`) and `compute_all_daily` (base record, then each criterion with the earlier days as history), per dataset. `scoring.py` executes the page's `mf_tri`, `mf_exp_ramp`, `mf_clip01`, `mf_value`, `fasl_score` and `gate_present` from the page source, so a change on the page is picked up automatically.
- **Per persona, per phase.** The warm-up Sunday is left out. Each phase is scored on its own days (the page scores the last M days of a selection).
- **Change of a metric:** Cliff's d = P(clinical > baseline) − P(clinical < baseline); |d| ≥ 0.33 (medium effect) counts as a change. It is rank-based, so outliers and skewed metrics (packet counts) don't dominate, and it works with 14 vs. 14 days. With fewer clinical days (before 22.11) the result is preliminary.
- **Verdict** against `expectations.yaml`: *as expected*, *opposite*, *no change*, and for metrics that should stay put *unchanged (ok)* or *changed (expected none)*.
- **Two configs** (thesis-alignment §4): the original thesis config (`fasl_config.json`) shows how the Dataset-B tuning transfers; a calibrated gateway config (tuned on the baseline days only) shows whether the logic works once calibrated. The calibration is a separate decision.
