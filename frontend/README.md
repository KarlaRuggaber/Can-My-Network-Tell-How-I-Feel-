# Results portal

A results portal for router-level network metrics → DSM-5 criterion likelihoods, per person. It does
not depend on where the traffic comes from: a **source** is any folder of Parquet captures in
`processed_parquet/` — a scripted gateway run (Ben: insomnia, Maria: MDD with suicidality overlay,
Carl: social anxiety) or live home traffic.

**Logins and roles** (as the Streamlit app, a login comes first; the portal looks the same for all):

- *Single-profile user* (the person themself): a simpler, friendly view of their own profile:
  four everyday areas (daily rhythm, variety and social contact, sleep, focus) with "as usual / a
  few different days / noticeably different" for the recent days, and daily network activity. The
  server never sends them expected outcomes, condition, persona description, scripted plan, DSM
  criterion names, or source and device names (these name the scripted condition), so the view
  cannot suggest symptoms (no expectation or placebo effect).
- *Multi-profile user* (clinician, parent): chooses between their profiles, can adjust the gate,
  and under **People and devices** adds people, picks their traffic source, assigns which devices
  (local IP addresses seen in that source) belong to whom, and sets the baseline period.

**Person profiles**: a name, a source, and either all devices of the source or a device set. With a
device set, the metrics are computed on that person's traffic only (several people behind one
router stay apart). Scripted sources bring their plan (baseline and clinical phase, ground truth,
§9 expectations); live sources use the profile's baseline period (default: the first 14 days with
data), and every later day is "recent". The three scripted personas are created as profiles on the
first start, with all devices of their source, so their numbers stay those of the evaluation.

**Assistant** (explanation layer, off by default): questions in natural language about the
results shown, answered only from the profile's derived daily results (likelihoods, metric values,
μ, w, baseline mean ± SD, gate per period). It never gets raw packets, IP addresses, hostnames or
device names and must not diagnose. Persons get everyday language without clinical terms or
expectations; clinicians get criterion names and, for scripted personas, the script's expectations
marked as such. A multi-profile user turns it on under **Settings → Assistant** and enters the
Claude model and the Claude API key there (stored in `~/cmn-data/frontend/assistant.json`,
owner-only, never sent back to a browser; `ANTHROPIC_API_KEY` also works). The assistant uses
Anthropic's Claude only (default Claude Sonnet 5.5, `claude-sonnet-5-5`, official SDK, with
server-side refusal fallback; the project key does not include Opus or Fable). The question and the
derived results go to Anthropic, so use it with the scripted data, or with live data only where
participants agreed.

**Two layers** (v2; the earlier single-layer version is tagged `frontend-v1`):

1. **Overview — what the network observed**, in real units, against the person's usual range (mean
   and SD over the baseline days), for everyone:
   - *What stands out*: risk flags over the recent days, not single days, e.g. "Later nights: on 4 of
     the last 7 nights Maria went quiet later than usual" (at least 3 of the last 7 days beyond
     1.5 SD in the risk direction). Crisis or self-harm sites are flagged as soon as they rise above
     the usual level (clinicians and parents only). Flags can be marked as seen; a new day brings
     them back.
   - *Day and night*: minutes in use per hour, with night shading and midnight lines (as in Robin Z),
     range presets and a date range.
   - *Quiet window at night*: when the devices went quiet and came back online (the longest stretch
     without use overlapping 00:00–06:00; a check of up to 15 min between 00:00 and 05:00 does not end
     it), with use during the night as dots. Called "quiet window", not sleep: asleep, away or
     switched off look the same from the network.
   - *Day by day*: time in use, use at night, chat sessions, different sites (and crisis or
     self-harm sites), with legend chips to hide or highlight rows.
   - *Compared with healthy people* (clinicians and parents): every day is also compared with a
     healthy reference, the pooled days of the other people that count as healthy (by default the
     scripted personas' baseline weeks, which live a healthy everyday profile from
     `profiles/tier0-healthy`; healthy volunteers can be added with "Healthy reference: all days"
     under Settings). The person's own source is never part of it. Its flags ("Later nights than
     healthy people") use the same rule and work from the first week, before an own baseline exists.
     With two or three people the reference is small and mixes lifestyles (student vs. office job),
     so a difference can reflect a lifestyle rather than health; it needs more healthy people of the
     target age before it is used clinically. The person does not see this comparison.
     (`gw_student_a` on the gateway is not a healthy reference: its devices run only the runner's
     background mode, no user; it is useful for tuning the "in use" cutoff instead.)
   "In use" = at least `CMN_ACTIVE_PACKETS` (default 50) packets in 5 minutes. Scripted devices are
   silent between blocks; real phones send background traffic, so tune this on a real device.
