# Feedback → Portal v3: tasks and work split

Sources: [Lukasz Vol. II.txt](Lukasz%20Vol.%20II.txt) (UZH / LiFE) and
[Clemens Vol. II.txt](Clemens%20Vol.%20II.txt) (19.11). Final presentation 08.12 (09.12 also mentioned;
confirm).

Code base: the **v2 portal on branch `frontend-v2`** (Thierry: worktree `~/cmn-frontend-v2`), the
version shown to Clemens. All v3 work starts from there. No priorities and no time plan: every session
below starts now, we see how far we get.

---

## 1. Lukasz Vol. II: what v2 already covers

| Point from the call | Status in v2 | v3 task |
|---|---|---|
| Two layers: quick overview + detail with explanation | ✅ Overview / Timeline / Details | — |
| Deviation from the person's own baseline | ✅ usual range, flags 3 of 7 days > 1.5 SD | — |
| Comparison with a healthy population | ⚠️ interim: pooled baselines of the other personas | D2 |
| Sleep overview "as from a Whoop" | ✅ *Quiet window at night* | — |
| Personalised monitoring per patient | ✅ care plan: focus, risks, sensitivity, normal ranges | — |
| Crisis / self-harm sites as safety signal | ✅ never switched off | — |
| Social network use | ✅ chat sessions, different sites | — |
| Robin Z-like trajectories to discuss with the patient | ✅ Day and night, timeline, notes | — |
| Away periods / routine explain missing traffic | ✅ onboarding, routine, away periods | C1 |
| LLM assistant | ✅ | B1–B3, B5, B6 |
| Sleep regularity | ❌ | D5 |
| Sudden improvement should be discussable | ❌ flags only in the risk direction | E1 |
| Assessment vs. treatment monitoring | ❌ | E2 |
| Mobile data via VPN | 📄 [MobileDataVPN.md](MobileDataVPN.md) | presentation outlook |
| LiFE analysis help, Clemens contact, DIGIT grant (13.01) | team | F |

---

## 2. Visual and icon rules for the whole frontend (V)

Clemens' points, applied to **every** screen (person view, timeline, details, care plan, onboarding,
settings, login, assistant), not only the clinician overview:

1. **Every element answers a question.** For each chart, tile, chip, colour and line: which question does
   it answer, and for whom? If nobody can say it in one sentence, it goes (or into a "Show more" layer).
2. **Red means alert, nothing else.** Red only for: a flag that needs attention, crisis/self-harm sites,
   "present" in the gate, the C9 signal, recording dictation. Activity intensity, likelihood ramps,
   periods, buttons, the assistant tab, the brand subtitle: neutral.
3. **Neutral intensity scale.** One sequential scale for "more / less use" (light warm grey → dark
   brown-grey), lightness only, validated with the palette validator. Used for heatmaps, the 24-hour
   strip, the μ dots and the likelihood grid.
4. **Shading only for the baseline period, in a neutral colour.** The clinical / recent period gets no
   shading; the baseline days get a light neutral band labelled "Baseline (usual weeks)". Applies to all
   charts, the phase strip, pills ("baseline" neutral pill, "recent/clinical" no pill or plain text),
   phase tiles and the plan Gantt.
5. **Every axis labelled with what and unit** (e.g. "minutes in use per hour", "clock time",
   "hours", "count per day", "likelihood 0–1"). Every band and line in a visible legend; "usual range"
   vs. "typical range" clearly different (fill vs. dashed outline) and named the same everywhere.
6. **Icons as eye-catchers** with one fixed meaning each, always with a text label or tooltip:
   night/quiet window (moon), back online (sunrise), time in use (clock), use at night (moon + dot),
   chat (speech bubble), different sites (globe), crisis/self-harm sites (alert triangle, the only red
   icon), irregular nights (zig-zag), notable improvement (arrow, neutral), note (pencil),
   explain (question mark), away (suitcase), device kinds (phone, laptop). Clinicians scan icons, then read.
7. **No unexplained tiles.** Every colour key has a legend; every tile has a tooltip with its value.
8. **Words:** "typical" instead of "healthy people", no "sleep" where we only see quiet devices.

**Shared contract** (so sessions can start before the foundation is merged; names are binding):

