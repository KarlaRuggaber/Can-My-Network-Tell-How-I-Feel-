# Project Process Log: Can My Network Tell How I Feel?

**Team:** Karla Ruggaber, Thierry Suhner
**Supervisor:** Dr. Bruno Rodrigues
**Period:** 14.09.2026 – 15.01.2027
**Weekly supervisor meeting:** every Friday

## Key Dates

| Date       | Milestone                  |
|------------|----------------------------|
| 07.10.2026 | Zwischenpräsentation       |
| 02.12.2026 | Abgabe des Videos          |
| 06.12.2026 | Abgabe Präsentationsfolien |
| 08.12.2026 | Abschlusspräsentation      |
| 15.01.2027 | Projektdokumentation       |

---

<details>
<summary><b>Week 1</b> (14.09 – 20.09)</summary>

**Kick-off meeting:** Mo 14.09
- **Done:** Introduction to the project, scope
- **Next / open:** Handover of hardware
- **Blockers / notes:**

**Hardware-Handover:** Di 15.09
- all of the hardware is stored at the CS-Building

</details>

<details>
<summary><b>Week 2</b> (21.09 – 27.09)</summary>

**Call with Lukasz (Psychology Expert):** Thu 24.09
- Lukasz will be kept in the loop
- He will give iterative feedback on profiles and our work in general

**Supervisor meeting:** Fri 25.09
- **Done:** recap on meeting with Lukasz
- **Next / open:** start on thinking about profiles
- **Blockers / notes:**

</details>

<details open>
<summary><b>Week 3</b> (28.09 – 04.10)</summary>

**Supervisor meeting:** Fri 02.10
- **Done:** discussed outline for presentation / hardware setup
- **Next / open:** set up hardware, make presentation
- **Blockers / notes:**

What we did today: we worked the entire day on the hardware setup. The entire process is documented in the file process/HardwareSetup.md.

</details>

<details>
<summary><b>Week 4</b> (05.10 – 11.10) 🎯 Wed 07.10: Zwischenpräsentation</summary>

**Supervisor meeting:** Fri 09.10
- **Done:**
- **Next / open:**
- **Blockers / notes:**

</details>

<details>
<summary><b>Week 5</b> (12.10 – 18.10)</summary>

**Supervisor meeting:** Fri 16.10
- **Done:**
- **Next / open:**
- **Blockers / notes:**

**Live ingest and app deployment:** Fri 16.10
- **Done:**
  - Live ingest service `tapingest`: every 60 s capture from tapcap is converted into the app's 5-min Parquet partitions within ~10 s, assigned per IP via `devices.csv` (one dataset = one person). Runs as a systemd service on the gateway.
  - Thesis app adapted: shared PCAP parser (upload and ingest give identical rows); pages 01/02 now pick up data that grows while the app runs.
  - Docker installed on the gateway with `"iptables": false` (firewall verified unchanged). The app runs in a container on localhost only, reachable via SSH tunnel.
  - Approach for traffic generation decided: one scheduler (profile + seed → ground-truth plan), executed live by runner containers on a separate `br-sim` network, later synthetically by stitching recorded activity snippets into PCAPs.
  - Runner container (Karla) and scheduler started as parallel work items.
- **Next / open:**
  - Background filter in the ingest (MasterThesisInc §3) before interpreting sleep/idle metrics
  - Connect `br-sim` (second capture folder, shared `devices.csv`), first end-to-end pilot with one container
  - Own fork of the app repo; remove temporary sudo rule and deploy key on the gateway
  - Validation on real data (MasterThesisInc §8, steps 3–6)
- **Blockers / notes:** App repo `origin` is Stephan Nef's repo, so our code changes (branch `live-ingest`) are only local until we have a fork. Full documentation: [Deployment.md](Deployment.md).

</details>

<details>
<summary><b>Week 6</b> (19.10 – 25.10)</summary>

**Supervisor meeting:** Fri 23.10
- **Done:**
- **Next / open:**
- **Blockers / notes:**

</details>

<details>
<summary><b>Week 7</b> (26.10 – 01.11)</summary>

**Supervisor meeting:** Fri 30.10
- **Done:**
- **Next / open:**
- **Blockers / notes:**

</details>

<details>
<summary><b>Week 8</b> (02.11 – 08.11)</summary>

**Supervisor meeting:** Fri 06.11
- **Done:**
- **Next / open:**
- **Blockers / notes:**

</details>

<details>
<summary><b>Week 9</b> (09.11 – 15.11)</summary>

**Supervisor meeting:** Fri 13.11
- **Done:**
- **Next / open:**
- **Blockers / notes:**

</details>

<details>
<summary><b>Week 10</b> (16.11 – 22.11)</summary>

**Supervisor meeting:** Fri 20.11
- **Done:**
- **Next / open:**
- **Blockers / notes:**

</details>

<details>
<summary><b>Week 11</b> (23.11 – 29.11)</summary>

**Supervisor meeting:** Fri 27.11
- **Done:**
- **Next / open:**
- **Blockers / notes:**

</details>

<details>
<summary><b>Week 12</b> (30.11 – 06.12) 🎯 Wed 02.12: Abgabe des Videos · 🎯 Sun 06.12: Abgabe Präsentationsfolien</summary>

**Supervisor meeting:** Fri 04.12
- **Done:**
- **Next / open:**
- **Blockers / notes:**

</details>

<details>
<summary><b>Week 13</b> (07.12 – 13.12) 🎯 Tue 08.12: Abschlusspräsentation</summary>

**Supervisor meeting:** Fri 11.12
- **Done:**
- **Next / open:**
- **Blockers / notes:**

</details>

<details>
<summary><b>Week 14</b> (14.12 – 20.12)</summary>

**Supervisor meeting:** Fri 18.12
- **Done:**
- **Next / open:**
- **Blockers / notes:**

</details>

<details>
<summary><b>Week 15</b> (21.12 – 27.12)</summary>

**Supervisor meeting:** Fri 25.12 (likely skipped: Christmas)
- **Done:**
- **Next / open:**
- **Blockers / notes:**

</details>

<details>
<summary><b>Week 16</b> (28.12 – 03.01)</summary>

**Supervisor meeting:** Fri 01.01 (likely skipped: New Year)
- **Done:**
- **Next / open:**
- **Blockers / notes:**

</details>

<details>
<summary><b>Week 17</b> (04.01 – 10.01)</summary>

**Supervisor meeting:** Fri 08.01
- **Done:**
- **Next / open:**
- **Blockers / notes:**

</details>

<details>
<summary><b>Week 18</b> (11.01 – 17.01) 🎯 Fri 15.01: Projektdokumentation</summary>

**Supervisor meeting:** Fri 15.01
- **Done:**
- **Next / open:**
- **Blockers / notes:**

</details>