2. **Timeline — day by day**: one card per day, newest first, with the quiet window, a 24-hour strip
   of use and what was clearly different from usual; clinicians and parents add notes (holidays,
   exams, a move to outpatient care), stored in `notes.json` and also given to their assistant.
3. **Details — the model** (clinicians and parents), the previous view, plus *What the network can
   tell*: how well each criterion C1–C9 can be observed (good / partial / barely), what the network
   sees and cannot see, from `profiles/symptom-network-mapping.md` §3 and §8 (`observability.py`).
4. **Care plan** (clinicians and parents) and **onboarding** (the patient), stored in `care.json`:
   - At first login the patient goes through a short onboarding: what is and is not measured, their
     week (per weekday away / at home / free, usual times), their devices in plain words, anything
     else and away periods. They can change it later under **My week**. The assistant can fill the
     form from a description in their own words.
   - The care plan shows the setup status, lets clinicians and parents complete the routine, link
     each named device to an address seen on the network, add away periods, write the history,
     concerns and treatment, choose the **criteria in focus** (with their observability), the risks
     to flag with a **sensitivity** (strict: 2 of 7 days beyond 1 SD; standard: 3 of 7 beyond 1.5 SD;
     relaxed: 4 of 7 beyond 2 SD) and **normal ranges** that replace the learned ones. The assistant
     can suggest the focus from the notes; it never switches off the crisis or self-harm sites flag.
     Suggestions only fill the forms; nothing is saved until a person saves.
   - Effect on the analysis: usual ranges per day type (away, at home, free) once there are 5
     baseline days of a type; away periods are left out of usual ranges and flags; flags follow the
     focus and sensitivity; a normal range set by the clinician decides what counts as different.
   - The patient never sees the clinical setup. The assistant (clinicians and parents) gets the
     care plan including the history, which is sent to Anthropic (Claude).
5. **Explain with the assistant**: click a value in the daily grid (likelihood, C9 signal, gate), a
   flag, a timeline chip, a C9 hit or a day's criterion score, and the assistant panel opens with a
   question about exactly that value.
6. **Dictation** (local speech to text): a microphone button in the free-text fields (describe your
   week, note, history, concerns, treatment, timeline notes, assistant question). The browser records
   the clip; the portal checks the login and passes it to a Whisper service on the same machine
   (`whisper/server.py`, faster-whisper, model `small` int8 by default), which returns the text in
   the language spoken. The audio does not leave the machine and is not stored, and no API key is
   needed. The button only appears when the service runs and the browser may use the microphone
   (HTTPS or localhost).

For clinicians and parents the Details tab shows:

For multi-profile users the Details tab shows:

- **Baseline vs. clinical (or recent) period**: every scored DSM-5 criterion with, for scripted
  personas, the outcome expected in the profile's §9 (`profiles/tier2-clinical/*.md`) and two gate results side by side, each computed
  on that phase's own days only: "Baseline (26.10–08.11)" and "Clinical (09.11–22.11)", with the days
  with L ≥ θ (n of the days counted) and present/absent, plus the episode per phase. The warm-up day
  and the day still being ingested are not counted. While the clinical phase has fewer than M days
  the result is marked *preliminary*. This is the same rule as the evaluation
  (`evaluation/compare.py` `score_phases()`), and the numbers match it.