- `web/src/theme.ts`: `C.intensity: string[]` (neutral sequential, 8 steps) + `C.intensityWhiteFrom`,
  `C.alert` / `C.alertSoft` (the only reds), `C.baselineShade` (neutral band for the baseline period),
  `C.usualBand` (own usual range, filled), `C.typicalLine` (typical range, dashed outline), `C.change`
  (neutral accent for "notable change"), `PRODUCT_NAME = "Rhythm"`, `PRODUCT_SUBTITLE = "Home network
  overview"`. `C.seq`, `C.clinical`, `C.clinicalTint` are removed.
- `styles.css`: `--accent` becomes ink; `--alert`, `--alert-soft`; `.pill-alert`, `.pill-neutral`,
  `.pill-baseline`; `--red` / `.pill-red` removed.
- `web/src/components/Icon.tsx`: `<Icon name="moon" | "sunrise" | "clock" | "night-use" | "chat" |
  "globe" | "alert" | "irregular" | "change" | "note" | "explain" | "away" | "phone" | "laptop" |
  "person" | "data" | "lock" label?="…" />`, inline SVG, `currentColor`.
- `web/src/lib/chart.ts`: `axisName(label, unit)`, `baselineMarkArea(days)` (the neutral baseline
  band), `usualBand(stats)`, `typicalBand(range)`: one implementation used by every ECharts chart.

---

## 3. Norm data for the reference ranges (D2): what exists

Short answer: **there are no published norms for network-level metrics** (went quiet, back online,
time with traffic, distinct sites, chat sessions). Norms exist for the behaviours these metrics stand in
for: sleep timing and duration, chronotype, sleep regularity, smartphone time and night-time phone use.
They can serve as an external reference **for clinicians only**, labelled as a proxy, next to our own
pooled reference days. The figures below come from abstracts and summaries; K1 checks every value in
the full text before it goes into `norms.json`.

| Our metric | Proxy norm | Population | Figures (to verify) | Source |
|---|---|---|---|---|
| Quiet window length | Overnight sleep duration, actigraphy | 0–18 y, meta-analysis of 79 studies | 15–18 y: ≈ 7.4 h; non-school nights ≈ +56 min; latency ≈ 19 min | Galland et al. 2018, *Sleep* 41(4) ([1]) |
| Quiet window length | Self-reported sleep duration | US, ages 13–32 (Add Health) | 8.5 h at 13 → 7.3 h at 18 → 8.5 h at 22 → 7.7 h at 32 | Maslowsky & Ozer 2014, *J Adolesc Health* ([2]) |
| Went quiet / back online | Sleep onset / offset, actigraphy | 15–18 y | non-school nights: onset ≈ 1 h, offset ≈ 2 h later | Galland et al. 2018 ([1]) |
| Went quiet / back online | Bedtime / wake time from a phone app | ≈ 6–8 k users, 100+ countries | by age and country; bedtime, not wake time, drives duration | Walch, Cochran & Forger 2016, *Sci Adv* ([3]) |
| Late vs. early (owls/larks) | Chronotype, MSF (MCTQ) | ≈ 25 k Germans, 10–65+ | latest around age 20 (≈ 17 in women, ≈ 21 in men) | Roenneberg et al. 2004, *Curr Biol* ([4]) |
| Irregular nights | Night-to-night variability of onset / offset | global wearables, adults | onset variability ≈ constant over adult age; higher on weekends | Jonasdottir et al. 2021, *Sleep* 44(2) ([5]) |
| Irregular nights | Sleep Regularity Index (SRI) | UK Biobank, ≈ 61 k adults (older) | median 81, IQR 73.8–86.3 | Windred et al. 2024, *Sleep* ([6]) |
| Irregular nights | SRI in adolescents | 46 healthy adolescents (Bern) | small sample, not a norm; link to depressive symptoms | Castiglione-Fontanellaz et al. 2023, *J Sleep Res* ([7]) |
| Time in use | Online time, self-report | Swiss 12–19 y (JAMES 2024) | ≈ 3 h 07 weekday, ≈ 4 h 30 weekend | JAMES 2024, ZHAW ([8], [9]) |
| Time in use | Smartphone time, passively logged | US adolescents (ABCD) | ≈ 5 h/day, ≈ 2 h more than self-report | Scientific Reports 2024 ([10]) |
| Use at night | Phone use 00:00–04:00, logged | 657 adolescents (ABCD) | about half used the phone in that window | JAMA Pediatrics 2026 ([11]) |
| Use at night | Late-night phone use, logged | US adolescents (SBU MEDiA) | ≈ 46 min per late night | SLEEP 2026 abstract ([12]) |
| Chat sessions, different sites, crisis sites | — | — | **no external norm**; own baseline + pooled reference only | — |

