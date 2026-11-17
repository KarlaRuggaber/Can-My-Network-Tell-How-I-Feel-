# Capturing mobile data through a VPN to the gateway (concept, not built)

Status 17.11.2026: **design only, nothing of this is implemented or configured on the gateway.** This
file describes how a participant's phone would be recorded on mobile data (and on foreign WiFi) in a
future real deployment, and what exactly has to be done for it. Nothing here is needed for the
simulated profiles of the live run.

Reviewed 17.11.2026 against the gateway's actual configuration (read-only: tapcap and tapfeed units,
dnsmasq, tmpfiles, tapingest flags) and the code (ingest background filter, app metrics, portal). The
ingest part was tested locally with a raw-IP capture. Points that can only be tested with a real phone
and router are marked "to test".

## 1. Problem

The gateway only sees traffic that passes through it, i.e. while the phone is on the access point's
WiFi at home. As soon as the person leaves the house (or switches WiFi off), the phone uses mobile data
and the gateway sees **nothing**. The app cannot tell this apart from inactivity: a day out reads as
"little usage", an evening away as "went to bed early". This biases exactly the metrics we care about
(sleep, withdrawal, activity, social contact).

## 2. Idea

The phone runs a **WireGuard VPN to the home gateway** whenever it is *not* on the home WiFi. All its
traffic then travels encrypted to the gateway, leaves for the internet from there (NAT on the uplink,
like the WiFi clients) and is recorded on the tunnel interface `wg0`, before NAT and unencrypted (as far
as the app itself does not encrypt it, the same as on `eno1`).

```
at home:     phone --WiFi--> U7 Lite AP --eno1--> gateway --wlp2s0--> internet     (recorded on eno1)
away:        phone --mobile data--> internet --UDP 51820--> home router --> gateway
                                    --wg0--> gateway --wlp2s0--> internet          (recorded on wg0)
```

Everything after the capture stays as it is: `tapcap` → pcap in a `ready/` folder → `tapingest` →
5-minute parquet in the person's dataset → app and portal.

### Why WireGuard and not an app on the phone

| Option | Verdict |
|---|---|
| **WireGuard VPN to the gateway** (this document) | Free official apps for iOS and Android, no own app development, same pipeline, stable device identity (fixed tunnel IP per phone). Chosen. |
| Tailscale exit node | Works without a port forward (NAT traversal), but the existing tailnet is Thierry's admin network; participants must not join it. Only as a fallback with a *separate* tailnet or a self-hosted Headscale (Section 11). |
| Own capture app on iOS | Apple allows no packet capture; only a "packet tunnel" app (NetworkExtension) with developer account, entitlements, TestFlight. Building our own VPN client: too big. |
| Capture app on Android (e.g. PCAPdroid) | Possible without root and even shows which app sent each packet, but needs an upload path of the pcaps to the gateway and does not exist for iOS. Possible later as an Android-only extra. |
| `rvictl` (iPhone via USB on a Mac) | Lab only, not for everyday use. |

## 3. Decisions to make before building

1. **Address range of the tunnel:** `10.42.2.0/24`, gateway `10.42.2.1`, phones `10.42.2.10–99`
   (10.42.0.0/24 = real LAN, 10.42.1.0/24 = br-sim, 10.43.0.0/24 = br-peer are taken).
2. **Port:** UDP `51820` (WireGuard default).
3. **How the phone reaches the gateway:** port forward on the home router plus a dynamic DNS name
   (Section 4). If that is impossible (carrier-grade NAT, no router access): fallback in Section 11.
4. **When the VPN is on:** always, *except* on the home access point's WiFi (there the gateway already
   sees the traffic on `eno1`). This avoids double recording and an unnecessary detour at home.
5. **Consent:** the consent text must explicitly say that traffic is also recorded **outside the
   home** (Section 10).
6. **Retention:** how long pcaps of real devices are kept (Section 5.4, "Storage").

**Prerequisite:** the real-device setup in `app_pcap_to_dsm5/ingest/README.md` ("Real devices") is done,
with the MAC-first ingest from PR #18 deployed. Build this only after the live run (after 22.11.2026).

