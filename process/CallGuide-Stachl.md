# Call Guide: Clemens Stachl

**Date:** 14.10.2026 · **Duration:** 60 min · **Attendees:** Karla Ruggaber, Thierry Suhner, Prof. Clemens Stachl

**Why him:** Lukasz covered the clinical side (DSM criteria, symptom focus, validation plan; see [Experts.md](../Experts.md)). Stachl's expertise is mobile sensing, measurement validity, ML vs. interpretable models, and the ethics of behavioural data. Use the hour for those topics, not for clinical criteria.

**Relevant work of his:**
- Stachl et al. (2020), *PNAS*: personality from smartphone behaviour (app use, communication, music, day–night activity, mobility)
- Stachl et al. (2020), *Eur. J. Personality*: personality research and assessment in the era of ML
- Harari et al. (2019), *JPSP*: *Sensing Sociability* (calls, texts, app use)
- Ilievski et al. (2025), *Nature MI*: aligning generalization between humans and machines

---

## 0. Before the call

- [ ] Have a one-pager ready to screen-share: network → behaviour → DSM chain, tier structure, one example profile ([mdd-severe-suicidality](../profiles/tier2-clinical/mdd-severe-suicidality.md)), and the expected-output table from [thesis-alignment.md](../profiles/thesis-alignment.md) §5
- [ ] Have these open: [ProfileStructure.md](../profiles/ProfileStructure.md), [symptom-network-mapping.md](../profiles/symptom-network-mapping.md), [activity-catalog.md](../profiles/activity-catalog.md), [HardwareSetup.md](HardwareSetup.md)
- [ ] Ask at the start if we may record the call / take detailed notes

## Agenda

| Min | Block |
|---|---|
| 0–8 | Intro and project pitch |
| 8–20 | 1. Profiles and validity |
| 20–30 | 2. Script and evaluation design |
| 30–40 | 3. Network traffic vs. smartphone sensing |
| 40–55 | 4. Explainability, usability and UX · 5. Ethics |
| 55–60 | 6. Wrap-up and next steps |

⭐ = must-ask. If time runs short, ask only the ⭐ questions.

---

## Intro and pitch (0–8 min)

Five minutes max, then hand over with the first question.

1. **The project:** can home-router metadata (DNS, TLS/QUIC SNI, flow timing and volume) indicate DSM-5 depressive behaviour in an explainable way? We build on CareNet (Nef & Rodrigues 2025) and its rule-based pipeline (`app_pcap_to_dsm5`).
2. **Done so far:**
   - A reboot-proof capture gateway: a mini-PC as the router, with full pcaps and a unified DNS/SNI feed, attributed per device by MAC.
   - A profile framework: Tier 0 healthy through Tier 4 edge cases, deviation from the personal baseline, spread × depth.
   - Five profiles drafted: student, 9-to-5 worker, insomnia, social anxiety, severe MDD with a suicidality overlay.
   - Each profile is executable as a YAML script of activities with an expected thesis output per criterion.
3. **Next:** an automatic ingest into the thesis pipeline, a pilot run, then 14 days of baseline plus 14 days of profile per instance.
4. **What we want from him:** his view on validity, evaluation design, explainability and UX.

---

## 1. Profiles and validity (8–20 min)

Context: the profiles are derived top-down from theory. The effect sizes are our own estimates, e.g. MDD: sessions −30 to −40 %, unique SLDs −40 to −50 %, social −50 to −70 %.

- ⭐ **Effect sizes.** Our deviation sizes are educated guesses. In the mobile sensing literature, depression–behaviour links are usually small and heterogeneous. Are our profiles caricatures? How would he ground the sizes in empirical data?
- **Within-person baseline.** Is 14 days enough to estimate someone's normal variability? Our student baseline already varies ±45–60 min per day. How should we set a threshold that is meaningful within one person?
- **Categorical or dimensional.** We use discrete tiers plus severity per symptom. Would he model symptoms as continuous dimensions instead, the way personality is modelled?
- **Blind spots as a finding.** Even a 9-of-9 severe MDD profile reaches only 4–5 criteria from network data (C3, C5 and C7 are not observable; C9 is episodic). Is that a legitimate result to report, and how should we frame it?

**Notes:**

-

---

## 2. Script and evaluation design (20–30 min)