How we use it (K1):

- **Percentile ranges, not mean ± SD.** Typical range = P16–P84 (the central 68 %, ±1 SD under a normal
  distribution); position as a percentile ("went quiet later than 85 % of reference nights"); status
  *within / above / below* the typical range. From pooled reference days: empirical percentiles. From a
  published mean ± SD: percentiles under a normal assumption, marked as such.
- **Two reference sources, switchable:** `pooled` (other people's usual weeks, as now) and `external`
  (`norms.json`, by age band and school/free day, with citation, population and proxy note). The UI
  shows which one is used and its source.
- **Proxy caveats in the data, not just in the text:** the quiet window is only an upper bound for sleep
  opportunity (asleep, away and phone off look the same; phone in bed shortens it); time with traffic ≠
  screen time (background traffic, shared devices; home Wi-Fi only). Every external entry carries its
  caveat, the clinician sees it on hover.
- **Owls and larks are not flagged:** reference flags only outside the typical range on several days,
  never against a single average; the own baseline stays the first comparison.
- **Ask LiFE** for norm data from their questionnaires / EMA (sleep times of their adolescents), which
  would fit the target age better than any of the above.

[1]: https://researchnow.flinders.edu.au/en/publications/establishing-normal-values-for-pediatric-nighttime-sleep-measured/
[2]: https://pmc.ncbi.nlm.nih.gov/articles/PMC4090255
[3]: https://www.sciencedaily.com/releases/2016/05/160506160105.htm
[4]: https://pure.rug.nl/ws/files/6682390/2004CurrBiolRoennebergSupp.pdf
[5]: https://orbit.dtu.dk/en/publications/gender-differences-in-nighttime-sleep-patterns-and-variability-ac/
[6]: https://researchnow.flinders.edu.au/en/publications/sleep-regularity-is-a-stronger-predictor-of-mortality-risk-than-s/
[7]: https://boris.unibe.ch/179353
[8]: https://www.zhaw.ch/storage/hochschule/medien/news/2024/241128_MM_JAMES-Studie/JAMES_Studie_2024.pdf
[9]: https://www.fr.ch/de/fritic/digitale-muendigkeit/forschungsergebnisse
[10]: https://www.ncbi.nlm.nih.gov/pmc/articles/PMC11297944/
[11]: https://www.contemporarypediatrics.com/view/adolescents-average-50-minutes-of-smartphone-use-during-school-nights
[12]: https://www.newswise.com/articles/bedtime-smartphone-use-predicts-overnight-phone-activity-in-teens

---

## 4. All tasks

**A. Person view** — A1 neutral product name, for now **"Rhythm"** with the subtitle "Home network
overview" (title, login, assistant prompt, API title; one constant per side so the final name is a
one-line change) · A2 "Data collected / not collected" label at the top (App-Store style) + "Your care
team also sees: …" · A3 "What stands out" **removed** from the person view (decided) ·
A4 layer 1 = week table (time in use, went quiet, back online per day), charts behind "Show charts",
toolbar hidden by default · A5 wording "Devices quiet at night" instead of "Quiet window" · A6 person
timeline: one line per day, labelled 0–24 h strip, no unexplained tiles.

**B. Assistant** — B1 short, answer-relevant replies (answer first, 1–3 sentences, from the week
overview; no unrequested "what it can imply") · B2 controls under each answer: Shorter (−), More detail
(+), 2–3 follow-ups · B3 person guardrail: observations only, no reasons/meaning/symptoms even on repeated
asking, point to the care team · ~~B4 disclaimer in the UI~~ → **presentation only** (see §7) · B5
reliability eval (≈ 20 questions per role on the scripted personas; numbers must exist in `<results>`,
no clinical terms for the person, refusal to diagnose) · B6 local model (OpenAI-compatible endpoint on a
laptop, e.g. Ollama / llama.cpp / LM Studio, over Tailscale), B5 eval also on it.