## 4. Making the gateway reachable from the internet

The gateway's uplink (`wlp2s0`) is a client of the home WiFi, behind the home router's NAT. Incoming
connections from the internet only reach it through a port forward.

1. **Check for carrier-grade NAT (CGNAT).** Compare the WAN address in the home router's web interface
   with the public address the gateway sees (e.g. `curl -4 https://ifconfig.me` on the gateway). If they
   differ, or the router's WAN address is in `100.64.0.0/10`, the line has CGNAT: a port forward cannot
   work → ask the provider for a public IPv4 address, or use Section 11.
2. **Give the gateway a fixed address in the home network:** in the home router, a DHCP reservation for
   the MAC of `wlp2s0` (`ip link show wlp2s0` on the gateway). The gateway's netplan stays on DHCP.
3. **Port forward on the home router:** UDP `51820` (external) → gateway's reserved address, UDP `51820`.
4. **Dynamic DNS name**, because home lines change their public IP: the router's built-in service
   (e.g. MyFRITZ on a FRITZ!Box) or a free DDNS service. The phones use this name as the VPN endpoint,
   never the bare IP.
5. **Check the home upload speed** (speed test while connected to the home WiFi). On the VPN, every
   byte the phone downloads goes down *and* up the home line once more, so the home **upload** caps the
   phone's download speed. A video stream needs about 3–8 Mbit/s.

## 5. Gateway setup (all with sudo, by whoever administers the gateway)

Back up first, as for the other gateway changes:

```bash
sudo mkdir -p /root/vpn-backup-$(date +%Y%m%d) && sudo cp -a /etc/nftables.conf /etc/dnsmasq.d /etc/dnsmasq.conf /root/vpn-backup-$(date +%Y%m%d)/
```

### 5.1 WireGuard

```bash
sudo apt install -y wireguard qrencode
sudo install -d -m 700 /etc/wireguard
cd /etc/wireguard && sudo sh -c 'umask 077; wg genkey | tee server.key | wg pubkey > server.pub'
```

(WireGuard is not installed on the gateway yet, checked 17.11.2026.) Create the config readable by root
only, then fill it in with `sudo nano /etc/wireguard/wg0.conf`:

```bash
sudo install -m 600 /dev/null /etc/wireguard/wg0.conf
```

No `PostUp`/`PostDown`: firewall and NAT stay in `/etc/nftables.conf`, the gateway's only firewall.

```ini
[Interface]
Address    = 10.42.2.1/24
ListenPort = 51820
PrivateKey = <content of /etc/wireguard/server.key>

# one [Peer] block per phone, see Section 6
```

```bash
sudo systemctl enable --now wg-quick@wg0
sudo wg show                       # interface wg0, listening port 51820
```

IP forwarding is already on (the gateway routes `eno1` and `br-sim`).

### 5.2 Firewall (`/etc/nftables.conf`, i.e. `traffic-runner/gateway/nftables.conf`)

New lines only; same pattern as the SIM side (DNS and ping on the gateway, internet, nothing else, no
access to `eno1`, `br-sim` or `br-peer`):

```nft
define VPN = "wg0"

# chain input
        iifname $WAN udp dport 51820 accept               # VPN: WireGuard from the internet
        iifname $VPN udp dport 53 accept                  # VPN: DNS
        iifname $VPN tcp dport 53 accept                  # VPN: DNS over TCP
        iifname $VPN icmp type echo-request accept        # VPN: ping the gateway

# chain forward
        iifname $VPN oifname $WAN accept                  # VPN: phones -> internet
```

The existing `oifname $WAN masquerade` already covers NAT for `10.42.2.0/24`. Check and load:

```bash
sudo nft -c -f /etc/nftables.conf && sudo systemctl restart nftables
```

Optional, only if some websites hang over the VPN (MTU problems): in `chain forward`, before the accept
rules, `oifname $VPN tcp flags syn tcp option maxseg size set rt mtu`.

### 5.3 DNS (dnsmasq)

