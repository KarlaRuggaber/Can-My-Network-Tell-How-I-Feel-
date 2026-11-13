# Results portal

A results portal for router-level network metrics → DSM-5 criterion likelihoods, per person. It does
not depend on where the traffic comes from: a **source** is any folder of Parquet captures in
`processed_parquet/` — a scripted gateway run (Ben: insomnia, Maria: MDD with suicidality overlay,
Carl: social anxiety) or live home traffic.

**Logins and roles** (as the Streamlit app, a login comes first; the portal looks the same for all):

- *Single-profile user* (the person themself): sees only their own profile, no settings.
- *Multi-profile user* (clinician, parent): chooses between their profiles, can adjust the gate,
  and under **People and devices** adds people, picks their traffic source, assigns which devices
  (local IP addresses seen in that source) belong to whom, and sets the baseline period.

**Person profiles**: a name, a source, and either all devices of the source or a device set. With a
device set, the metrics are computed on that person's traffic only (several people behind one
router stay apart). Scripted sources bring their plan (baseline and clinical phase, ground truth,
§9 expectations); live sources use the profile's baseline period (default: the first 14 days with
data), and every later day is "recent". The three scripted personas are created as profiles on the
first start, with all devices of their source, so their numbers stay those of the evaluation.

For each profile the portal shows:

- **Baseline vs. clinical (or recent) period**: every scored DSM-5 criterion with, for scripted
  personas, the outcome expected in the profile's §9 (`profiles/tier2-clinical/*.md`) and two gate results side by side, each computed
  on that phase's own days only: "Baseline (26.10–08.11)" and "Clinical (09.11–22.11)", with the days
  with L ≥ θ (n of the days counted) and present/absent, plus the episode per phase. The warm-up day
  and the day still being ingested are not counted. While the clinical phase has fewer than M days
  the result is marked *preliminary*. This is the same rule as the evaluation
  (`evaluation/compare.py` `score_phases()`), and the numbers match it.
- **Daily likelihoods**: a day × criterion grid of L<sub>k</sub> with the baseline/clinical phase,
  days ≥ θ, "present" according to the DSM gate, number of present criteria and the episode flag.
- **Metric trends**: for the selected criterion, L over time with θ, and each configured metric with
  its baseline mean ± 1 SD, the membership function's range and μ per day.
- **Day detail (traceability)**: packets per 5 minutes per device; for scripted sources the plan blocks on a
  timeline (baseline vs. clinical-profile, sensitive, away, failed), the block table with block IDs and
  runner status (ok / exit code / late), and the breakdown L = Σ w·μ for every metric of that day.

θ, N and M can be changed in the browser; the gate is recomputed there. In the grid, trends and day
detail, a day carries its phase's gate result if it is counted in that phase. A rolling window over
the last M days (as the Streamlit page evaluates it) can be switched on for these day marks only; it
is labelled "mixes phases" because right after the switch it is mostly baseline days. It is never
used in the summary. Weights and membership
functions come from `app_pcap_to_dsm5/app/fasl_config.json` (re-read on every request).

The Streamlit app in `app_pcap_to_dsm5/app/` is not changed and stays the reference.

Look: as the midterm presentation: Book Antiqua for titles (falls back to Palatino), Arial for text,
red #DC3A4F (subtitle, clinical phase, likelihood ramp) and beige #EBD6C1 (baseline phase, gate bar,
highlights), thin black outlines. Colours live in `web/src/theme.ts` and `web/src/styles.css`; the
device colours (phone blue, laptop tan) were checked for colour-vision separation and contrast.

## How it works

```
~/cmn-data/eval/<dataset>.daily.csv ──────────────┐  (evaluation's daily metric tables, preferred)
~/cmn-data/processed_parquet/<dataset>/*.parquet ─┤
                                                  │  python -m cmn_frontend.export
app_pcap_to_dsm5/app/metrics  (imported, unchanged)┤  one day at a time, incremental
                                                  ▼
                       ~/cmn-data/frontend_cache/<dataset>/<YYYY-MM-DD>.json
                       (all daily metrics + 5-min activity per device)
                                                  │
fasl_config.json ─────┐                           │
~/cmn-data/run/<dataset>.csv, .state.jsonl ───────┤  uvicorn cmn_frontend.api:app  (port 8600)
traffic-runner/config/devices.csv ────────────────┤  scores L_k, gate per phase, joins ground truth
                                                  ▼
                                   React UI (Vite, port 5173 in dev; or built and served by the API)
```