**C. Onboarding** — C1 detect missing routine fields deterministically and ask targeted follow-up
questions (with dictation), answers fill the form again.

**D. Clinician view** — D1 "healthy people" → "typical" / "reference group" everywhere · D2 percentile
reference ranges with pooled + external norms (§3) · D3 neutral colours, red only for alerts (now part of
V) · D4 axes and legends (now part of V) · D5 "Irregular nights" risk (variability of went-quiet time /
quiet-window length over 7 nights vs. baseline) + icons on flags (V6) · D6 scalable patient selector
(searchable list, attention icons per person) · D7 plain-language "what contributed" per criterion; z,
w, μ behind "Show model details" · D8 "About the data" tab (what the network sees / cannot see, no
search terms or page content, observability per criterion) · D9 care plan with clinicians (team, F).

**E. Lukasz gaps** — E1 "notable change" flags in the other direction, neutral, "to discuss" · E2 care-
plan purpose *assessment* (status vs. typical range first) or *treatment monitoring* (change over time
first, improvements shown).

**V. Visual and icon rules (§2)** applied to every screen; **S. Baseline-only neutral shading** (§2.4).

---

## 5. Work split

### 5.1 Git setup (Thierry, once, before the sessions start)

1. `git switch frontend-v2 && git switch -c frontend-v3 && git push -u origin frontend-v3` — the
   integration branch.
2. Every session: its own branch `v3/<id>-<slug>` from `frontend-v3`, in its own worktree
   (Claude Code session with worktree, or `git worktree add ../cmn-v3-<id> -b v3/<id>-<slug> origin/frontend-v3`),
   PR into `frontend-v3`. Karla: `git fetch origin && git worktree add …` on her laptop the same way.
3. **T0 is merged first** (small); every other session rebases on `frontend-v3` once T0 is in, and
   codes against the contract in §2 until then.
4. Shared files with additive edits only: `web/src/api.ts` (types: add, never rename; conflicts resolved
   by keeping both), `backend/cmn_frontend/api.py` (new endpoints / fields in separate functions).
   `README.md` and `process.md` are updated only by T5 at the end; sessions write their notes into
   the PR description.
5. Dev: each laptop runs the backend on its own copy of `~/cmn-data` (the gateway data already synced);
   two sessions on one laptop use different ports (API 8600, 8602, 8603, … since 8601 is Whisper;
   Vite 5173, 5174, …).

### 5.2 API contract between Karla (backend) and Thierry (UI)

Added to the observed block of `/api/profiles/{pid}/timeline` (K1 writes it, T1/T2 render it; until it
exists the UI falls back to the v2 fields):

```ts
reference?: {
  source: "pooled" | "external";
  label: string;                         // "typical (other people's usual weeks)" / "typical 15–18 y, actigraphy"
  tracks: Record<string, { p16: number; p50: number; p84: number; n?: number; citation?: string; proxy_note?: string }>;
};
percentile_ref?: Record<string, number | null>;        // per day and track, 0–100
// flags gain:
kind: "risk" | "change";                 // change = notable improvement (E1), neutral colour
icon: string;                            // one of the Icon names in §2
// new track + risk:
track "quiet_start_sd7" (min), risk "irregular_nights" (icon "irregular")
```

Care plan (K5 writes, T3 reads for the selector): `care.purpose: "assessment" | "treatment"`.
Person attention summary (K1 adds to `/api/profiles`): `attention: { flags: number; alert: boolean }`.

### 5.3 File ownership