The phones must use the gateway's dnsmasq: the app gets domain names from the captured DNS answers
(`enrich_with_hostnames`), and the dnsmasq log feeds `tapfeed`. New file `/etc/dnsmasq.d/vpn.conf`, same
pattern as the existing `sim.conf` for `br-sim`:

```
interface=wg0
no-dhcp-interface=wg0
```

`wg0` comes up after dnsmasq at boot; that is fine because `tapgw.conf` already uses `bind-dynamic`
(checked on the gateway 17.11.2026; HardwareSetup.md still shows the older `bind-interfaces`), so
dnsmasq starts listening on `wg0` as soon as it appears. Then:

```bash
dnsmasq --test && sudo systemctl restart dnsmasq
```

### 5.4 Capture: a third tapcap instance

Same pattern as `tapcap@br-sim` (`traffic-runner/gateway/tapcap@br-sim.override.conf`), own folder:

`/etc/tmpfiles.d/tapcap.conf`, append:
```
d /var/lib/tapcap/vpn        0750 tapcap tapcap -
d /var/lib/tapcap/vpn/tmp    0750 tapcap tapcap -
d /var/lib/tapcap/vpn/ready  0750 tapcap tapcap -
```

`/etc/systemd/system/tapcap@wg0.service.d/override.conf`:
```ini
[Unit]
After=wg-quick@wg0.service
Wants=wg-quick@wg0.service
StartLimitIntervalSec=0

[Service]
ExecStart=
ExecStart=/usr/local/bin/tapcap --iface %i --out-dir /var/lib/tapcap/vpn --rotate-secs 60 --rotate-mb 512 --buffer-mb 256
RestartSec=5
```

```bash
sudo systemd-tmpfiles --create
sudo systemctl daemon-reload && sudo systemctl enable --now tapcap@wg0
```

Like `br-sim`, the unit keeps restarting (base unit: `Restart=always`) until `wg0` exists, so the order
at boot does not matter.

**What was checked (17.11.2026, gateway read-only and a local test):**

- The base unit `tapcap@.service` runs `ip link set dev %i up promisc on` and
  `-ethtool -K %i gro off …` before starting. The `-` makes the `ethtool` step optional, so it may fail
  on `wg0` without stopping the unit. The `ip link … promisc on` step has no `-`; it should work on a
  WireGuard interface, but check `systemctl status tapcap@wg0` at the first start.
- tapcap writes each file with the interface's own link type (`cap.get_datalink()` in
  `~kathy/tapcap/src/main.rs`), so `wg0` files are **raw IP** without an Ethernet header
  (`capinfos -E <file>` → "Raw IP"). A raw-IP test file went through `tapingest` correctly: rows,
  device lookup without a MAC, DNS rows (Section 5.5).

`tapfeed@wg0` (SNI and hostnames) is optional: the app does not read `feed.ndjson` yet. If it is added,
give it the same drop-in as `tapfeed@br-sim` (`Environment=TAPFEED_DNS=0`): the DNS events come from
the dnsmasq journal, which `tapfeed@eno1` already follows for all interfaces, so a second instance would
write them twice.

**Storage:** none of the `ready/` folders is cleaned up automatically (no age field in
`/etc/tmpfiles.d/tapcap.conf`), and on 17.11.2026 the disk was 70 % full (137 GB free). Mobile data adds
the person's whole day away from home. A retention rule for the real-device folders (e.g. delete pcaps
once ingested and older than N days) has to be decided before real use anyway, with or without VPN.

### 5.5 Ingest

Two changes in `tapingest.service` (`sudo systemctl edit --full tapingest`), both needed:

1. One more watch folder, next to the existing ones:
   ```
       --watch /var/lib/tapcap/vpn/ready \
   ```
