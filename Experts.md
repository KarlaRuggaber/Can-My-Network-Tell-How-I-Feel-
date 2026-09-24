# Lukasz Smigielski (lukasz.smigielski@kjpd.uzh.ch)

### Call 24/09/26


**1. Expert background and existing work**

Lucas is a psychiatry researcher who has been exploring digital monitoring of psychiatric patients for approximately two years, specifically through smartphone-based applications. He frames this space in two domains:

- **Active monitoring** (ecological momentary assessment / EMA): patients actively input data at multiple points during the day. He highlighted this as valuable because psychiatric symptoms fluctuate throughout the day — morning to evening — making repeated sampling far more informative than a single clinical interview. A 3–4pm appointment with a clinician captures an extremely narrow window of a patient's state.
- **Passive / ambient sensing**: monitoring patient parameters in real life without any active input from the patient. He described this as "even more interesting" because it removes burden from the patient, though he acknowledged it sits in a sensitive privacy domain that requires regulation.

He is also part of a Denmark-based project called **"Personas AI"** which involves PhD students from Copenhagen (mathematics faculty) and has a psychiatry component — notably, it is also called "personas," which he found a striking overlap with this project's framing.

---

**2. Validation of the overall approach**

Lucas was broadly enthusiastic and validated several core assumptions:

- The idea of connecting a monitoring device to a patient's router and extracting network traffic features is technically and conceptually sound to him
- The **symptom → behaviour → observable network feature** mapping chain Karla described ("disturbed sleep → phone use at night → DNS queries at 2am") was explicitly endorsed as the right direction
- Using **DSM-5 and ICD-10** as the diagnostic anchor is appropriate and he found it "fantastic" that the project tries to map back to existing diagnostic systems rather than inventing new ones
- The **deviation-from-baseline** model — detecting changes from a person's own normal pattern rather than comparing against population averages — was something he strongly agreed with. He gave an example: someone using social media frequently is not inherently a signal; it's the deviation from their personal norm that matters
- He agreed the system should **never state that a person is depressed** — it should only flag a deviation in behaviour and recommend the person see a doctor

---

**3. Clinical context: patient types**

Lucas described the patient landscape relevant to this technology:

- **Stationary patients** (inpatient / hospitalised)
- **Semi-stationary patients**
- **Ambulatory patients** — the largest group; people coming in regularly for medication or clinical check-ins

He suggested ambulatory patients would be the most relevant target group for this kind of home-based monitoring technology, and that it would need to sit within a **formally arranged clinical research framework** with ethics approval and patient informed consent.

---

**4. The heterogeneity problem**

He flagged this as a fundamental challenge for the project. There is no single "depression profile" — depression always presents as a combination of symptoms with varying:
- **Spread** (which symptoms are present)
- **Depth** (severity of each symptom)
- **Comorbidities** — the most common being depression + anxiety and depression + insomnia

He also noted that diagnostic systems themselves evolve (DSM-5, ICD-10, now ICD-11), adding another layer of complexity. This heterogeneity makes it very difficult to state definitively that a certain network pattern indicates depression, which reinforces the need for the deviation model and clinical validation.

---

**5. Recommended symptom focus areas**

Lucas suggested narrowing the initial profile work to symptoms that are most visible from a network / behavioural perspective. His specific recommendations:

**Insomnia / sleep disturbance**
He called sleep patterns "so interesting" for depression specifically. He highlighted that a very characteristic symptom of depression is **early morning waking** — around 4–5am — not just general sleep disruption. This specific window is diagnostically meaningful and potentially observable through DNS activity during those hours.

**Suicidality**
He was particularly animated about this. Key points:
- Most suicidal intent goes **uncommunicated**, especially in adolescents — he referenced data from a project on Swiss adolescents showing how often this is not expressed verbally
- He is separately involved in a project using **audio-visual interview data** to predict suicide risk
- He believes there are behavioural signs that can be detected from unmonitored behaviour — website visits, domain access patterns — even when the person does not communicate intent
- On the technical question of whether search terms can be captured: he acknowledged that search query content is encrypted, but pointed out that **DNS queries reveal which websites a person clicks through to** from search results, which can carry semantic signal even without seeing the query text itself
- He asked for suicidality to be explicitly included as a profile