| File / area | Owner session |
|---|---|
| `theme.ts`, `styles.css` tokens, `Icon.tsx`, `lib/chart.ts`, `VISUAL.md` | **T0** |
| `Overview.tsx`, `Timeline.tsx`, new `DataLabel.tsx`, `WeekTable.tsx`, `lib/observed.ts` | **T1** |
| `MetricTrends.tsx`, `DayDetail.tsx`, `Heatmap.tsx`, `HourlyHeatmap.tsx`, `CriteriaSummary.tsx`, `UnscoredMetrics.tsx`, `ObservabilityCard.tsx`, new `AboutData.tsx`, `Chart.tsx` | **T2** |
| `App.tsx`, `Login.tsx`, `ProfileSettings.tsx`, `Assistant.tsx`, `Markdown.tsx`, new `PersonPicker.tsx` | **T3** |
| `observed.py`, new `norms.py` + `norms.json`, `profiles.py` (attention), `tests/test_observed.py` | **K1** |
| `assistant.py` (prompts, context), `settings.py` (`PRODUCT_NAME`), new `tests/test_assistant_rules.py`, new `eval/assistant_eval.py` | **K2** |
| new `llm.py` (provider layer), `assistant.py` only `stream_answer`/`stream_claude`/settings class, `setup_assist.complete_json`, `AssistantSettings.tsx`, `deploy/` for the LLM host | **K3** |
| `setup_assist.py` routine part, `Onboarding.tsx`, `RoutineForm.tsx`, `Dictate.tsx` | **K4** |
| `care.py`, `CarePlan.tsx`, `tests/test_care.py` | **K5** |
| `README.md`, `process.md`, deploy of v3, screenshots | **T5** (last) |

Every session applies the visual rules (§2) to the files it owns, so the V/S work is spread over
T1, T2, T3, K3, K4, K5; T0 only provides the tools.

### 5.4 Thierry (frontend structure and visuals)

**T0 — Visual foundation** (short, merge first). Tokens, icons and chart helpers exactly as in the §2
contract; neutral intensity scale validated (palette validator, CVD, contrast); `VISUAL.md` with the
eight rules and the icon table; replace `C.seq` / `C.clinical` / `C.clinicalTint` / `.pill-red` in the
theme so old names fail to compile (the owning sessions fix their files). *Done when:* build passes
with the old names only referenced in files owned by other sessions, and `VISUAL.md` exists.

**T1 — Overview and timeline (person + clinician).** A1–A6 for the person; for clinicians: flag tiles
with icons (V6), typical range from `reference` (dashed) vs. usual range (filled) with legend (D2 UI),
"typical" wording (D1 UI), irregular-nights and "notable change" flags rendered (D5/E1 UI), baseline-only
neutral shading in Day and night / Quiet window / Day by day, labelled axes. *Done when:* the person page
has the data label, week table and optional charts, no red except alerts, and `Timeline.test.tsx` /
`observed.test.ts` pass.

**T2 — Details tab and About the data.** D7 plain-language contributions from the L = Σ w·μ breakdown
(top metrics and outlier days per criterion), z / w / μ behind "Show model details"; D8 `AboutData.tsx`
from the observability data (+ "no search terms or page content"); neutral intensity in both heatmaps
and the μ dots; baseline-only shading in MetricTrends / UnscoredMetrics / phase strip / Gantt / phase
tiles / day pill; red only for present, C9 signal, episode; every y-axis labelled. *Done when:* no
`C.seq`/`clinicalTint` left in these files and `CriteriaSummary.test.tsx` passes.

**T3 — App shell, selector, assistant panel.** A1 title in header and login (name from the decision
in §8, behind one constant); D6 `PersonPicker.tsx` (search, list, attention icons from
`profiles[].attention`, works for 300 people); D8 "About the data" tab wired in; tab icons; B2 controls
under each answer (Shorter, More detail, follow-ups from the current focus); assistant tab and primary
buttons in ink (rule 2). *Done when:* switching between 3 and 300 generated profiles works and the
assistant shows the controls.

**T5 — Integration (at the end).** Merge order T0 → K1 → T1/T2 → rest; README v3 section, process log
entries for both calls and the v3 work, deploy v3 next to v2 (`switch-gateway.sh`), before/after
screenshots for the report and the presentation.

### 5.5 Karla (data, models, LLM)