2. **The tunnel network for the background filter.** The filter only keeps packets of clients in its
   LAN networks and treats traffic to the gateway as gateway service (except DNS). Its defaults are
   `10.42.0.0/24` and `10.42.1.0/24` with the gateways `10.42.0.1` and `10.42.1.1`, so **without this
   step every VPN packet is dropped as `no_client`** (tested: 4 of 4 dropped). The flags replace the
   defaults, so all three networks must be listed:
   ```
       --gateway-ip 10.42.0.1 --gateway-ip 10.42.1.1 --gateway-ip 10.42.2.1 \
       --lan-net 10.42.0.0/24 --lan-net 10.42.1.0/24 --lan-net 10.42.2.0/24 \
   ```

```bash
sudo systemctl restart tapingest
journalctl -u tapingest -n 5 --no-pager    # "Background filter on: gateway 10.42.0.1,10.42.1.1,10.42.2.1, LAN …,10.42.2.0/24"
```

No code change is needed for the device lookup: packets from `wg0` carry no MAC, and since the
MAC-first lookup (PR #18, must be merged and deployed first) a packet without a MAC is assigned by its
IP. The tunnel IP is fixed per phone (`AllowedIPs = 10.42.2.x/32` on the gateway), so it identifies the
phone reliably: WireGuard only accepts packets with that source address from that phone's key.

Tested locally on 17.11.2026 with a raw-IP pcap (DNS query and answer via `10.42.2.1`, a TCP handshake
to a public address) and a devices file with a `_vpn` row: with the flags above, all packets landed in
the person's dataset.

## 6. Per phone

Requires the person's consent (Section 10) and that the phone is already registered for the home WiFi
(`ingest/README.md`, "Real devices").

1. **Choose the tunnel address**, e.g. `10.42.2.21` (same last number as the WiFi address `10.42.0.21`
   keeps the list readable).
2. **Create the phone's keys and config on the gateway** in a temporary folder:
   ```bash
   sudo -i
   umask 077; mkdir -p /root/vpn-new && cd /root/vpn-new
   wg genkey | tee phone.key | wg pubkey > phone.pub
   cat > karla_iphone.conf <<EOF
   [Interface]
   PrivateKey = $(cat phone.key)
   Address    = 10.42.2.21/32
   DNS        = 10.42.2.1

   [Peer]
   PublicKey  = $(cat /etc/wireguard/server.pub)
   Endpoint   = <ddns-name>:51820
   AllowedIPs = 0.0.0.0/0, ::/0
   EOF
   ```
   `AllowedIPs` includes `::/0` so IPv6 cannot bypass the tunnel. The tunnel has no IPv6 address, so
   IPv6 is simply unavailable on the VPN and apps fall back to IPv4 (the pipeline reads IPv4 only).
3. **Register the phone on the gateway:** append to `/etc/wireguard/wg0.conf`
   ```ini
   [Peer]
   # karla_iphone (gw_karla_a)
   PublicKey  = <content of phone.pub>
   AllowedIPs = 10.42.2.21/32
   ```
   and apply without dropping the other phones: `wg syncconf wg0 <(wg-quick strip wg0)`.
4. **Transfer the config to the phone by QR code**, then delete the temporary files (the gateway must
   not keep the phone's private key):
   ```bash
   qrencode -t ansiutf8 < karla_iphone.conf      # scan in the WireGuard app: + → "Create from QR code"
   cd / && shred -u /root/vpn-new/* && rmdir /root/vpn-new
   ```
5. **On the phone, always-on except at home:**
   - **iPhone** (app "WireGuard" from the App Store): open the tunnel → Edit → "On-Demand Activation":
     *Cellular* on, *Wi-Fi* on with "Except these SSIDs" = the access point's WiFi name. In Settings,
     switch off iCloud Private Relay: it sends Safari's DNS and traffic through Apple's relays, so the
     gateway sees no domain names (the same gap exists at home, `MasterThesisInc.md` §2). Whether a
     full-tunnel VPN already bypasses Private Relay is not verified; switching it off is the safe way.
   - **Android** (app "WireGuard"): Settings → Network → VPN → WireGuard ⚙ → "Always-on VPN" and "Block
     connections without VPN". Android has no exception per WiFi name in the official app, so the VPN
     also runs at home; that needs the "split DNS" step in Section 9 ("VPN on at home").
6. **Register the tunnel address for the ingest:** one more row in `/etc/tapingest/devices.real.csv`,
   **same dataset**, separate device name, no MAC:
   ```
   karla_iphone_vpn,phone,,10.42.2.21,gw_karla_a
   ```
   The ingest reloads the file by itself (no restart). Device names must be unique, MACs and IPs too;
   an empty MAC is allowed.
7. **Test** (Section 7).

**Remove a phone:** delete its `[Peer]` block, `wg syncconf …` as in step 3, delete the `_vpn` row in
`devices.real.csv`, delete the tunnel on the phone.

## 7. Checks after setup

With the phone on mobile data (WiFi off):

| Check | Expected |
|---|---|
| WireGuard app | "Active", data received grows |
| `sudo wg show wg0` on the gateway | the phone's peer with a recent "latest handshake" |
| Open `https://ifconfig.me` on the phone | the home line's public IP, not the carrier's |
| An IPv6 test page on the phone | "no IPv6" |
| `journalctl -u dnsmasq -n 20` | queries from `10.42.2.21` |
| `ls -lt /var/lib/tapcap/vpn/ready \| head` | a new file every minute |
| `journalctl -u tapingest -n 20` | files from `vpn/ready` processed, rows mapped, **not** "dropped as background" |
| App or portal | the person's day shows activity during the test |

Then on the home WiFi: the VPN switches off by itself (iPhone), traffic appears again on `eno1`. Then
the reverse: leave the home WiFi and check that the tunnel comes back on mobile data within a minute.

Repeat the mobile-data test once per carrier the participants use (Swisscom, Sunrise, Salt, …): some
mobile networks are IPv6-only towards the phone and reach IPv4 addresses through translation (NAT64 or
464XLAT); the endpoint name must then still resolve and connect.

## 8. Rollback

```bash
sudo systemctl disable --now tapcap@wg0 wg-quick@wg0
sudo cp -a /root/vpn-backup-<date>/nftables.conf /etc/nftables.conf && sudo systemctl restart nftables
sudo rm /etc/dnsmasq.d/vpn.conf && sudo systemctl restart dnsmasq
```

In tapingest, remove the `--watch /var/lib/tapcap/vpn/ready` line and the `--gateway-ip`/`--lan-net`
flags (or leave the flags: without `wg0` they change nothing), then restart it. Remove the port forward
on the home router. Phones lose internet while On-Demand is active, so switch off or delete the tunnel there too.

## 9. Consequences for the data and the metrics

- **Full days:** the main gain. Gaps then mean "phone off or VPN off", not "away from home".
- **One dataset per person:** the VPN rows go into the same dataset as the WiFi rows. Where a packet
  came from stays visible through the address range (`10.42.2.x` = mobile data / foreign WiFi,
  `10.42.0.x` = home WiFi), so "time away from home" is even a possible new feature.
- **Portal:** the portal chooses a person's devices by their local IP (`filter_devices` in
  `frontend/backend/cmn_frontend/daily.py`). The tunnel IP `10.42.2.x` must be selected together with
  the WiFi IP, otherwise the mobile-data traffic is left out of the person's view. Device names come
  only from `traffic-runner/config/devices.csv` (see "Not built yet" in `ingest/README.md`), so the
  tunnel IP appears without a name until the portal also reads `devices.real.csv`.
- **The app's metrics:** no change needed. Up/download and the other address-based metrics only ask
  whether an address is private (`ipaddress.is_private`), and `10.42.2.x` is private like `10.42.0.x`.
- **Packet sizes:** packets on `wg0` have no 14-byte Ethernet header, so `Length` is 14 bytes smaller
  per packet than the same packet on `eno1` (confirmed in the local test: a TCP SYN is 40 instead of 54
  bytes). The tunnel MTU (1420 on the gateway; the phone app may choose a lower one) also splits large
  transfers into slightly more packets. Byte-volume metrics are therefore not exactly comparable
  between home and away. Either accept it or add 14 bytes per raw-IP packet in `tapingest` (one line);
  decide when building.
- **Coverage:** if the person switches the VPN off, the data has gaps again. A coverage flag per day
  (the data-quality flags planned in `MasterThesisInc.md`) should count hours with neither `eno1` nor
  `wg0` traffic.
- **Gateway or home internet down = no internet on the phone.** WireGuard has no connection state: if
  the gateway is unreachable (power cut, home internet outage, router restart with a new IP before the
  DDNS name is updated), the phone keeps sending into the tunnel and has **no internet on mobile data**
  until the person switches the VPN off (on Android with "Block connections without VPN" not even
  then without opening the app). Participants must know this, and the gateway's daily report should
  warn when a phone has had no handshake for a long time (`wg show wg0 latest-handshakes`, needs root,
  so via a small root helper or a systemd timer that writes the value to a file).
- **VPN on at home (Android, or an iPhone without the SSID exception):** the phone then connects to its
  endpoint from inside the home WiFi. Two problems: the DDNS name points to the home's public IP, which
  only works if the home router supports "hairpin NAT"; and the encrypted tunnel packets would also be
  recorded on `eno1` and counted as traffic. Fix for both, **split DNS**: dnsmasq answers the DDNS name
  with the gateway's LAN address (`/etc/dnsmasq.d/vpn.conf`: `address=/<ddns-name>/10.42.0.1`) and the
  firewall accepts WireGuard on the LAN side (`iifname $LAN udp dport 51820 accept`). Then the tunnel
  runs from the phone straight to the gateway, the inner traffic is recorded once on `wg0`, and the
  outer packets on `eno1` go to `10.42.0.1` on a port other than 53, which the existing background
  filter already drops (`gateway_service`). To test: when the phone leaves home, WireGuard must look the
  name up again (now via the carrier's DNS → public IP); if the app keeps the old address, the tunnel
  stays dead until it is restarted.
- **Latency and speed:** slightly slower on the go (detour via the home), video calls and games
  included. Battery: WireGuard is light; the effect should be small, but it should be checked with the
  first user.

## 10. Privacy and consent

- The recording no longer stops at the front door: work, university, friends' homes are included. The
  consent text must say this explicitly, and the person must know how to pause it (switch off the VPN)
  and that pauses are visible as gaps.
- The gateway only records the inner packets on `wg0`. The carrier IP of the phone (a coarse location)
  is visible in `wg show` while connected but is not written to any file; it must not be logged.
- Each phone has its own key. Losing the phone → delete its peer (Section 6, "Remove a phone").
- The home router port forward exposes one UDP port; WireGuard does not answer packets without a valid
  key, so the port looks closed to scanners.

## 11. Fallback without a port forward (CGNAT, no router access)

A VPN service that connects outward from the gateway, like the existing Tailscale access:

- **Separate tailnet or self-hosted Headscale** just for participants (never Thierry's admin tailnet),
  gateway as **exit node** (`tailscale up --advertise-exit-node`), the phone's Tailscale app with that
  exit node and "always on". Capture then on that interface (`tailscale0` or a second instance), the
  phone's Tailscale IP (`100.x.y.z`, fixed per device) goes into `devices.real.csv` instead of
  `10.42.2.x`, and the ingest's background filter needs that network instead of `10.42.2.0/24`
  (`--lan-net 100.64.0.0/10 --gateway-ip <gateway's Tailscale IP>`, Section 5.5). Note that the app
  counts up/download only between private and public addresses, and `100.64.0.0/10` is not "private"
  for Python's `ipaddress`; this would have to be checked in the metrics before choosing this route.
- To check before choosing it: running a second tailscaled next to the admin one, DNS (Tailscale's
  MagicDNS must forward to dnsmasq, otherwise DNS names are missing), and the firewall lines for the new
  interface (as in 5.2).

## 12. Effort estimate

| Part | Effort |
|---|---|
| Router: reservation, port forward, DDNS, CGNAT check | ~1 h, at the participant's home |
| Gateway: WireGuard, firewall, dnsmasq, tapcap@wg0, ingest | ~2–3 h including tests |
| Per phone | ~15 min |
| Code | none required; optional: `Length` correction, filter for double recording, coverage flag |