**Anxiety**
He identified this as another strong cluster, distinguishing:
- Generalised anxiety disorder
- Social anxiety
- Anxiety as a comorbidity with depression (very frequent combination)

**Rumination**
He described rumination as "very characteristic" — the tendency to repetitively revisit certain thoughts or emotions. He suggested this might translate into observable network behaviour such as repeatedly returning to the same domains or content clusters.

**High-functioning depression**
He raised this as a harder sub-profile where people can mask their symptoms externally. He was uncertain whether network data would capture this well, noting that someone who is mentally struggling but maintaining normal outward behaviour may not show clear network deviations.

---

**6. Profile and persona design**

He endorsed the three-tier structure (healthy baseline / grey zone / clear depression signals) and suggested going further by creating **sub-profiles based on symptom combinations**, for example:
- Depression + insomnia
- Depression + social anxiety
- Depression + generalised anxiety
- Mild vs. severe depression (noting that mild and severe would likely produce different behavioural signatures)

He drew a parallel to his Denmark "Personas AI" project where similar persona-based profiling is used in a psychiatric context.

He also raised an interesting idea: if a doctor is already observing a patient and knows their rough profile type (e.g. high-functioning, or anxiety-dominant), the doctor could potentially **instruct the monitoring system** to look for specific patterns relevant to that patient type, rather than searching for all patterns generically. He acknowledged this is a step further but found it conceptually interesting.

---

**7. Validation methodology**

Lucas was clear that the synthetic profile phase is the correct starting point but is only a stepping stone. His vision for the full validation pipeline:

1. Define profiles based on diagnostic criteria (current phase)
2. Build and test the system on synthetic / simulated data
3. Move to real-world data with a formal clinical study:
   - Ethics approval required (he was explicit this is non-negotiable)
   - Patients must have a confirmed diagnosis of **major depressive disorder** as an inclusion criterion
   - **Informed consent** required from all participants
   - Technology deployed in patients' homes
   - Network data collected and mapped to diagnostic profiles
   - **Cross-validation**: training group to establish profiles, testing group to validate predictions

He also mentioned the possibility of going further — using the system to predict **which patients respond to which therapy**, which he called "super interesting" given how much time is lost on ineffective interventions in depression treatment.

He cautioned against relying on existing large data banks, noting these are unlikely to contain the right kind of data for this specific use case — a point reinforced by the team's own previous experience with a smart home dataset that was not designed for this purpose and proved insufficient for validation.

---

**8. The 2-week diagnostic window**

Karla asked explicitly how fixed the 2-week period is (as required by ICD-10 / DSM-5). Lucas's answer: it is a **consensus definition** that makes sense for comparability and practicability, but it should not be treated as a hard cutoff — "15 days versus 14 days doesn't make a meaningful difference." He recommended using 2 weeks as the reference period for alignment with established diagnostic standards. He noted that for synthetic data this timeline can be freely compressed; for real-world measurement it cannot.

---

**9. What cannot be observed from network data**

An important caveat Lucas raised: not all depression symptoms will be visible from network traffic. He gave the example of someone who is depressed but responds by reading books — generating no network activity at all. The system will have **blind spots**, and the project should be honest about which symptoms are observable and which are not. This reinforces the earlier distinction between "high DNS signal" symptoms (sleep, suicidality, social withdrawal) and "low DNS signal" symptoms (guilt, self-confidence, psychomotor changes).

---

**10. Next steps agreed**

- Team to develop concrete profile definitions and send to Lucas for clinical review
- Iterative feedback loop with Lucas as the clinical validator
- Follow-up meeting after profiles are drafted (Lucas has a conference in October, otherwise generally available)
- Longer-term: potential joint funding application for a formal clinical study