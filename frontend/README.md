# Results frontend

A cleaner view of the thesis app's results for the three simulated personas (Ben: insomnia,
Maria: MDD with suicidality overlay, Carl: social anxiety). For each persona it shows:

- **Expected vs. observed**: every DSM-5 criterion C1–C9 with the outcome expected in the
  profile's §9 (`profiles/tier2-clinical/*.md`), the gate state at the end of the baseline and on
  the latest clinical day, the number of days with L ≥ θ in each phase, and whether that matches.
- **Daily likelihoods**: a day × criterion grid of L<sub>k</sub> with the baseline/clinical phase,
  days ≥ θ, "present" according to the DSM gate, number of present criteria and the episode flag.
- **Metric trends**: for the selected criterion, L over time with θ, and each configured metric with
  its baseline mean ± 1 SD, the membership function's range and μ per day.
- **Day detail (traceability)**: packets per 5 minutes per device, the scripted plan blocks on a
  timeline (baseline vs. clinical-profile, sensitive, away, failed), the block table with block IDs and
  runner status (ok / exit code / late), and the breakdown L = Σ w·μ for every metric of that day.

θ, N and M can be changed in the browser; the gate is recomputed there. Weights and membership
functions come from `app_pcap_to_dsm5/app/fasl_config.json` (re-read on every request).

The Streamlit app in `app_pcap_to_dsm5/app/` is not changed and stays the reference.

## How it works

```
~/cmn-data/processed_parquet/<dataset>/*.parquet ─┐
                                                  │  python -m cmn_frontend.export
app_pcap_to_dsm5/app/metrics  (imported, unchanged)┤  one day at a time, incremental
                                                  ▼
                       ~/cmn-data/frontend_cache/<dataset>/<YYYY-MM-DD>.json
                       (all daily metrics + 5-min activity per device)
                                                  │
fasl_config.json ─────┐                           │
~/cmn-data/run/<dataset>.csv, .state.jsonl ───────┤  uvicorn cmn_frontend.api:app  (port 8600)
traffic-runner/config/devices.csv ────────────────┤  scores L_k, rolling gate, joins ground truth
                                                  ▼
                                   React UI (Vite, port 5173 in dev; or built and served by the API)
```

- **Export** (`backend/cmn_frontend/export.py`, `daily.py`): mirrors `compute_all_daily()` of the
  Early Signs page (same partition-to-day rule, hostname enrichment, background filter, base record,
  all nine criteria, previous days as history). It keeps only the resulting row per day, so memory
  stays at about one day of packets (1–3 GB, up to ~7 GB for a 9M-packet day) instead of the 24 GB
  the Streamlit app needs for its in-memory cache. A day is recomputed when its partitions change,
  when the metric code changes, or when an earlier day was recomputed (history-dependent metrics).
  The newest day is marked *incomplete* until a later day has data.
- **Scoring** (`fasl.py`): membership functions and `fasl_score` are ported from the page, which cannot
  be imported (it runs Streamlit at import). `tests/test_fasl_parity.py` extracts the original
  functions from the page source and checks that both give identical results. Two deliberate
  differences: unconfigured criteria have no likelihood (the page shows 0), and the gate is evaluated
  for **every day** over the M days up to it (the page evaluates it once, for the last M days; on the
  last day both agree).
- **API** (`api.py`): only reads the cache. It never computes metrics, so it is light and can run
  while the export is working.
- **UI** (`web/`): React + TypeScript + ECharts. The gate in `src/lib/gate.ts` and the Python gate
  share the test cases in `shared/gate_cases.json`.

Speed: the metric code calls `is_private_ip` per packet in row-wise `apply`, which dominates the run
time. The export memoizes this pure function in its own process (results identical, tested;
`CMN_NO_IP_CACHE=1` disables it). A normal day still takes 0.5–3 min, and a 9M-packet streaming day
several minutes. A first full export of three personas × ~21 days takes about an hour with `--jobs 3`;
after that, only new or changed days are computed.

## Run it (laptop only, not on the gateway)

Prerequisites: Python 3.11+, Node 20+, and the gateway data copied to `~/cmn-data`
(`processed_parquet/` and `run/`, as for the local Streamlit run).

```bash
cd frontend/backend
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
```

Compute or update the per-day cache (all datasets, three in parallel):

```bash
.venv/bin/python -m cmn_frontend.export --jobs 3
```

During the live run, keep it updating every 15 minutes:

```bash
.venv/bin/python -m cmn_frontend.export --jobs 3 --watch 900
```

Start the API:

```bash
.venv/bin/uvicorn cmn_frontend.api:app --host 127.0.0.1 --port 8600
```

Start the UI in a second terminal, then open http://127.0.0.1:5173:

```bash
cd frontend/web && npm install && npm run dev
```

For the video, build the UI once; the API then serves it at http://127.0.0.1:8600 (one process):

```bash
cd frontend/web && npm run build
```

The URL keeps the view: `#/<dataset>/<day>/<criterion>`, e.g. `#/gw_mdd_suicidality_a/2026-11-12/C2`.

### Settings (environment variables)

| Variable | Default | Meaning |
|---|---|---|
| `CMN_DATA` | `~/cmn-data` | Base folder of the copied gateway data |
| `CMN_PROCESSED` | `$CMN_DATA/processed_parquet` | Parquet partitions |
| `CMN_RUN` | `$CMN_DATA/run` | Plans (`<dataset>.csv`) and runner logs (`<dataset>.state.jsonl`) |
| `CMN_CACHE` | `$CMN_DATA/frontend_cache` | Per-day results of this frontend (separate from Streamlit's `feature_cache`) |
| `CMN_APP_DIR` | `app_pcap_to_dsm5/app` | Thesis app with `metrics/` and `fasl_config.json` |
| `CMN_FASL_CONFIG` | `$CMN_APP_DIR/fasl_config.json` | FASL weights, membership functions, θ/N/M |
| `CMN_DEVICES` | `traffic-runner/config/devices.csv` | IP → device |
| `CMN_API` | `http://127.0.0.1:8600` | API address the Vite dev server proxies to |
| `CMN_NO_IP_CACHE` | unset | `1` turns off the `is_private_ip` memoization |

## Tests

```bash
cd frontend/backend && .venv/bin/python -m pytest
```

```bash
cd frontend/web && npm test && npm run typecheck
```

Backend: FASL parity with the Streamlit page, the gate cases, ground-truth join (plan + runner state,
blocks crossing midnight, away/planned/not-run status), export on synthetic partitions with the real
metric code (cache, incremental update, cascade) and the API. Web: gate (same cases), formatting,
and the expected-vs-observed table.

## Reading the results

- Expected outcomes are those of the **calibrated gateway config** in each profile's §9. "elevated"
  means the criterion should move but stay below the gate; "borderline" and "flag" (C9, outside the
  gate) are not scored as match or miss.
- Metric days are **calendar days** of the packet timestamps (local time), as in the thesis app. A
  symptomatic night therefore shows on the day after, and a block planned for the evening of day d
  can appear on day d + 1 in the day detail.
- Membership quirk kept from the thesis code: with `mid == hi` (most bands in `fasl_config.json`),
  μ drops to 0 at x ≥ hi instead of staying at 1. Values above the band therefore count as no evidence.
- The metric values are those of the unchanged thesis code, including implausible values (e.g. 0 or
  very large values); the UI shows them as they are so they can be checked.
