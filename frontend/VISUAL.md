# Visual rules (portal v3)

These rules apply to every screen: person view, timeline, details, care plan, onboarding,
settings, login and assistant. The tools are `web/src/theme.ts`, `web/src/styles.css`,
`web/src/components/Icon.tsx` and `web/src/lib/chart.ts`.

## The eight rules

1. **Every element answers a question.** Each chart, tile, chip, colour and line answers one
   question for one reader. If nobody can say it in one sentence, remove it or move it behind "Show more".
2. **Red means alert, nothing else.** Red (`C.alert`, `C.alertSoft`, `--alert`, `.pill-alert`, the
   `alert` icon) is only for: a flag that needs attention, crisis/self-harm sites, "present" in the
   gate, the C9 signal, and recording dictation. Intensity, likelihood ramps, periods, buttons, the
   assistant tab and the brand subtitle are neutral. Buttons and accents use ink (`--accent`).
3. **One neutral intensity scale.** `C.intensity` (8 steps, light warm grey to dark brown-grey,
   lightness only) for "more / less use": heatmaps, the 24-hour strip, the μ dots and the likelihood
   grid. Use `intensityColor(t)`. Cell text is white from `C.intensityWhiteFrom` on, ink before it.
4. **Only the baseline period is shaded, in a neutral colour.** Use `baselineMarkArea(days)`
   (`C.baselineShade`, labelled "Baseline (usual weeks)"). The recent / clinical period gets no
   shading and no coloured pill. The same applies to the phase strip, pills (`.pill-baseline`),
   phase tiles and the plan Gantt.
5. **Every axis names what and the unit.** Use `axisName(label, unit)`, e.g. "minutes in use per
   hour", "clock time", "hours", "count per day", "likelihood 0–1". Every band and line is in a
   visible legend. The **usual range** (the person's own, `usualBand`, filled) and the **typical
   range** (other people, P16–P84, `typicalBand`, dashed outline) always look different and always
   carry these names.
6. **Icons are eye-catchers with one fixed meaning each** (table below), always with a visible text
   label or a `label` (tooltip and accessible name). Clinicians scan icons first, then read.
7. **No unexplained tiles.** Every colour key has a legend, every tile has a tooltip with its value.
8. **Words.** "Typical" instead of "healthy people". No "sleep" where we only see quiet devices.

## Icons

`<Icon name="…" label="…" />`: inline SVG, 24 px line icons, drawn in `currentColor`.

| Name | Meaning |
|---|---|
| `moon` | Night / quiet window |
| `sunrise` | Back online in the morning |
| `clock` | Time in use |
| `night-use` | Use at night (moon with a dot) |
| `chat` | Chat |
| `globe` | Different sites |
| `alert` | Crisis / self-harm sites, needs attention (the only red icon) |
| `irregular` | Irregular nights (zig-zag) |
| `change` | Notable change, e.g. improvement (arrow, neutral `C.change`) |
| `note` | Note (pencil) |
| `explain` | Explain (question mark) |
| `away` | Away (suitcase) |
| `phone` | Phone |
| `laptop` | Laptop |
| `person` | Person |
| `data` | Data / about the data |
| `lock` | Private / protected |

## Colours (validated)

Checked with the dataviz palette validator on a white surface. The intensity ramp is one hue
(OKLCH h ≈ 62°), monotone, every step at least ΔL 0.06 apart, and its light end has 2.04:1
contrast. Steps 2 and up have at least 3:1 as marks. `alert` has 6.5:1 contrast. `change`
vs. `alert`: CVD ΔE 10.8, normal-vision ΔE 21.3. The device colours are unchanged from v2.
