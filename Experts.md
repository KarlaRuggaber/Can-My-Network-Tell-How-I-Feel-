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




# Experteninterview Stefan – CareNet

Oct 16, 2026 · @Thierry Suhner

## Summary

Stefan hält das Projekt für sinnvoll. Sein grösster Hebel liegt aber nicht bei den Profilen, sondern bei der Ergebnisdarstellung: Flags mit Unsicherheit statt Prozentwerten, ein individueller Baseline-Vergleich und Erklärungen in natürlicher Sprache für Kliniker. Nächster Schritt ist, erste synthetische Daten zu erzeugen und sie ihm für Feedback zu zeigen.

**Gespräch:** Experteninterview zum Bachelorprojekt CareNet ("Can My Network Tell How I Feel?"), ca. 42 Min. Teilnehmende: Thierry, Karla, Stefan (Experte).

### Kernaussagen von Stefan

- **Synthetische Daten sind theoriegeleitete Annahmen.** Sie können komplett falsch sein. Das muss im Report immer klar kommuniziert werden. Ein echtes Modell braucht später reale Patientendaten. Die Pipeline für den Datenfluss lässt sich wiederverwenden, ein auf Fake-Daten trainiertes Modell nicht.
- **Depression zeigt sich je nach Subgruppe unterschiedlich.** Z.B. gibt es starke Geschlechterunterschiede beim sozialen Rückzug, dazu passive statt aktive Nutzung. Ein Profil ist immer nur eine von vielen möglichen Ausprägungen.
- **Passende Feature-Ideen:** Uhrzeit (Aktivität um 3 Uhr nachts), Session-Länge (fragmentierter Schlaf, viele kurze Sessions), Abwesenheit von zu Hause über Geräte-Pings, Regelmässigkeit vs. Veränderung, aktiv vs. passiv, App-Kategorien (Kommunikation = soziale Interaktion, Fitness-Apps = Bewegung), WhatsApp-Calls, fremde Geräte im WLAN (Besuch = soziale Kontakte), Unterschiede zwischen Wochenende und Werktag.
- **Neuer Signalkandidat:** lange Gespräche mit Chatbots (ChatGPT, Replika). Das ist ein schwaches, aber möglicherweise relevantes Signal.
- **Methodik:** Statt handgebauter Features wären Sequenzmodelle denkbar. Interessanter ist ein neuer Ansatz: Ein lokales, datenschutzfreundliches LLM übersetzt Netzwerk-Logs in Verhaltensbeschreibungen. Kliniker validieren diese ("Stimmt das ungefähr?"), und per Prompt Engineering liegt der Fokus auf depressionsrelevanten Aspekten.
- **Ergebnisse als Flag, nicht als Diagnose.** Lebensereignisse (neuer Job, Party) erzeugen ähnliche Muster. Zeitfenster und Schwellen wie bei DSM-5 (≥ 2 Wochen, nicht zwingend jeden Tag) verwenden. Erst mehrere gleichzeitig auffällige Bereiche (Schlaf + Sozial + Bewegung) ergeben ein starkes Signal.
- **Individuelle Baseline:** Abweichungen vom persönlichen Mittelwert messen (Person-Mean-Centering, Anomalie-Erkennung) statt fixer Schwellen für alle.
- **Zwei Zielgruppen trennen:** Kliniker bekommen Details. Patient:innen bekommen eine vorsichtige Darstellung, damit kein Nocebo-Effekt entsteht.
- **Mehrwert im echten Einsatz:** Als Ergänzung zur klinischen Diagnostik (Fragebögen, Gespräch) ergibt das eine deutlich stärkere Befundlage.
- **EMA-Rückfragen** ("Was hast du gerade gemacht?") wären wertvoll für Labels, aber "ganz dünnes Eis": ethische Fragen, Dropout-Risiko und Reaktivität (Leute lernen, Trigger-Verhalten zu vermeiden).
- **Fallstrick Common Sense:** Annahmen wie "ist nachts wach" nicht vorschnell als Symptom interpretieren. Deshalb ist Experten-Input wichtig.