**K1 — Reference ranges and new flags (backend).** D2: verify the §3 figures in the full texts, write
`norms.json` (value, age band, school/free day, citation, proxy note), `norms.py` (normal-assumption
percentiles), empirical percentiles for the pooled reference, `reference` / `percentile_ref` fields
as in §5.2; D1 wording in all flag texts; D5 `irregular_nights` (SD of went-quiet time over the last 7
nights vs. the baseline's rolling SD); E1 `kind: "change"` flags in the improving direction; `icon` per
flag; `attention` per profile. *Done when:* `test_observed.py` covers percentiles, both reference
sources, irregular nights and change flags, and the evaluation numbers of the gate are unchanged.

**K2 — Assistant behaviour and reliability.** B1 prompts (answer first, short, week overview; person
replies ≤ ~80 words unless "More detail"); B3 person guardrail incl. repeated asking; prompt support for
the B2 controls ("Shorter" / "More detail" messages); A1 product name in the prompt; "typical" wording;
B5 `eval/assistant_eval.py`: question set per role and persona, checks (numbers present in the context,
forbidden-term list for the person, no diagnosis), results table as Markdown for the report.
*Done when:* the eval runs against Claude and writes the table; `test_assistant_rules.py` checks the
prompt rules offline.

**K3 — Local model.** B6: `llm.py` with two providers (Anthropic, OpenAI-compatible local endpoint),
`assistant.py` and `setup_assist.complete_json` call it (JSON mode / schema for the local path),
`AssistantSettings.tsx` provider choice (with the visual rules), setup notes for running the model on a
laptop and reaching it from the mini-PC over Tailscale; run K2's eval on the local model. *Done when:*
the portal answers and fills the routine with the local model on the gateway demo setup.

**K4 — Onboarding asks for what is missing.** C1: `missing_fields(routine)` (times null, weekdays
still at the default, no devices, no free-day times) → template questions; `Onboarding.tsx` shows them
one by one with dictation; answers go through `suggest_routine` again and merge; visual rules on
Onboarding / RoutineForm / Dictate (icons for away / home / free, no red except recording). *Done when:*
a description without times leads to questions and a complete form; `RoutineForm.test.tsx` and
`Dictate.test.tsx` pass.

**K5 — Care plan.** E2 `purpose` (assessment / treatment) in `care.py` + `CarePlan.tsx`, effect: which
comparison the overview shows first (T1 reads `care.purpose`) and whether change flags are on by
default; visual rules on the care plan (icons for risks matching the flag icons, no red except the
crisis-site risk); prepare the clinician question list (F) from what the care plan asks. *Done when:*
`test_care.py` covers `purpose` and the care plan follows `VISUAL.md`.

### 5.6 Parallel sessions per laptop

All sessions in one column can run at the same time; they own disjoint files.

| Thierry's laptop | Karla's laptop |
|---|---|
| T0 (first, short) → then T1 | K1 |
| T2 | K2 |
| T3 | K3 |
| — | K4 |
| — | K5 |
| T5 at the end | — |

Dependencies: T1 renders K1's fields (falls back to v2 fields until K1 is merged); T3's attention icons
need K1's `attention`; K3 and K2 both touch `assistant.py` (different functions; K3 rebases on K2);
T1 reads K5's `purpose`. Everything else is independent.

---

## 6. Not code (team)

- **Thierry:** send Clemens date, time and place of the final presentation; ask Lukasz whether his and
  Mia Bachmann's names may be passed to Clemens (Clemens asked), then connect them (also covers Lukasz'
  wish for help with the LiFE passive-sensing analysis).
- **Karla:** question list to LiFE (red flags positive and negative, norm data from their
  questionnaires/EMA, care-plan fields); DIGIT Innovation Grant (€75k, 1 year, deadline 13.01): decide
  with Bruno and Lukasz.

## 7. For the presentation (verbal, not in the UI)

- **B4:** the assistant sends questions and derived results to Anthropic (USA); this is a proof of
  concept, a clinical deployment needs an in-house model (show K3's local model if it works).
- Limits: no published norms for network metrics (proxies only), small reference group, home Wi-Fi only
  (VPN plan as outlook), the assistant's explanations are evaluated (B5) but not validated clinically.

## 8. Decisions

1. Product name (A1): placeholder **"Rhythm"** ("Home network overview") until the final name is chosen.
   Frontend: `PRODUCT_NAME` / `PRODUCT_SUBTITLE` in `web/src/theme.ts` (T0); backend:
   `PRODUCT_NAME` in `backend/cmn_frontend/settings.py` (K2). The thesis title stays only in an
   "About" line.
2. "What stands out" is dropped from the person view (A3). The clinician view keeps its flags.
