# Using the Master Thesis Model (app_pcap_to_dsm5) with Our Gateway Data

## 1. How well our captures fit the model

The thesis prototype expects PCAP files. It turns them into 5‑minute Parquet partitions, builds one feature record per day, and then computes the FASL likelihoods and the DSM‑5 gate. Our `tapcap` output is a standard rotating PCAP, so the format already fits. Several details still need attention:

| Aspect | Thesis app expects | What our gateway delivers | Consequence |
| --- | --- | --- | --- |
| Input | PCAP/PCAPNG, uploaded by hand in the Streamlit UI (max ~1 GB per file) | 60 s / 512 MB rotating pcaps in `/var/lib/tapcap/ready/` | Thousands of small files. We need a batch or automatic ingest instead of manual upload |
| Vantage point | "Home router", but the evaluation used public datasets (Dataset A/B) | Real gateway on `eno1`, **before NAT** | ✅ Better than the thesis data: we see real client IPs |
| Direction (up/down) | `is_private_ip()`: private→public = upstream | Clients are in `10.42.0.0/24` (private) | ✅ Inbound and outbound detection work directly |
| Domain enrichment | Only plain DNS answers (`DNS_ANS_NAME` → IP map) | dnsmasq is every client's resolver, so DNS appears on `eno1`. We also have SNI/QUIC SNI in `feed.ndjson` | ✅ Works. SNI from our feed can fill gaps (DoH, cached lookups) |
| IP version | Parses IPv4 only (`IP in pkt`) | Gateway runs IPv4 only (no DHCPv6/RA) | ✅ Fine |
| Timestamps | `datetime.fromtimestamp()`, i.e. the **local time of the machine that runs the app** | pcap timestamps are UTC epoch | ⚠️ Run the ingest with `TZ=Europe/Zurich`, or night/day metrics shift by 1–2 h |
| Person attribution | **Not implemented.** All traffic in a dataset counts as one "person". Profiles/IP mapping exist in the UI but do not feed the calculations | We know the MAC, IP, DHCP hostname and SNI per client | ⚠️ We have to split per device ourselves (see 2.3). This is the most important step |
| Background traffic | Assumes household traffic only | Our capture also contains AP↔controller (8080, 10001, 3478), DHCP, mDNS, NTP and SSH | ⚠️ Must be filtered, or sleep and idle metrics never see "silence" (the same failure the thesis saw with Dataset B, C4_F2) |
| Retention | Thesis: short retention, rotate raw PCAPs | We delete nothing (by request) | ⚠️ Fine for a study, but it contradicts the thesis privacy design. Document it |

## 2. How to analyse our data now

### 2.1 Quick check: manual upload (small test)
1. Copy a few pcaps from the server to the laptop: `sudo bash -c 'tar czf /tmp/sample.tgz /var/lib/tapcap/ready/*.pcap'`, then `scp`.
2. Merge them into one file: `mergecap -w day1.pcap *.pcap`. The file must stay under 1 GB.
3. Start the app: `cd app && streamlit run 00_Home.py`. Go to **User & Network Settings** and upload `day1.pcap`.
4. Open **Network Metrics** and **Early Signs Overview**, select the dataset (it falls under the "Other" type) and press *Refresh cached day metrics*.

This only proves the pipeline runs. The results are meaningless until filtering and per‑device splitting are in place.

### 2.2 Proper way: batch ingest script (recommended)
`partition_pcap_to_parquet()` and `parse_packet_row()` live inside a Streamlit page that runs `login(); st.stop()` on import. Steps:

1. **Move the ETL into a plain module**, e.g. `app/utils/etl.py` (containing `parse_packet_row`, `partition_pcap_to_parquet`, `floor_to_interval`, `_commit_partition`). The page then imports from there, so the UI keeps working.
2. Write `scripts/ingest_gateway.py`. It reads `ready/*.pcap`, filters, splits per device and writes into `app/processed_parquet/<dataset>/`. It also keeps a "done" list so each pcap is processed only once.
3. Later, run it as a systemd timer or file watcher on the server. This is the "file‑watcher" next step from HardwareSetup.md.