### Empfehlungen

1. Ergebnisdarstellung zur Priorität machen. Prozentwerte aus der Masterarbeit durch Flags mit sichtbarer Unsicherheit und Kontext ersetzen.
2. Ein lokales LLM als Erklärschicht prototypen (Log → Beschreibung in Klinikersprache). Die Nachvollziehbarkeit der bestehenden Pipeline ("keine Black Box") bleibt dabei erhalten.
3. Profile mit wenigen, gut sichtbaren Symptomen starten: Insomnie, Suizidrisiko (DNS-Aufrufe von Hilfeseiten, Vorschlag des Zürcher Experten), sozialer Rückzug. Chatbot-Nutzung und viele kurze Google-Suchen als Zusatzsignale prüfen.
4. Pro Profil eine Baseline-Woche (Werktag + Wochenende) modellieren, darauf ein Symptom über ≥ 2 Wochen legen. Ein Kontrollprofil mit gesundem Lebensereignis (neuer Job) testet False Positives.
5. Zwei Ansichten konzipieren: eine für Kliniker:innen, eine für Patient:innen.
6. Disclaimer zu fiktiven Daten und zur Symptom-Heterogenität fest in den Report einbauen. EMA vorerst nur als Ausblick mit ethischer Diskussion aufnehmen.

### Next Steps

- [ ] Synthetische Usage-Profile und Traffic für die ersten 2–3 Symptome scripten (Team)
- [ ] Stefan die ersten Daten bzw. Profile für Feedback schicken und prüfen, ob sie realistischer oder schärfer werden können (Team)
- [ ] Daten in Mapping und Pipeline der Masterarbeit integrieren (Team)
- [ ] Konzept für Flag-Darstellung und LLM-Erklärschicht skizzieren (Team)
- [ ] Stefan im Loop halten. Er ist interessiert und will ein Thema rund um lokale LLMs später besprechen (Team)

*Hinweis: Die Summary basiert auf einer automatischen Transkription mit eingeschränkter Qualität, Namen und Fachbegriffe sind teils rekonstruiert. Den Namen des Zürcher Experten (verstanden: "Lukas Schmiedelski", UZH) bitte prüfen.*

## Bereinigtes Transkript

Füllwörter, Wiederholungen und Satzabbrüche sind geglättet, der Inhalt bleibt erhalten. **Team** = Thierry bzw. Karla. Ihre Stimmen lassen sich in der automatischen Erkennung nicht zuverlässig trennen. \[unklar\] markiert Stellen, die akustisch nicht sicher verständlich waren.

### Teil 1: Projektvorstellung (00:00–04:35)

**Team (00:19):** Ganz kurz zum Abholen, was unser Projekt macht. Der Name sagt schon viel. Es geht darum, inwiefern wir aus Netzwerkdaten Informationen gewinnen können, die zu einer Einschätzung führen, wie wahrscheinlich bei einer Person ein depressives Symptom auftritt.

**Stefan (00:44):** Auftreten wird oder schon vorliegt?

**Team (00:47):** Aktuell vorliegt, also anhand des Verhaltens der letzten Zeit. Das Herzstück ist das Mapping von Netzwerkdaten auf Depressionskriterien. Das existiert bereits aus einer Masterarbeit. Unsere Aufgabe: Die Hardware-Komponente haben wir schon gebaut. Jetzt geht es um gescriptete Usage-Profiles. Das Modell wurde bisher nur auf ungeeigneten Datensätzen getestet, z.B. Smart-Home-Daten, die kein menschliches Verhalten mit Bezug zu Depressionskriterien abbilden. Wir wollen deshalb Profile imaginärer Personen erstellen: Wie würden sie das Netzwerk nutzen, wenn sie ein bestimmtes Kriterium erfüllen? Auf Basis dieser Profile scripten wir dann den Netzwerk-Traffic. Genau da hätten wir gern Domain-Expertise.