- **Source of the daily metrics**: the evaluation (`evaluation/`, branch `evaluation`) writes the
  same daily rows to `~/cmn-data/eval/<dataset>.daily.csv`. The export takes a day's metrics from that
  table when the table has the day and is newer than the day's partitions, and then only computes the
  5-minute traffic summary (seconds per day). Days the table does not have yet (e.g. today during the
  live run) are computed here with the same code, using the previous rows as history. Days before the
  table's first day (pre-run test captures) are skipped, so the history matches the evaluation's.
  Without a table, every day is computed here.
- **Export** (`backend/cmn_frontend/export.py`, `daily.py`): when computing, it mirrors `compute_all_daily()` of the
  Early Signs page (same partition-to-day rule, hostname enrichment, background filter, base record,
  all nine criteria, previous days as history). It keeps only the resulting row per day, so memory
  stays at about one day of packets (1–3 GB, up to ~7 GB for a 9M-packet day) instead of the 24 GB
  the Streamlit app needs for its in-memory cache. A day is recomputed when its partitions change,
  when the metric code changes, or when an earlier day was recomputed (history-dependent metrics).
  The newest day is marked *incomplete* until a later day has data.
- **Scoring** (`fasl.py`): membership functions and `fasl_score` are ported from the page, which cannot
  be imported (it runs Streamlit at import). `tests/test_fasl_parity.py` extracts the original
  functions from the page source and checks that both give identical results. The gate is the
  page's `gate_present`, applied per phase (`fasl.phase_gate`, shared test cases with the web code in
  `shared/gate_cases.json`). One deliberate difference: unconfigured criteria have no likelihood (the
  page shows 0).
- **API** (`api.py`): only reads the cache. It never computes metrics, so it is light and can run
  while the export is working.
- **UI** (`web/`): React + TypeScript + ECharts. The gate in `src/lib/gate.ts` and the Python gate
  share the test cases in `shared/gate_cases.json`.

Speed: the metric code calls `is_private_ip` per packet in row-wise `apply`, which dominates the run
time. The export memoizes this pure function in its own process (results identical, tested;
`CMN_NO_IP_CACHE=1` disables it). A normal day still takes 0.5–3 min, and a 9M-packet streaming day
several minutes. Computing everything here takes about an hour for three personas with `--jobs 3`; importing
from the evaluation's tables takes about a minute per persona. After that, only new or changed days
are processed.

## Run it (laptop only, not on the gateway)

Prerequisites: Python 3.11+, Node 20+, and the gateway data copied to `~/cmn-data`
(`processed_parquet/` and `run/`, as for the local Streamlit run). Run the evaluation's daily step
first if possible (`~/cmn-data/eval/`); otherwise the export computes the metrics itself.

```bash
cd frontend/backend
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
```

Create logins (stored in `~/cmn-data/frontend/users.json` with scrypt hashes, not in git; the
password is asked for). Profile ids are the lowercase names (`ben`, `maria`, `carl`, or the id of a
person added in the portal):

```bash
.venv/bin/python -m cmn_frontend.users add anna --role single --profile ben
```

```bash
.venv/bin/python -m cmn_frontend.users add dr-meier --role multi --profiles all
```

`--profiles maria,carl` limits a multi-profile user to some people; `list`, `passwd <name>` and
`remove <name>` manage existing logins. A multi-profile user who adds a person can see that person.

Compute or update the per-day cache (every source, plus every person with their own device set;
three in parallel). A new device set is computed once with the full metric code (about an hour for
three weeks of one person); until then the portal says the data is being prepared:

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

The URL keeps the view: `#/<profile>/<day>/<criterion>`, e.g. `#/maria/2026-11-12/C2`, or `#/settings`.

### Settings (environment variables)

| Variable | Default | Meaning |
|---|---|---|
| `CMN_DATA` | `~/cmn-data` | Base folder of the copied gateway data |
| `CMN_PROCESSED` | `$CMN_DATA/processed_parquet` | Parquet partitions |
| `CMN_RUN` | `$CMN_DATA/run` | Plans (`<dataset>.csv`) and runner logs (`<dataset>.state.jsonl`) |
| `CMN_DAILY_TABLES` | `$CMN_DATA/eval` | Evaluation's daily metric tables (`<dataset>.daily.csv`), used when present |
| `CMN_CACHE` | `$CMN_DATA/frontend_cache` | Per-day results: `<source>/` for all traffic, `<source>/@dev-<hash>/` per device set |
| `CMN_HOME` | `$CMN_DATA/frontend` | Logins (`users.json`), person profiles (`profiles.json`), session key |
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
metric code (cache, incremental update, cascade, import from a daily table), logins and sessions
(hashing, expiry, forged tokens), roles (a single-profile user sees only their profile and cannot
configure), a person computed on their own devices only, and the baseline period of live sources.
Web: gate (same cases), formatting, and the overview for scripted and live profiles.

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