Performance: scapy is slow, roughly 10–50k packets/s. For days of traffic, pre‑filter with `tshark`, or build the Parquet rows directly with `tshark -T fields` (frame.time_epoch, ip.src, ip.dst, ports, frame.len, dns.qry.name, dns.a, eth.src). The **schema must match** what the app reads:
`Timestamp, Date, Hour, Protocol, Source IP, Destination IP, Source Port, Destination Port, TCP Flags, Length, IsDNS, DNS_QNAME, DNS_QTYPE, DNS_ANS_NAME, DNS_ANS_IPS`

### 2.3 Filter and split per device (this replaces the missing identity resolution)
- **Drop** packets where:
  - either side is the AP's IP, or the port is 8080, 8443, 10001, 3478 or 11443 (UniFi)
  - the port is 67/68 (DHCP), 5353 (mDNS), 123 (NTP) or 22 (SSH)
  - the traffic is not to/from a client (e.g. the server's own traffic)
- **Keep DNS to 10.42.0.1.** The enrichment needs it.
- **Split by client MAC** (`eth.src` / `eth.dst`), not by IP, because DHCP IPs can change. Write one dataset per device, e.g. `gw_<mac-or-alias>`, using the MAC→friendly‑name mapping file proposed in HardwareSetup §11.
  - The app only filters by dataset name, so one dataset per device gives per‑person attribution with no app change.
  - Note: iOS "Private Wi‑Fi Address" can rotate the MAC. Fix it per test network ("Fixed" mode) or re‑check the mapping each session.
- Optional: add `eth.src` as an extra column `MAC`. Extra columns are ignored by the app but useful later.

### 2.4 Calibrate before you interpret
- The `fasl_config.json` parameters (lo/mid/hi, weights, θ=0.6, M=14, N=6) were tuned by hand on **Dataset B**, which is not a real person. Re‑tune on our own baseline days, with the distribution and over‑time views per metric (thesis §6.2.5).
- The DSM gate needs **≥14 days** of data per device before "criterion present" means anything. Plan the capture duration with this in mind.
- Expect phone background traffic at night (APNs push 5223, iCloud keep‑alives). Check C4 (sleep) metrics for the same "never silent" artifact as Dataset B. If needed, add an exclusion list for known keep‑alive SNI/ports.
- The hotspot uplink caps bandwidth. Byte‑based metrics (down/up ratio, streaming flows ≥2 h) may behave differently than on a normal home line.

## 3. What we can take from the thesis for our extension

The thesis names its own gaps (Ch. 6.5 Limitations, Ch. 7.2 Future Work). Our hardware setup directly addresses several of them:

| Thesis gap / future work | What we already have | Possible extension |
| --- | --- | --- |
| **Real, in‑situ data** (§6.1.1: the author tried a Raspberry Pi and gave up; §7.2.1 field study) | Reboot‑proof gateway that captures real clients continuously | Our main contribution: the first real‑world data source for the model. With consent, add PHQ‑9 per participant as ground truth |
| **Identity resolution not implemented** (§4.4.1, §6.5.2, §7.2.4) | MAC per packet, DHCP hostnames, mDNS, SNI per client in `feed.ndjson` | Device→person mapping (MAC + alias file). Wire `user_profiles.json` into the calculations instead of display only |
| **DNS‑only enrichment, weak against DoH/encryption** (§4.3.4) | TLS SNI + QUIC SNI per client | Use the SNI feed as a second source for `ResolvedHost`/`SLD`. Improves C1/C2/C8 domain metrics |
| **"Partial / not computed" metrics** (Appendix B) | dnsmasq DHCP log, AP events, SNI | **C5_F1** Wi‑Fi/DHCP re‑associations per hour (from dnsmasq log or UniFi events). **C8_F3** notification micro‑sessions (APNs/FCM SNI + short burst). **C3** food‑delivery hits via SNI |
| **BOM fusion (caps, grouping) not implemented** (§5.6.5) | – | Implement eq. 4.11/4.12 (metric→BOM→criterion with caps) |
| **Auto‑tuning failed on Dataset B** (§7.2.2) | Real per‑person baselines | Retry clustering/STL/CUSUM tuning on our data |
| **Data‑quality flags** (§7.2.5: coverage, VPN detection) | `tapcap` drop counters, capture uptime | Per day and device: coverage %, capture gaps, VPN/tunnel detection (e.g. WireGuard 51820, known VPN SNI). Exclude low‑coverage days from the gate |
| **Manual PCAP upload** (§5.8.4: "fully automatic capture pipeline" as future work) | Rotating `ready/` folder | Automatic ingest (2.2) → the dashboard updates daily without manual steps |
| **Privacy by design** (§2.3, §4.2.3: local processing, pseudonymised IDs, short retention) | Everything runs locally on the box | Pseudonymise MACs in Parquet (salted hash), keep the mapping separate, and define a retention or deletion policy before the field study. Get consent (and parental consent for minors, §2.3) |

## 4. Suggested order of work
### Step 4.1 in Detail: Automatic Ingest of Gateway Captures into the Thesis App

## Goal
Every night, convert yesterday's `tapcap` pcaps into exactly the Parquet layout the thesis app already reads. Write **one dataset per device**, with background traffic removed and timestamps in Swiss local time. The app (Network Metrics, Early Signs Overview) then works on our data without any UI changes.

```
/var/lib/tapcap/ready/*.pcap  (60 s rotation, UTC epoch)
        │  nightly, 00:20  (systemd timer)
        ▼
ingest_gateway.py ── tshark (fields only) ──► pandas
        │   1. convert to app schema (+ SNI column)
        │  2. filter background traffic
        │  3. split by client MAC → device alias
        │  4. write 5-min partitions per device and day
        ▼
<parquet root>/gw_<device>/gw_<device>__YYYYMMDD_HHMM.parquet
        │
        ▼
Streamlit app (on the server via SSH tunnel, or synced to laptop)
```

## 1. Constraints from the app code (why the design looks like this)

| App behaviour (file) | Consequence for the ingest |
| --- | --- |
| Partitions named `<dataset>__YYYYMMDD_HHMM.parquet` and found by regex `__(\d{8})_(\d{4})\.parquet$` (`03_User_and_Network_Settings.py`) | Use exactly this name. **One file per 5‑min window.** With 60 s pcaps, ~5 pcaps feed one window, so per‑pcap partitioning overwrites itself. Process a **whole day at once** and rewrite that day's files |
| Columns read: `Timestamp, Date, Hour, Protocol, Source IP, Destination IP, Source Port, Destination Port, TCP Flags, Length, IsDNS, DNS_QNAME, DNS_QTYPE, DNS_ANS_NAME, DNS_ANS_IPS` | Produce the same schema. `Protocol` ∈ {`TCP`,`UDP`,`OTHER`}. Extra columns (e.g. `SNI`) are ignored, so they're safe to add |
| `Timestamp` is naive local time (`datetime.fromtimestamp`). Night/day windows rely on it | Convert epoch → `Europe/Zurich`, then drop the tz info |
| Hostnames only from DNS answers within **the same day frame**, looked up by **Destination IP** (`metrics/common.py`) | Keep the client's DNS packets (to 10.42.0.1:53). Add SNI and fix inbound lookup (section 5) |
| DHCP rows (UDP 67/68) are counted for C5_F1 re‑associations (`base_features.py`) | Keep the client's DHCP packets |
| Dataset type is "Other" unless the name contains `onu`/`bras`. `group_prefix()` strips trailing digits | Name datasets `gw_<alias>`, with no trailing digits and no `onu`/`bras` substring |
| No person attribution: one dataset = one person | Splitting per MAC is our identity resolution |

## 2. Prerequisites on the server

```bash
sudo apt install -y python3-pandas python3-pyarrow   # tshark is already installed
ip -br link show eno1                                # note the gateway MAC
cat /var/lib/misc/dnsmasq.leases                     # note the AP's MAC and the client MACs
sudo install -d -o tapmeta -g tapmeta /var/lib/tapcap/parquet
sudo install -d /etc/tapgw
```

Device alias file `/etc/tapgw/devices.json`. It is the only place where MAC ↔ person is stored, so keep it root‑readable only:
```json
{
  "aa:bb:cc:dd:ee:01": "thierry_iphone",
  "aa:bb:cc:dd:ee:02": "karla_laptop"
}
```
iPhones: set the study Wi‑Fi to "Private Wi‑Fi Address: Fixed" so the MAC stays stable. Also note that **iCloud Private Relay** hides DNS and SNI. Agree with participants to turn it off on the study network, or document the gap.

## 3. Filtering rules

| Keep / drop | Rule | Why |
| --- | --- | --- |
| Drop | AP MAC and gateway's own traffic (any packet without a client MAC) | Controller/adoption traffic (8080, 10001, 3478 …) would fill every "quiet" minute |
| Drop | Any packet to/from `10.42.0.1` **except** ports 53 (DNS) and 67/68 (DHCP) | Removes SSH, UniFi and other gateway services. Keeps what the metrics need |
| Drop | mDNS 5353, SSDP 1900, NTP 123 | Periodic device chatter, not user behaviour. Would break sleep/idle metrics |
| Drop | Broadcast/multicast destination from the gateway (e.g. DHCP offers) | Not attributable to a device |
| Keep | Everything else between a client and the internet | That is the behavioural signal |

Do **not** drop STUN 3478 globally. WhatsApp/FaceTime calls use it towards the internet. Only the 3478 traffic to the gateway goes, and the rule above already covers that.

Optional, later: an exclusion list for known always‑on keep‑alives (e.g. Apple push on 5223). Decide this only after looking at real night data, because those packets may also be genuine signals.

## 4. The script: `scripts/ingest_gateway.py` (sketch, untested)

```python
#!/usr/bin/env python3
"""Convert one day of tapcap pcaps into the app's 5-min Parquet layout, one dataset per device."""
import argparse, hashlib, io, json, subprocess
from datetime import date, datetime, time, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo
import pandas as pd

READY   = Path("/var/lib/tapcap/ready")
OUT     = Path("/var/lib/tapcap/parquet")
ALIASES = Path("/etc/tapgw/devices.json")
TZ      = ZoneInfo("Europe/Zurich")
GW_IP   = "10.42.0.1"
GW_MAC  = "xx:xx:xx:xx:xx:xx"            # eno1
AP_MACS = {"yy:yy:yy:yy:yy:yy"}          # U7 Lite
SALT    = "change-me"                     # for pseudonymous names of unknown devices
NOISE_PORTS = {5353, 1900, 123}
GW_ALLOWED_PORTS = {53, 67, 68}

FIELDS = ["frame.time_epoch", "frame.len", "eth.src", "eth.dst", "ip.src", "ip.dst", "ip.proto",
          "tcp.srcport", "tcp.dstport", "udp.srcport", "udp.dstport",
          "dns.flags.response", "dns.qry.name", "dns.qry.type", "dns.resp.name", "dns.a",
          "tls.handshake.extensions_server_name"]   # also filled for QUIC Initial in tshark 4.x

def run_tshark(pcap: Path) -> pd.DataFrame:
    cmd = ["tshark", "-n", "-r", str(pcap), "-Y", "ip", "-T", "fields",
           "-E", "separator=\t", "-E", "occurrence=a", "-E", "aggregator=,", "-E", "quote=n"]
    for f in FIELDS:
        cmd += ["-e", f]
    out = subprocess.run(cmd, capture_output=True, text=True, check=True).stdout
    return pd.read_csv(io.StringIO(out), sep="\t", header=None, names=FIELDS, dtype=str, quoting=3)

def first(s: pd.Series) -> pd.Series:
    return s.str.split(",", n=1).str[0]

def to_app_schema(raw: pd.DataFrame) -> pd.DataFrame:
    d = pd.DataFrame(index=raw.index)
    ts = pd.to_datetime(first(raw["frame.time_epoch"]).astype(float), unit="s", utc=True)
    d["Timestamp"] = ts.dt.tz_convert(TZ).dt.tz_localize(None)
    d["Date"] = d["Timestamp"].dt.date
    d["Hour"] = d["Timestamp"].dt.hour
    d["Protocol"] = first(raw["ip.proto"]).map({"6": "TCP", "17": "UDP"}).fillna("OTHER")
    d["Source IP"] = first(raw["ip.src"])
    d["Destination IP"] = first(raw["ip.dst"])
    d["Source Port"] = pd.to_numeric(first(raw["tcp.srcport"]).fillna(first(raw["udp.srcport"])), errors="coerce").astype("Int64")
    d["Destination Port"] = pd.to_numeric(first(raw["tcp.dstport"]).fillna(first(raw["udp.dstport"])), errors="coerce").astype("Int64")
    d["TCP Flags"] = None                                  # not used by any metric
    d["Length"] = pd.to_numeric(raw["frame.len"]).astype("int64")
    resp = first(raw["dns.flags.response"])
    d["IsDNS"] = resp.notna()
    is_query = resp.isin(["0", "False", "false"])
    d["DNS_QNAME"] = first(raw["dns.qry.name"]).where(is_query)
    d["DNS_QTYPE"] = pd.to_numeric(first(raw["dns.qry.type"]), errors="coerce").where(is_query)
    d["DNS_ANS_NAME"] = first(raw["dns.resp.name"])
    d["DNS_ANS_IPS"] = raw["dns.a"]                        # already "ip1,ip2"
    d["SNI"] = first(raw["tls.handshake.extensions_server_name"])
    d["_esrc"] = first(raw["eth.src"]).str.lower()
    d["_edst"] = first(raw["eth.dst"]).str.lower()
    return d

def filter_and_tag(d: pd.DataFrame, no_filter: bool = False) -> pd.DataFrame:
    d["_mac"] = d["_esrc"].where(d["_esrc"] != GW_MAC, d["_edst"])
    keep = ~d["_mac"].isin(AP_MACS | {GW_MAC, "ff:ff:ff:ff:ff:ff"})
    keep &= ~d["_mac"].str.startswith(("01:00:5e", "33:33"), na=True)
    if not no_filter:
        sp, dp = d["Source Port"], d["Destination Port"]
        to_gw = (d["Source IP"] == GW_IP) | (d["Destination IP"] == GW_IP)
        keep &= ~to_gw | sp.isin(GW_ALLOWED_PORTS) | dp.isin(GW_ALLOWED_PORTS)
        keep &= ~(sp.isin(NOISE_PORTS) | dp.isin(NOISE_PORTS))
    return d[keep.fillna(False)]

def device_name(mac: str, aliases: dict) -> str:
    if mac in aliases:
        return f"gw_{aliases[mac]}"
    h = hashlib.sha256((SALT + mac).encode()).hexdigest()[:8]
    return f"gw_unknown_{h}_dev"                           # no trailing digits (group_prefix)

def pcaps_for_day(day: date) -> list[Path]:
    start = datetime.combine(day, time(0), TZ).timestamp()
    end = datetime.combine(day + timedelta(days=1), time(0), TZ).timestamp()   # DST-safe
    return sorted(p for p in READY.glob("*.pcap") if start <= p.stat().st_mtime < end + 600)

def write_day(df: pd.DataFrame, name: str, day: date) -> int:
    ddir = OUT / name
    ddir.mkdir(parents=True, exist_ok=True)
    for f in ddir.glob(f"{name}__{day:%Y%m%d}_*.parquet"):   # idempotent: rewrite the whole day
        f.unlink()
    cols = [c for c in df.columns if not c.startswith("_")]   # MAC never stored in Parquet
    n = 0
    for key, part in df.groupby(df["Timestamp"].dt.floor("5min")):
        final = ddir / f"{name}__{key:%Y%m%d_%H%M}.parquet"
        tmp = final.with_suffix(".tmp")
        part[cols].to_parquet(tmp, index=False)
        tmp.rename(final)                                  # atomic, the app never sees half files
        n += 1
    return n

def ingest_day(day: date, aliases: dict, no_filter: bool) -> None:
    frames = [filter_and_tag(to_app_schema(run_tshark(p)), no_filter) for p in pcaps_for_day(day)]
    if not frames:
        print(f"{day}: no pcaps"); return
    df = pd.concat(frames, ignore_index=True)
    df = df[df["Timestamp"].dt.date == day].sort_values("Timestamp")
    for mac, g in df.groupby("_mac"):
        name = device_name(mac, aliases)
        print(f"{day} {name}: {len(g)} packets, {write_day(g, name, day)} partitions")

if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--day", help="YYYY-MM-DD (default: yesterday)")
    ap.add_argument("--since", help="backfill from YYYY-MM-DD up to yesterday")
    ap.add_argument("--no-filter", action="store_true", help="skip background filtering (for validation)")
    a = ap.parse_args()
    aliases = {k.lower(): v for k, v in json.loads(ALIASES.read_text()).items()} if ALIASES.exists() else {}
    yesterday = datetime.now(TZ).date() - timedelta(days=1)
    if a.since:
        d = date.fromisoformat(a.since)
        while d <= yesterday:
            ingest_day(d, aliases, a.no_filter); d += timedelta(days=1)
    else:
        ingest_day(date.fromisoformat(a.day) if a.day else yesterday, aliases, a.no_filter)
```

Design notes:
- **Idempotent:** a re‑run rewrites the device/day, so a crash or a change to the filter rules just means running it again (`--since`).
- **Pseudonymous:** the MAC never goes into Parquet. Only the alias file links a dataset to a device/person (thesis §4.2.3).
- **Memory:** one day for all devices is held in RAM. Fine for a few devices. If it grows, process per pcap and append per device to a day buffer on disk.
- **Speed:** about 1,440 tshark calls per day (one per pcap). Expect several minutes. If that's too slow, `mergecap` the day's files first and run tshark once.

## 5. Small patch in the app: hostnames for inbound traffic + SNI

In `app/metrics/common.py`, `enrich_with_hostnames()` looks up hostnames by `Destination IP` only. Inbound packets (server → client) therefore never get an SLD, which leaves e.g. `streaming_inbound_mask` empty. Proposed change:

```python
def enrich_with_hostnames(df):
    ...
    ip2host = build_dns_map(out)
    if "SNI" in out.columns:                     # TLS/QUIC ClientHello: client -> server
        sni = out.loc[out["SNI"].notna(), ["Destination IP", "SNI"]]
        for ip, name in zip(sni["Destination IP"], sni["SNI"]):
            ip2host.setdefault(ip, name)         # DNS answers take precedence
    src_priv = out["Source IP"].map(is_private_ip)
    dst_priv = out["Destination IP"].map(is_private_ip)
    remote = out["Destination IP"].where(~(dst_priv & ~src_priv), out["Source IP"])
    out["ResolvedHost"] = remote.map(ip2host)
    ...  # rest unchanged
```
This changes metric values compared to the thesis (more rows get an SLD). Re‑calibrate afterwards anyway (step 5 of the plan), and record the change in our report.

## 6. Scheduling (systemd)

`/etc/systemd/system/tapgw-ingest.service`
```ini
[Unit]
Description=Convert yesterday's pcaps to per-device Parquet
After=tapcap@eno1.service

[Service]
Type=oneshot
User=tapmeta
Group=tapcap
Environment=TZ=Europe/Zurich
ExecStart=/usr/bin/python3 /usr/local/bin/ingest_gateway.py
Nice=10
IOSchedulingClass=idle
```

`/etc/systemd/system/tapgw-ingest.timer`
```ini
[Unit]
Description=Nightly ingest

[Timer]
OnCalendar=*-*-* 00:20:00
Persistent=true

[Install]
WantedBy=timers.target
```

```bash
sudo install -m 755 ingest_gateway.py /usr/local/bin/
sudo chown root:tapmeta /etc/tapgw/devices.json && sudo chmod 640 /etc/tapgw/devices.json
sudo systemctl daemon-reload && sudo systemctl enable --now tapgw-ingest.timer
sudo -u tapmeta TZ=Europe/Zurich python3 /usr/local/bin/ingest_gateway.py --since 2026-10-01   # backfill
journalctl -u tapgw-ingest -n 50
```

## 7. Getting the data into the app

**Option A (recommended, data stays on the box, as in the thesis edge design):** run the app on the server.
```bash
# in app/docker-compose.yml add a volume:  /var/lib/tapcap/parquet:/app/processed_parquet:ro
docker compose up -d --build
ssh -L 8501:localhost:8501 kathy@172.20.10.10    # then open http://localhost:8501
```
Note: a read‑only mount means the UI uploader and `known_ips.txt` can't write there. Use a read‑write mount if you need them.

**Option B:** sync to the laptop, e.g. `rsync -a kathy@172.20.10.10:/var/lib/tapcap/parquet/ app/processed_parquet/`. Simpler for development, but sensitive data leaves the gateway. Only do this with test data or consent.

In both cases: in the app, select the `gw_*` datasets (type "Other") and press **"Refresh cached day metrics"**, because `feature_cache/` holds old daily records.

## 8. Validation before trusting results

1. **Schema:** compare `python3 -c "import pyarrow.parquet as pq; print(pq.read_schema('<one gw file>'))"` with a thesis partition.
2. **Equivalence with the thesis loader:** take one small pcap. Upload it through the app UI (scapy path) and also run `ingest_gateway.py --no-filter` on it. Packet counts per 5‑min window and the day's base record (`compute_daily_base_record`) should match closely.
3. **Counts:** `capinfos -c` over the day's pcaps ≈ sum of all `gw_*` packets plus the filtered packets. Log the drop count per rule.
4. **Time zone:** do a known action at a noted time (e.g. open YouTube at 14:05). It must appear at 14:05 in "Packets per minute".
5. **Enrichment:** the DNS Enrichment Map / SLD list for the test phone shows plausible domains (apple.com, youtube.com …), not mostly `None`.
6. **Night silence:** look at 00:00–06:00 for a phone lying unused. If it never goes quiet for ≥30 min, C4 sleep metrics will saturate like Dataset B. Then investigate which SNI/ports cause it before adding any exclusion.

## 9. Tasks and order
1. Fill in GW_MAC, AP_MACS and devices.json. Run the script by hand on 1 day. Do validation 1–5.
2. Apply the app patch (section 5) on a branch. Re‑run, then compare the SLD coverage before and after.
3. Install the systemd timer and backfill.
4. Pick a hosting option (A/B) and refresh the feature cache.
5. Validation 6 with real nights. Then start the ≥14‑day collection per participant.

### Step 4.2 other future tasks

2. Run it on 1–2 days of test‑device data. Check plausibility in Network Metrics, especially night/day and idle gaps.
3. Add SNI from `feed.ndjson` as a second source of hostnames.
4. Automate the ingest on the server (systemd timer).
5. Collect ≥14 days per participant, then re‑calibrate `fasl_config.json` and evaluate the gate.
6. Extensions: BOM fusion, the newly feasible metrics (C5_F1, C8_F3), data‑quality flags, retention policy.