**Team (02:21):** Als Hintergrund: Wir haben noch einen weiteren Experten, Lukas \[Nachname unklar\] von der UZH, Psychiater \[unklar\]. Er hat enormes Wissen zu den Symptomen, kann sich aber weniger vorstellen, was Netzwerkdaten bedeuten. Wir hoffen, dass du diese Brücke etwas mehr bauen kannst.

**Stefan (02:55):** Wir können es probieren.

**Team (02:57):** Konzeptionell gehen wir vom Symptom aus, z.B. Insomnie. Wie würde sich so eine Person verhalten, und was würden wir davon im Netzwerk-Traffic sehen? Ein Disclaimer: Wir starten mit wenigen Profilen und wissen, dass sich Symptome auf viele Arten zeigen können. Es gibt depressive Personen, die nur noch Bücher lesen, und von denen sieht man im Netzwerk nichts. Wir wählen jeweils eine mögliche Ausprägung.

**Stefan (03:56):** Euch ist sicher klar, dass das eine Annahme sein wird. Es kann sein, dass es übereinstimmt, wenn man reale Daten hätte, es könnte aber auch komplett anders sein.

**Team (04:18):** Genau, das sind unsere Annahmen, vieles einfach Common Sense. Das Problem ist, dass wir nicht von Anfang an mit realen Patientendaten arbeiten können.

### Teil 2: Erste Einschätzung und Datenbasis (04:37–14:20)

**Team (04:37):** Erste offene Frage: Wie ist deine erste Reaktion, und wo siehst du Fallstricke?

**Stefan (05:03):** Meine initiale Reaktion ist erst einmal: Okay, aber wofür soll es sein? Was ihr versucht, ist quasi theoriegeleitet eine Heuristik oder ein Modell zu bauen. Eigentlich ist es ein Schritt davor: Ihr erzeugt Daten, die Verhaltensmuster depressiver Personen in einem bestimmten Ausprägungsgrad abbilden sollen. Ganz wichtig ist: Es kann sein, dass das komplett nicht stimmt. Wir haben Annahmen aus der Theorie und der Forschung. Es gibt aber Unterschiede nach Subgruppen, z.B. beim sozialen Rückzug starke Geschlechterunterschiede, und manche Betroffene sind eher passiv. Da müsst ihr überlegen, was ihr bei welcher Gruppe seht. Man würde z.B. auch sehen, wenn jemand seltener auf WhatsApp ist oder Kommunikationsmedien reduziert.

**Stefan (06:56):** Seht ihr den Inhalt des Netzwerk-Traffics?

**Team (07:02):** Nein, nur dass kommuniziert wird, nicht den Inhalt. Bei einer Website sehen wir den DNS-Namen, aber nicht den Inhalt. Wir sehen, wenn du Spotify oder Instagram öffnest, aber nicht, was du scrollst.

**Stefan (07:26):** Das ist schon mal gut. Ihr macht das so, weil ihr keinen Zugang zu Patient:innen habt?

**Team (07:45):** Genau, und weil wir die bestehende Masterarbeit mit dem Mapping integrieren wollen. Die wurde bisher nur auf Datensätzen getestet, die nicht für diesen Use Case gedacht waren. Um die Pipeline-Integration zu bauen und zu testen, brauchen wir irgendwelche Daten. Der letzte Schritt ist dann User Experience und Darstellung der Ergebnisse: Wie zeigen wir verständlich, wie man zu einem Resultat kommt? Und wie für verschiedene Zielgruppen? Einem Psychiater muss man zeigen können, wie das System zu einem Schluss kommt, und zwar so, dass er damit weiterarbeiten kann. Beim Patienten muss man aufpassen, dass False Positives nicht dazu führen, dass er glaubt, etwas zu haben, fast wie ein Placebo-Effekt. Das ist Teil 2.