- **Daily likelihoods**: a day × criterion grid of L<sub>k</sub> with the baseline/clinical phase,
  days ≥ θ, "present" according to the DSM gate, number of present criteria and the episode flag.
- **When the devices were online**: a day × hour grid of packets (log scale relative to the
  person's own hours), so late nights, early waking and quiet days show up as patterns.
- **Other criteria (not scored)**: the metrics the thesis code computes for criteria without weights in
  `fasl_config.json` (currently C3, C5, C6, C7, C9), as raw daily values. A C9 (suicidality) metric
  above its baseline (mean + 2 SD, or above zero when it was always 0) is flagged here and as a row
  in the daily grid; it stays outside the gate. Never shown to the person.
- **Episodes**: an episode needs 5 present criteria including a core one. With the current
  configuration only 4 criteria are scored, so the portal says that an episode is not possible
  instead of showing "no".
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

Look: Book Antiqua for titles (falls back to Palatino), Arial for text, thin black outlines, beige
surfaces. Since v3, red means an alert and nothing else, and intensity uses a neutral scale (see
[VISUAL.md](VISUAL.md) and "v3" below). Colours live in `web/src/theme.ts` and `web/src/styles.css`;
the device colours (phone blue, laptop tan) were checked for colour-vision separation and contrast.

## v3: second round of expert feedback (tag `frontend-v2` is the version shown to the experts)

v3 builds on v2 and follows the second calls with the UZH child and adolescent psychiatry team (LiFE)
and with a UX / data-science reviewer. The tasks, the norm research and how the work was split are in
[`process/Feedback-v3-Plan.md`](../process/Feedback-v3-Plan.md). Main changes:

- **Name and look.** The portal is called **Rhythm** ("Home network overview"; placeholder, one
  constant in `web/src/theme.ts` and `backend/cmn_frontend/settings.py`); the thesis title is only an
  "About" line. Visual rules in [VISUAL.md](VISUAL.md), applied to every screen: every element answers
  a question; red only for alerts (crisis or self-harm sites, "present", the C9 signal); one neutral
  intensity scale; only the baseline period is shaded, in a neutral colour (the clinical / recent
  period is not); every axis is named with its unit; fixed icons with one meaning each
  (`web/src/components/Icon.tsx`); buttons and the assistant tab in ink.
- **Person view.** A "What this page is based on" label at the top (collected / not collected, like
  an App Store privacy label, plus what the care team also sees). Layer 1 is a table of the last 7
  days (time in use, went quiet, back online, and the usual weeks); the charts are behind "Show
  charts". "What stands out" is gone for the person. "Devices quiet at night" instead of "Quiet
  window". The timeline has one line per day with a labelled 0–24 h strip.
- **Typical range instead of "healthy people"** (`observed.py`, `norms.py`, `norms.json`). The
  reference is a percentile range P16–P84 (the central 68 %), with the position as a percentile
  ("later than 85 % of reference nights"). Two sources: `pooled` (default: other people's usual days)
  and `external` (published norms by age band, 15–18 and 19–24 y, with citation, population and a proxy
  note; only sources that publish a spread between people give a range). There are no published norms
  for network metrics, so every external entry is a proxy (sleep duration, screen time). Switch with
  `?reference=external&age_band=15-18` or `CMN_REFERENCE_SOURCE` / `CMN_NORM_AGE_BAND`.
- **New flags.** "Irregular nights" (SD of the went-quiet time over 7 nights against the baseline's).
  "Notable change" flags in the improving direction (earlier nights, more chats, …), neutral, "to
  discuss"; on by default, a clinician can switch them off in the care plan. Every flag carries
  `kind` and `icon`.
- **Clinician view.** A searchable person picker that works for hundreds of people, with an
  attention marker per person (new flags, crisis sites). Flag tiles with icons. The care plan has a
  **purpose**: *assessment* shows the comparison with the typical range first, *treatment monitoring*
  the change against the own usual weeks first. Details: a plain-language "What contributed" sentence
  per criterion; z, w and μ behind "Show model details". A separate tab **About the data**: what the
  network can and cannot see (no search terms, no page content, no messages) and how well each
  criterion can be observed.
- **Onboarding** asks for what the description of the week left open (times, free days, devices),
  one question at a time, typed or dictated (`setup_assist.missing_fields`, rule-based).
- **Assistant.** Answers first, short (from a week overview in the context); "− Shorter" and "+ More
  detail" under the latest answer, plus follow-ups from the current view. The person only gets
  observations: no reasons, meanings, symptoms or diagnoses, also on repeated asking, and is pointed to
  the care team. Eval: `backend/eval/assistant_eval.py` (40 questions on the three personas; results in
  `backend/eval/results/`).
- **Local model.** The assistant can run on a model on our own machines instead of Anthropic
  (`backend/cmn_frontend/llm.py`, any OpenAI-compatible endpoint). Settings → Assistant → Local model.
  Setup, model choice, context length and the gateway over Tailscale: [deploy/local-llm.md](deploy/local-llm.md).
  Measured on a 48 GB MacBook with a 4-week profile (≈ 24k tokens of context): `qwen3.8:27b-mlx`
  ≈ 5 min for the first answer and correct; `qwen3.5:35b-mlx` with thinking off
  (`CMN_LOCAL_EXTRA_BODY='{"reasoning_effort": "none"}'`) ≈ 35 s, but it mixed up days with full
  confidence. A clinical deployment needs an in-house model either way.

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
  the Streamlit app needed for its in-memory cache before 17.11 (since PR #17 the app also computes
  one day per process, peak 3.8 GB for a 9M-row day; `app/metrics/daily_cache.py`). A day is recomputed when its partitions change,
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

Speed: the metric code used to call `is_private_ip` per packet in row-wise `apply`, which dominated
the run time. The export memoizes this pure function in its own process (results identical, tested;
`CMN_NO_IP_CACHE=1` disables it). Since PR #17 (17.11) the metric code itself checks each distinct
address only once (`private_ip_mask`, `outbound_mask`, `inbound_mask` in `metrics/common.py`), so the
memoization adds little; the timings below were measured before that change. A normal day still takes 0.5–3 min, and a 9M-packet streaming day
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

Optional, for dictation: start the local Whisper service in a third terminal (the first start
downloads the model, about 0.5 GB):

```bash
cd frontend/whisper && python3 -m venv .venv && .venv/bin/pip install -r requirements.txt
```

```bash
cd frontend/whisper && WHISPER_PRELOAD=1 .venv/bin/uvicorn server:app --host 127.0.0.1 --port 8601
```

For the video, build the UI once; the API then serves it at http://127.0.0.1:8600 (one process):

```bash
cd frontend/web && npm run build
```

### Deploy (one laptop, reachable by the team)

1. Build the UI once (and after every UI change): `cd frontend/web && npm run build`. The API then
   serves it, so one process is enough: `.venv/bin/uvicorn cmn_frontend.api:app --host 127.0.0.1 --port 8600`
   → http://127.0.0.1:8600.
2. Keep the data current in a second process: `.venv/bin/python -m cmn_frontend.export --jobs 3 --watch 900`.
3. Create logins with `python -m cmn_frontend.users` (see above). The assistant is turned on in the portal.
4. To let others in, keep the API on 127.0.0.1 and publish it inside the tailnet only (the gateway
   already uses Tailscale): `tailscale serve --bg 8600` gives an HTTPS address that only members of
   the tailnet can open. Start the API with `CMN_COOKIE_SECURE=1` then, so the login cookie is only
   sent over HTTPS.

### Deploy on the gateway mini-PC (reachable only in the tailnet)

The mini-PC serves the portal; the laptop keeps computing (the export needs 1–3 GB per day and up to
~7 GB for a heavy day, which the mini-PC cannot spare during the live run). Files in `deploy/`:

| File | Purpose |
|---|---|
| `Dockerfile`, `docker-compose.yml` | Container `cmn-portal-v3` on top of the app's `app-app` image, host network, `127.0.0.1:8620` only, 512 MB limit, data mounted read-only, own home `/var/lib/cmn-portal-v3/home` |
| `../whisper/Dockerfile` | Container `cmn-whisper` (dictation), same base image, `127.0.0.1:8601` only, 1.5 GB and 2 CPU limit, model kept in `/var/lib/cmn-whisper/models` and unloaded after 10 idle minutes. Started by v2's compose project and shared by v2 and v3 |
| `deploy-gateway.sh` | Builds the UI, copies the code to `/opt/cmn-portal-v3/frontend`, copies v2's home (logins, people, care plans, notes, assistant settings) on the first deploy, (re)builds and starts the container |
| `switch-gateway.sh v1\|v2\|v3 [--keep]` | Points the tailnet URL to v1 (`8600`), v2 (`8610`) or v3 (`8620`) and stops the others (with `--keep` they keep running); `status` shows what runs |
| `sync-gateway.sh [--watch 900]` | Pulls new partitions and plans and v2's `profiles.json`, runs the export on the laptop, pushes the day records to `/var/lib/cmn-portal/cache` (read by v1 and v2) |
| `gateway.env.example` | Host, user, key and sources; copy to `gateway.env` to change them |

One-time steps:

1. Tailscale admin console → DNS → enable **HTTPS Certificates** (needed by `tailscale serve`).
2. `frontend/deploy/deploy-gateway.sh`, then `frontend/deploy/sync-gateway.sh`.
3. Logins on the mini-PC: `sudo docker exec -it cmn-portal-v3 python -m cmn_frontend.users add …`
   (or copy `users.json` from the laptop to `/var/lib/cmn-portal-v3/home/`). The assistant is set up
   in the portal under Settings → Assistant.
4. Publish in the tailnet: `switch-gateway.sh v3` (runs `sudo tailscale serve --bg 8620`) and allow HTTPS on `tailscale0` in
   `/etc/nftables.conf` (`iifname "tailscale0" tcp dport 443 accept`, after a backup and
   `sudo nft -c -f`). The portal is then at `https://minipc.<tailnet>.ts.net`.

**v1, v2 and v3 side by side.** v1 (tag `frontend-v1`) stays installed in `/opt/cmn-portal`
(container `cmn-portal`, port 8600, home `/var/lib/cmn-portal/home`), v2 (tag `frontend-v2`) in
`/opt/cmn-portal-v2` (container `cmn-portal-v2`, port 8610, home `/var/lib/cmn-portal-v2/home`, plus
the dictation container), and v3 runs from `/opt/cmn-portal-v3`. v2's files were deployed from the
`frontend-v2` branch; `deploy-gateway.sh` on this branch only deploys v3. Only one version is shown at
the tailnet URL, and the others are stopped to free memory. A stopped container keeps its image and
data and stays stopped after a reboot. For before/after screenshots, run `switch-gateway.sh v2` (or
`v1`), and `switch-gateway.sh v3` afterwards. v3 has its own home, so care plans, notes and logins
added in v3 after the first deploy do not appear in v2, and `sync-gateway.sh` takes the people from
v3's home.

Rollback: `switch-gateway.sh v2` shows v2 again; `sudo docker compose -f
/opt/cmn-portal-v3/frontend/deploy/docker-compose.yml down` removes v3's container (its home stays).

Do not put it on the public internet: the data is personal (health-related inferences), and the
login has no rate limiting or second factor.

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
| `CMN_ACTIVE_PACKETS` | `50` | Packets per 5 minutes from which a device counts as "in use" (quiet window, time in use) |
| `CMN_COOKIE_SECURE` | unset | `1` marks the login cookie HTTPS-only (set it behind `tailscale serve` or another HTTPS proxy) |
| `CMN_WHISPER_URL` | `http://127.0.0.1:8601` | Local Whisper service for dictation; `off` hides the microphone buttons |
| `WHISPER_MODEL`, `WHISPER_COMPUTE`, `WHISPER_THREADS`, `WHISPER_LANGUAGE`, `WHISPER_IDLE_UNLOAD` | `small`, `int8`, `2`, detect, `600` | Settings of the Whisper service itself (see `whisper/server.py`) |

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