Context: Playwright scripts run on a real phone and laptop through the gateway. Every activity goes to a ground-truth log. One instance takes 28 days in real time.

- ⭐ **Circularity.** We script behaviour from the same mapping the pipeline encodes. If the pipeline recovers it, we have verified the implementation, not shown the construct is valid. Does he agree? How should we frame this honestly?
- **Sample size.** We will only have about 1–2 instances per profile. What can we credibly claim? How many seeded instances would he want?
- **What counts as "recovered"?** Should we evaluate at criterion level (present or absent), at metric level (direction of change vs. baseline), or as a full trace from packet to likelihood?
- **Calibration.** We plan to re-tune the thesis bands on Tier 0 runs only and test on the clinical runs, then report the original and the recalibrated config side by side. Is that clean enough?
- **Ecological validity.** Scripted sessions are not human behaviour (gaming in particular is only approximated). Which threats to validity must we name?

**Notes:**

-

---

## 3. Network traffic vs. smartphone sensing (30–40 min)

- ⭐ **Recoverable features.** Which of the feature families from his PNAS study (communication, app use, music, day–night activity, mobility) can a router recover, and which are lost? Mobility, screen state and call logs are invisible to us.
- **Missing data.** We see household-level traffic on one network only. Mobile data and time away from home are gaps. How do sensing studies handle coverage gaps in deviation-based models?
- **Sociability.** We separate social anxiety from depressive withdrawal by upstream share and by synchronous vs. asynchronous use. *Sensing Sociability* looked at calls vs. texts. Is that distinction robust?
- **Erosion over time.** Encrypted DNS (DoH), Encrypted Client Hello, iCloud Private Relay and rotating MACs reduce what a router can see. Is router-based sensing a long-term dead end, or a useful complement to phones and wearables?

**Notes:**

-

---

## 4. Explainability, usability and UX (40–50 min)

Context: the pipeline uses fuzzy membership functions, then a weighted likelihood per criterion, then a gate (L ≥ 0.6 on ≥ 6 of 14 days). The bands were tuned by hand on a dataset that is not a real person.

- ⭐ **Rules or ML.** Should we stay rule-based (as Rudin argues), learn the weights, or use an interpretable model (e.g. a GAM or a sparse model)? Is a transparent but arbitrary rule really more explainable than a well-validated model?
- ⭐ **What clinicians need.** What is the minimum explanation? The full trace from packet to metric to criterion, or a plain summary like "night activity 3× above your baseline on 9 of 14 days"?
- **Who the user is.** Clinician, patient, or both? Should the patient see the same view as the clinician?
- **Not a diagnosis.** How should the output be designed so nobody reads it as a diagnosis? Has his group studied how people react to algorithmic feedback about themselves?
- **Evaluating UX without clinicians.** How could we test usability and explainability in a bachelor project? Options: think-aloud sessions, a vignette study, a few clinicians via Lukasz.
- **Clinician-steered monitoring.** Lukasz suggested the doctor could tell the system which profile to look for. Does that help usability, or does it bias the results?

**Notes:**

-

---

## 5. Ethics and privacy (50–55 min)

- ⭐ **Bystanders.** The router sees flatmates and family members who never consented. How does he handle consent for third parties in sensing research?
- **Suicidality flag.** We can detect domain hits on 143.ch and 147.ch. Who would be alerted, and how fast? What duty of care comes with a flag that nobody acts on in real time?
- **Retention.** At the moment we delete nothing. What retention and pseudonymisation would he expect before a field study?
- **Dual use.** The same box could profile people without their consent. Should our report address this?

**Notes:**

-

---

## 6. Wrap-up and next steps (55–60 min)

- Does he know of datasets combining passive sensing with PHQ-9 or EMA, or of IBT studies we could use for realistic effect sizes?
- Which 2–3 papers should we read or cite?
- Would he be interested in staying involved, or in a future field study? Lukasz mentioned a possible joint funding application.
- May we send him follow-up questions or a draft later?

**Notes:**

-

---

## After the call

- [ ] Clean up the notes and add a summary under a new heading in [Experts.md](../Experts.md)
- [ ] Log the call in [process.md](process.md) (current week)
- [ ] List concrete changes to the profiles, evaluation plan and UX plan, then raise them with Bruno on Friday
- [ ] Send a thank-you email with any promised material

| Action item | Due |
|---|---|
| | |
| | |