**Stefan (09:16):** Euch ist bewusst, dass es besser wäre, ihr hättet Daten von Betroffenen. Wichtig ist, dass ihr das immer klar kommuniziert. Ein Modell müsste man eigentlich mit realen Daten bauen. Was ihr jetzt habt, ist komplett fiktional und kann im Gegenteil komplett nicht stimmen.

**Team (09:46):** Genau, im Moment geht es wirklich um die Pipeline-Integration. Wir kreieren künstliche Daten, integrieren die Pipeline, und im nächsten Schritt laufen reale Daten durch die bestehende Pipeline.

**Stefan (10:05):** Wenn die Pipeline ein Modell enthält, müsst ihr das dann ändern. Wenn sie nur Datenflüsse generiert, könnt ihr sie wahrscheinlich weiterverwenden.

**Team (10:19):** Das Mapping aus der Masterarbeit müsste man je nach Daten noch anpassen. Grundsätzlich geht es aber um den Datenfluss.

**Stefan (10:39):** Was seht ihr denn genau? Nur Pakete, die gesendet werden?

**Team (10:57):** Kurz zusammengefasst: Wir sehen, welches Gerät verwendet wird. Weil das System in einem Umfeld läuft, wo klar ist, wem welches Gerät gehört, wissen wir, welche Person gerade Pakete schickt. Wir sehen, wohin die Anfrage geht, also zu welcher Website oder welchem Endpunkt. Bei Apps ist es dasselbe: Es wird z.B. die Instagram-API aufgerufen. Bei Outlook sieht man den Mail-Refresh und welcher Account, z.B. Arbeits- oder Privat-Account. Sehr wichtig ist auch der Traffic an sich: Uhrzeit, Menge über die Zeit, ob er in Bursts kommt oder über lange Sessions. Daraus bauen wir Features.

**Stefan (12:10):** Bei Schlaf ist die Zeit sehr relevant: Ist jemand um drei Uhr morgens eingeloggt? Und die Session-Länge: Wenn jemand nachts wach ist und tagsüber müde und viele Powernaps macht, gibt es viele kurze Sessions statt langer. Auch ohne Inhalt kann man damit schon viel anfangen.

**Stefan (12:36):** Könnt ihr herausfinden, ob die Person die Wohnung verlässt? Das wäre ein starkes Signal.

**Team (12:46):** Nicht direkt. Beim Router, den wir aufgesetzt haben, verbindet man sich, und ab dann wird alles gemessen. In der Masterarbeit kann man aber Arbeitszeiten ausser Haus und Homeoffice angeben, das wird einbezogen. Die initiale Verbindung sehen wir. Wenn das Gerät weg ist, können wir das nach einer gewissen Zeit annehmen. Ein Handy pingt auch ohne Nutzung alle paar Minuten, wegen Hintergrund-Updates, WhatsApp-Benachrichtigungen usw. Wir können also mit einer Spanne von ein paar Minuten sagen, ob das Gerät da ist und wann es zurückkommt.

**Stefan (13:57):** Das ist gut. Dann schaut, was regelmässig ist und was sich verändert, und ab welchem Zeitraum ohne Signal man annehmen kann, dass die Person das Haus verlassen hat.

### Teil 3: Signale und Feature-Ideen (14:20–20:20)

**Stefan (14:20):** Ich denke laut weiter: Nachtaktivität ist interessant. Ihr müsst unterscheiden, ob jemand aktiv ist oder ob nur Hintergrund-Traffic läuft.

**Team (14:43):** Genau, dieses Background-Filtering machen wir. Wir unterscheiden aktiv und passiv.

**Stefan (15:02):** Super interessant ist, welche Apps generell genutzt werden. Kommunikations-Apps sagen etwas über soziale Interaktion aus. Wenn eine Fitness-App läuft, sagt das etwas über körperliche Aktivität aus.

