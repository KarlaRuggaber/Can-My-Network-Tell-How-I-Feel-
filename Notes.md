## Website Links
DSM-5: 
- https://www.mdcalc.com/calc/10195/dsm-5-criteria-major-depressive-disorder

ICD-10: 
- https://icd.who.int/browse10/2019/en#/F32
- https://gpnotebook.com/pages/psychiatry/icd-10-depression-diagnostic-criteria

ICD-11:
- https://icd.who.int/browse/2026-01/mms/en#323148092
- https://neurotorium.org/slidedeck/major-depressive-disorder-definitions-and-diagnosis/slide/32-icd-11-classification-of-depression/


11 | Bruno Rodrigues | Can My Network Tell How I Feel?
Summary
Your router sees the traffic of every device in your home. Most of this content is encrypted by default as todays standards, but when you talk, how much, how often, and roughly to whom is still possible to be observed. These are the metadata that your traffic exposes and you might have already seen them (I hope you have used Wireshark at some point). The patterns leaked by metadata can potentially give insights for clinical doctors to diagnose depression, which can be obtained from the router alone, with no app and no wearable. For example, whether you are awake at 3am, how varied your activity is, how stable your routine looks.

However, clinicians cannot act on a calculated number/indicator that arrives without a reason. If the system reports signs of disturbed sleep, the chain of events that triggered this indicator has to be clear and explainable. Our current approach follows this principle relying on explicit rules and weights rathern than a black-box model. But, as of today, it has only run offline on stored captures, so neither the local deployment nor the explanation chain has been demonstrated on live traffic in a real house.

In this project students will improve the existing approach in terms of explainability and usability (how can a clinician understand network metrics), and mirror household traffic to a analysis box (e.g., Raspberry Pi or Mini-pc) making the system practical. Students will also define a routine and generate specific traffic patterns that would trigger an intended indicator, and observe how this traffic activates the pipeline in an explainable way.  The only behaviour recorded is the one you scripted, so there are no patients and no personal data. No networking background is required, and the hardware is provided. The specific goal of this project is to turn the analysis into a local, explainable appliance running on real traffic, and to show that its reasoning can be followed end to end by a clinician, so that a future field study with real patients becomes possible.

Project topics
Network traffic analysis.
Explainable AI

Privacy by Design

Applied ML
Objectives
Understand how router metadata becomes a behavioural indicator and how explicit rules turn those features into a clinical criterion likelihood.

Deploy the pipeline on the mini-PC and mirror traffic to it from the MikroTik router, so that no data leaves the household.

Script daily routines that vary wake time, nocturnal activity, activity diversity, and routine stability, and record real traffic for each.

Test whether the pipeline recovers the scripted routine from live traffic, and trace every reported likelihood back to the packets that produced it.

Literature list
Nef, S., & Rodrigues, B. (2025). CareNet: Linking Home-router Network Traffic to DSM-5 Depressive Behavior Indicators. arXiv:2511.12772. Published at IEEE/IFIP NOMS 2026.

Nef, S. (2025). At the Edge of Empathy: Mental-Health Awareness Through Home-Router Network Traffic Insights. Master's thesis, University of St.Gallen. https://sensing-group.com/files/theses/ma-stephan-nef.pdfLinks to an external site.

Haller, T. (2026). Explainable Multimodal-based Depression Awareness at the Edge. Master's thesis, University of St.Gallen. https://sensing-group.com/files/theses/ma-tibor-haller.pdfLinks to an external site.

Rudin, C. (2019). Stop explaining black box machine learning models for high stakes decisions and use interpretable models instead. Nature machine intelligence, 1(5), 206-215.
American Psychiatric Association (2013). Diagnostic and Statistical Manual of Mental Disorders (5th ed.). DSM-5.