**Team (15:24):** Das sehen wir. Es gibt aber zweigespaltene Apps: Bei Spotify sehen wir, dass du hörst, aber nicht, ob traurige Musik oder ein Podcast. Damit müssen wir arbeiten.

**Stefan (15:51):** Spannend wäre auch, wie oft andere Geräte ins WLAN kommen, die einer anderen Person gehören. Könnt ihr feststellen, dass es das Telefon einer anderen Person ist? Dann ist diese Person wahrscheinlich physisch in der Nähe, also Besuch in der Wohnung. Das könnte interessant sein.

**Team (16:32):** Gute Punkte. Das funktioniert auf jeden Fall.

**Stefan (16:48):** Sieht man Telefonate?

**Team (16:55):** Anrufe über WhatsApp kann man nachvollziehen, Anrufe über das Mobilnetz nicht. Ausser WLAN-Calling ist aktiviert.

**Team (17:17):** Kurz zu unserem Gedankenexperiment: Wir erstellen Basisprofile gesunder Personen und legen dann ein Symptom wie Insomnie darüber, um die Unterschiede zu sehen. Gedacht haben wir an einen 9-to-5-Worker und an einen Studenten, also wie deren Tagesablauf normalerweise aussieht. Dann kommen plötzlich nachts Peaks dazu.

**Stefan (17:53):** Nachts schaut man vielleicht auch Netflix, aber oft sieht man in der Nacht \[unklar\]. Interessant ist auch fehlende Aktivität: Die Leute schlafen länger oder sind zu bestimmten Zeiten inaktiv.

**Team (18:22):** Genau, z.B. am Nachmittag, wenn man eigentlich im Homeoffice wäre und gar nichts kommt.

**Stefan (18:32):** Generell ist es nicht trivial, das auszumachen. Ihr macht im Moment klassische Feature-Extraction. Wenn ich das neu aufbauen würde, würde ich es wahrscheinlich eher über Sequenzmodelle machen. Ein neuer Ansatz wird immer populärer: Man übersetzt die Logs in Sprache. Ein LLM, nicht in der Cloud, sondern privacy-sensitiv lokal, interpretiert, was passiert, und erstellt Beschreibungen. Die muss man natürlich validieren und Leuten vorlegen: Stimmt das ungefähr? Ein System, das kryptische Logs in Text übersetzt, z.B. "Patient war um diese Uhrzeit wach und in diesen Apps aktiv", könnte man per Prompt Engineering so ausrichten, dass die für euch besonders relevanten Aspekte vorkommen.

**Team (20:04):** Im Moment ist das System bewusst keine Black Box: Jeder Schritt ist nachvollziehbar gelöst. Das soll so bleiben, damit klar ist, wie eine Herleitung zustande kommt.

### Teil 4: Profile und Symptome (20:20–24:30)

**Stefan (20:20):** Man kann es auch symbolisch, also regelbasiert, machen, z.B. "vermehrte Nachtaktivität" oder "verlässt das Haus am Wochenende nicht". Bei Berufstätigen sieht man unter der Woche meistens die Arbeit, am Wochenende sieht man, wie sie ihre freie Zeit gestalten. Ich würde mich aber nicht auf die Kasuistik verlassen, sondern den Input von Kolleg:innen holen. \[unklar\] Man könnte die typische Symptomatik beschreiben, z.B. wie sich ein milder Depressionsverlauf zeigt und wie eine schwere Major Depression. Eine wichtige Frage ist auch: Was interessiert euch genau, die einzelnen Symptome oder eine Klassifizierung?

**Team (22:26):** Die Masterarbeit basiert auf den DSM-5-Kriterien, dazu gibt es eine ganze Liste mit Tabellen. Das Mapping deckt grundsätzlich alle Symptome ab. Für die Profile beginnen wir mit wenigen, um die Pipeline zu testen. In Zukunft könnte man Daten für alles einspeisen. Insomnie nehmen wir sicher, weil sie relativ gut sichtbar ist. Der Experte aus Zürich meinte, ein weiteres gutes Symptom wäre Suizidrisiko, z.B. über DNS bzw. Hostnames von Hilfeseiten, die sich häufen. Und vielleicht als drittes ein Symptom, bei dem die sozialen Interaktionen komplett wegbrechen. Also Symptome, die im Netzwerk relativ eindeutig sind.

**Stefan (23:45):** Gute Idee. Was vielleicht nicht so eindeutig ist, aber auch eine Rolle spielt: wenn man häufig Chatbots wie ChatGPT oder Replika nutzt und sehr lange Unterhaltungen führt. Das ist ein schwaches Signal, weil man mit denen über alles redet. Aber viele besprechen dort Probleme oder Suizidgedanken. Das könnte man auch einbauen.

**Team (24:16):** Daran haben wir auch gedacht, z.B. sehr viele kurze Google-Suchen, die auf Zweifel hindeuten könnten.

### Teil 5: Aktive Rückfragen und Ethik (24:30–28:30)

**Team (24:31):** Eine Frage, die mir gerade kommt: Unsere Idee ist ein passiver Ansatz. Als Patient hast du eigentlich nichts zu tun, ausser initial deine Routine anzugeben ("Ich arbeite hier, bin tagsüber weg"). Würde es Sinn machen, nach einem auffälligen Event eine Notification zu schicken, "Was hast du gerade gemacht?", um das besser zu klassifizieren? Würde man das in dieser Situation überhaupt ehrlich beantworten? Wahrscheinlich eher weniger.

**Stefan (25:29):** \[unklar\] Wissen die Leute denn, dass sie mitmachen?

**Team (25:37):** Ja. Die Idee ist auch, weg vom Begriff "Überwachung" zu kommen. Wir argumentieren damit, dass wir den Content nicht sehen. Der Use Case ist, dass man als ambulanter Patient mit dem Arzt vereinbart: Ich installiere das als zusätzliches Diagnose-Tool. Nicht, dass das jemand heimlich macht.

**Stefan (26:12):** Die Idee liegt nahe: Leute bei einem auffälligen Event fragen, was sie gerade machen. Ich glaube aber, das ist ganz dünnes Eis. Man bekommt damit wertvolle Daten, die man für die Labels braucht. Aber man muss sehr vorsichtig sein, auch wegen der ganzen Ethik dahinter und der Frage, in welchen Use Cases.

**Team (26:56):** Wir würden das für uns etwas abgrenzen: Wir implementieren es mal, und wie es eingesetzt wird, ist ein nächster Schritt. Wir bauen die Rakete, wir gehen nicht damit in den Krieg.

**Stefan (27:20):** Das Ethische ist das eine. Pragmatisch gedacht ist das Risiko bei Rückfragen, dass die Leute die Teilnahme abbrechen. Und es besteht die Gefahr, dass die Leute lernen, das Verhalten nicht mehr zu zeigen, um die Rückfragen zu vermeiden. Wenn ein Trigger mehrfach passiert, lernt die Person: Wenn ich das so mache, kommt die Frage nicht. Das ist dann nicht das Ziel.

### Teil 6: Ergebnisdarstellung, Unsicherheit und Baseline (28:30–38:00)

**Stefan (28:19):** Was habt ihr sonst noch, das ihr betrachten wollt?

**Team (28:32):** Es gibt zwei grosse Pakete: das Profil-Scripting und die Ergebnisdarstellung. Die sprachliche Erklärung von vorhin finden wir eine sehr coole Idee, um verständlich zu machen, was das System ausgibt. In der Masterarbeit hat man Kriterien und Symptome, und am Schluss gibt es einen Prozentwert, wie wahrscheinlich das Symptom zutrifft, auf einem Dashboard. Das ist nicht schön gelöst. Darauf wollen wir aufbauen. Das Modell ist momentan: Daten, darauf Features wie "Bursts in der Nacht", die linear auf den Wert für Insomnie bzw. dessen Likelihood einfliessen. Das wird zusammengerechnet, und am Schluss bekommst du einen Prozentsatz.

**Stefan (30:01):** Wichtig ist, dass man die Unsicherheit kommuniziert und eher ein Flag setzt, so wie "Hey, es könnte". Wenn man z.B. einen neuen Job hat und gestresst ist, zeigt man oft solche Verhaltensweisen, und das ist komplett normal und gesund.

**Team (30:28):** Genau darum geht es: die Unterscheidung, was ein Arzt bekommt und damit anfangen kann, und was wir dem User zeigen, um ihn nicht in eine falsche Richtung zu lenken und keinen Placebo-Effekt zu kreieren. Wenn ich dir sage "Du hast depressive Tendenzen", denkst du plötzlich, du hast sie, auch wenn es einfach Lebenssituationen sein können.

**Stefan (30:54):** Mir ist noch nicht klar: Sind die Leute, die das nutzen, neu, oder sind sie schon auffällig geworden?

**Team (31:08):** Das ist grundsätzlich nicht definiert. Die Idee ist, dass es mit entsprechender Konfiguration für verschiedene Zwecke genutzt werden kann. Wir sehen drei Use Cases: die klassische Arzt-Patienten-Beziehung bei ambulanter Behandlung als Ergänzung zur Diagnose. Eltern, die bei Teenagern merken, dass etwas nicht gut ist. Und Selbstinteresse, auch wenn es einem gut geht. Ein weiterer Gedanke: nicht konkret nach Symptomen suchen, sondern Abweichungen vom Durchschnitt erkennen. Das System läuft mit, nimmt dein Leben auf und sieht den Shift, wenn sich Schlafverhalten oder Soziales ändern.

**Stefan (32:28):** Das wäre dann eine Art Person-Mean-Centering: Du hast einen Mittelwert, der für die Person normal ist, und vergleichst damit. Dann sieht man Abweichungen oder Anomalien. Es kann natürlich sein, dass jemand an einem Fest war und spät ins Bett ging. Ihr wollt also wissen, ob es auch an normalen, typischen Tagen auftritt, z.B. an Werktagen.

**Team (33:09):** Im DSM-5 gibt es auch die Zwei-Wochen-Spanne. Mit einem Zeitfenster kann man überhaupt erst feststellen, ob etwas symptomrelevant ist oder eine Lebenssituation.

**Stefan (33:31):** Ist das eine Bachelorarbeit?

**Team (33:39):** Ein Bachelorprojekt, eine Vorstufe zur Bachelorarbeit an der HSG, ein \[unklar\] Projekt für BWLer bzw. Informatiker, 8 ECTS \[unklar\] zu zweit. Die Professoren schreiben Themen aus. Es geht weniger darum, eine Arbeit zu schreiben, als ein Produkt zu bauen und einen Report darüber zu machen.

**Stefan (34:12):** Dann könnt ihr gut argumentieren. Wenn ihr euch auf DSM-5 stützt und Zeitfenster und Schwellen festlegt, müsst ihr das wahrscheinlich etwas lockerer angehen. Es ist im Zweifel nicht jeden Tag. Wer schlaflos ist, ist am nächsten Tag müde und schläft vielleicht wieder mehr. \[unklar\] Ihr könnt ja nur die offensichtlichsten Muster abbilden.

**Team (35:25):** Genau, darum haben wir einen grossen Disclaimer: Das ist eine mögliche Form, wie sich ein Symptom zeigen kann. Die Fälle, in denen jemand nur noch Bücher liest und sich zurückzieht, nehmen wir nicht mit rein, weil wir sie nicht sehen.

**Stefan (35:45):** Es gibt ja auch Leute, die einfach kein Handy nutzen. Bei Depression gibt es meist ein deutliches Muster: sozialer Rückzug, wenig Schlaf, wenig Bewegung. Das verstärkt sich im System gegenseitig und führt zu dem, was wir Depression nennen, oder ist ein Ausdruck davon. Wenn das alles zusammen passiert, kann man auch ohne Prozent sagen: Hier besteht möglicherweise eine Depression.

**Team (36:15):** Da wird der Prozentsatz aus dem Mapping wieder sinnvoll. Man sieht nicht nur "hier ist ein Peak", sondern z.B. 30 % höher beim Schlaf, etwas höher beim Sozialen. Kombiniert sieht man: Vieles schlägt an, jetzt ist es vielleicht wirklich relevant.

**Stefan (36:38):** Gute Idee, ein Flag auf System-Ebene. Auch im DSM-5 heisst es: Fünf oder mehr der folgenden Symptome müssen über einen Zeitraum vorliegen.

**Team (37:02):** Wir müssen sehr vorsichtig sein, dass wir es als Flagging benennen und nicht als Diagnose.

**Stefan (37:14):** Ihr müsst immer ganz klar machen, dass es ein Flagging ist, das auf Verhaltensdaten zu Hause basiert, also auf dem digitalen Fussabdruck über den Router. Die Person kann es richtig schlecht gehen, und wenn sie kein Handy nutzt, seht ihr nichts. \[unklar\]

**Team (37:51):** Genau. Der reale Use Case wäre eine Unterstützung zu anderen Methoden, nicht das einzige Diagnosemittel.

**Stefan (38:06):** Das ist super. In der klinischen Diagnostik gibt es Fragebögen und Verfahren. Wenn man dazu noch Verhaltensdaten hat, ist das eine wesentlich stärkere diagnostische Befundlage, als wenn man nur auf Selbstauskunft angewiesen ist. Superprojekt.

### Teil 7: Takeaways und Abschluss (38:31–42:08)

**Team (38:31):** Wir müssen aufpassen, dass wir nicht in die Common-Sense-Falle tappen. Genau deshalb holen wir Experten. Für uns sagt Common Sense: Er ist nachts wach, also schläft er schlecht. Aber was bedeutet das genau?

**Team (38:55):** Mein erstes Takeaway: Vor allem bei der Ergebnisdarstellung können wir noch echt etwas bauen bzw. differenzieren, weil sie aktuell sehr schwach ist. Wie du angesprochen hast, kann man ein lokales LLM anhängen, das versucht, menschlich zu erklären und in Text zu fassen, was gesehen wird. Und das Flag so darstellen, dass man einerseits sieht, dass es erhöht ist, und andererseits, dass Unsicherheit mitspielt.

**Stefan (39:39):** Gut, guter Plan. Das mit den LLMs zum Erklären wäre wirklich eine super Idee. Das bricht auch diese Black-Box-Vorstellung auf, die Erklärbarkeit steckt dahinter. Und das ist am ehesten das, was Kliniker verstehen würden: in menschlicher Sprache, kurz, in der Art Sprache, die Kliniker erwarten würden, mit dem Kontext. \[unklar\]

**Team (41:02):** Unser nächster konkreter Schritt ist, einfach anzufangen und die Daten zu kreieren, auch wenn die erste Version noch nicht perfekt ist. Dann holen wir auf diesen Daten nochmals Feedback ein, um zu sehen, ob wir sie schärfen können. Danach folgt die Integration in das Mapping und die Pipeline.

**Stefan (41:27):** Mich interessiert \[unklar\] ein lokales LLM, das jemand gebaut hat. Das können wir später besprechen. Ich bin gern im Loop, ich bin erreichbar.

**Team (41:57):** Super, herzlichen Dank für deine Zeit. Wir melden uns.

**Stefan (42:03):** Alles gut, macht's gut. Ciao.
