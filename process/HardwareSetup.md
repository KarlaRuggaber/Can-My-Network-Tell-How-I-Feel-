## 1. What we did today and why

Today's work covered the hardware setup for the project: building a self-contained, reboot-proof WiFi gateway that records all client traffic as rotating pcap files and as a unified metadata feed (DNS, TLS SNI, QUIC SNI, hostnames), ready to feed the existing analysis model. This is one part of the larger project, not the whole of it; the analysis model and its integration are separate work.

The brief for this part set four requirements:

- Mirror network traffic using an Ubuntu server and Ubiquiti equipment, without disturbing the network.
- Store the traces so an existing analysis model can consume them.
- Use the most modern capture approach available, with the capture program written in Rust for speed.
- First understand the overall approach, then build it step by step from a clean server.

The work was done with the support of an AI assistant (Claude), which proposed designs, wrote and tested code and configurations, and guided debugging; all commands were executed and verified by the team on the real hardware.

## 2. Phase 1: Research and architecture decisions

The research phase chose switch port mirroring as the copy method and AF\_PACKET TPACKET\_V3, driven from Rust, as the capture path. Both choices were later revised or confirmed by the hardware reality (Phase 4).

**How to obtain a copy of the traffic.** Four approaches were compared:

| Approach | How it works | Assessment |
| --- | --- | --- |
| Switch port mirroring (SPAN) | The switch copies all frames of a source port to a destination port | Recommended: free, passive, network unaffected if the server fails. UniFi only supports 1:1 mirroring, so the uplink to the gateway would be mirrored |
| Hardware network TAP | Dedicated inline device | Most complete, but active taps for 1G+ are costly |
| Server as inline bridge | Server bridges two NICs between router and network | Sees everything, but becomes a single point of failure |
| Flow export (NetFlow/IPFIX) | Router exports connection metadata | Cheap, but no packet contents |

**How the server captures.** Three Linux capture paths were evaluated:

- **AF\_PACKET with TPACKET\_V3**: a memory-mapped ring buffer delivering packets in blocks. Handles 1 Gbit/s comfortably and is used automatically by libpcap.
- **AF\_XDP**: the most modern path, bypassing most of the network stack via an XDP/eBPF program. Reaches millions of packets per second, but adds operational complexity (driver support, XDP program lifecycle).
- **eBPF (e.g. with the Rust crate aya)**: useful later for in-kernel filtering or feature extraction.

**Decision.** At the link speeds of Ubiquiti equipment (1 to 10 Gbit/s), TPACKET\_V3 is not the bottleneck; disk and model are. The capture tool therefore used TPACKET\_V3 via the mature Rust `pcap` crate, in a design where the backend can later be swapped for AF\_XDP. The tool's drop counters were designed to show when that switch becomes necessary.

A practical constraint identified early: a full-duplex link can carry twice its nominal speed in total, so a mirror destination port of the same speed can drop copies under heavy load.

## 3. Phase 2: Building the Rust capture tool (tapcap)

A custom Rust program, `tapcap`, was written and tested before deployment; testing uncovered one real bug, which was fixed before the tool reached the server.

**Design.** The tool separates capturing from writing to disk:

1. A capture thread reads packets from the kernel ring buffer (promiscuous mode, full packets, 256 to 512 MB ring).
2. Packets pass through a bounded queue to a separate writer thread, so a slow disk causes counted drops instead of silent kernel overflows.
3. The writer saves rotating pcap files (every 60 s or 512 MB) into a `tmp/` folder.
4. Finished files are moved atomically into `ready/`, so the analysis model never reads a half-written file.
5. Every 10 s the tool logs three drop counters (kernel ring, NIC, queue) that show where tuning is needed.

It runs as a hardened systemd service (`tapcap@<interface>`): an unprivileged user with only the two capture capabilities, NIC offloads (GRO/LRO/TSO) disabled so captured frames match the wire, and automatic restart.

**Hiccup: the tool could not shut down on an idle link.** In the first test, the process ignored the stop signal (SIGTERM) and kept running. Investigation showed that on Linux with TPACKET\_V3, a blocking read can wait forever when no packets arrive, so the loop never checked the stop flag.

- First fix: switch the capture to non-blocking mode with a 1 ms back-off when the ring is empty. Shutdown then worked, but no packets were captured at all.
- Cause: removing the read timeout also removed the kernel's block-delivery timer, so filled blocks were never handed to the program.
- Final fix: non-blocking mode **plus** a 100 ms timeout. A re-test captured 600 of 600 test packets, rotated files every 2 s as configured, and shut down cleanly.

A minor test-environment issue (an old Rust toolchain that could not build the newest crate versions) was solved by pinning versions for the compile check only; the delivered code uses current versions.

## 4. Phase 3: Operating system and first network configuration

A planned fresh installation turned out to be unnecessary: the server (a Lenovo ThinkCentre, hostname thinkcentre720q) already ran Ubuntu 26.04.1 LTS, the current long-term release.

**Hiccup: no USB stick for installation.** The standard route (bootable USB stick) was not possible. Alternatives were evaluated: other USB storage, the server's remote management, network boot, moving the disk to another machine, and booting the installer ISO directly from the existing disk via GRUB. The GRUB route was prepared in detail, including the main risk: the installer wipes the disk that holds the ISO, which the `toram` boot option is meant to avoid by copying the installer into RAM.

**Resolution.** Before executing it, the installed version was checked with `lsb_release -a`. It reported Ubuntu 26.04.1 LTS, so the reinstall was cancelled and the existing system was used after a full update. This avoided the riskiest step of the whole project.

**Hiccup: missing configuration file.** The first network step referred to a configuration file (`60-capture.yaml`) that existed only as a download on the laptop, not on the server. From then on, all files were created directly on the server with shell heredocs, which proved more reliable than transferring files. The configuration was also made safer: it touched only the capture interface and inherited the system's existing network renderer.

**Hiccup: "Permission denied" when displaying the file.** Netplan requires configuration files to be readable only by root (`chmod 600`), so displaying it needed `sudo cat`. The file itself was correct.

## 5. Phase 4: Hardware reality check and architecture change

The planned mirroring design was abandoned once the Ubiquiti device was identified as a UniFi U7 Lite, which is a WiFi access point, not a router or switch.

**Hiccup: the "router" cannot mirror.** The U7 Lite has a single 2.5 GbE port that both connects it to the network and powers it via PoE. With one port it has nothing to mirror to, and UniFi access points offer no port mirroring. No switch was available. Fix: rather than mirror on a switch, the server was placed directly in the traffic path as the gateway (option B2 below), so all client traffic passes through it and is captured there.

Three options were assessed:

| Option | Description | Trade-off |
| --- | --- | --- |
| A: managed switch | Add a switch (e.g. a cheap TP-Link Easy Smart or a non-Flex UniFi model) and mirror the AP's port | Cheapest working mirror; server stays out of the critical path |
| B: server inline | Place the server between the internet uplink and the AP | No switch needed; server becomes a single point of failure |
| C: router mirroring | Mirror on the existing router | Usually unsupported |

**Decision: option B.** The goal was to deploy the server together with the access point as one unit, so that people connect to it and their internet traffic is recorded. This favoured the server sitting in the traffic path.

Option B was then split into two variants:

- **B1, transparent bridge:** the server only relays frames between two network cards; an existing router keeps handing out addresses and doing NAT.
- **B2, server as gateway:** the server itself hands out addresses (DHCP), translates to the internet (NAT) and resolves names (DNS).

**Hiccup: the uplink is WiFi.** The server's internet connection (`wlp2s0`) was a WiFi link to a phone hotspot (`172.20.10.x`), and its only wired port (`eno1`) was free. A WiFi client connection cannot be placed in a transparent bridge, so B1 was ruled out by the hardware. **B2 was chosen**: internet arrives over WiFi, clients leave through `eno1` to the access point, and all client traffic converges on `eno1`, the ideal capture point.

Two physical facts followed: the server cannot power the AP, so a PoE injector was required; and the phone hotspot limits the total bandwidth, which must be considered when interpreting results.

## 6. Phase 5: Building the gateway

The server was turned into a router in four configuration steps; the DNS/DHCP service needed four separate fixes before it ran.

**Configuration steps.**

1. **Network addressing (netplan):** `eno1` received the static address `10.42.0.1/24` as the gateway for clients; the WiFi uplink kept its existing configuration.
2. **IP forwarding:** enabled permanently via sysctl so the server routes packets between interfaces.
3. **Firewall and NAT (nftables):** default-deny for incoming traffic; clients may use DNS, DHCP, ping and SSH on the LAN side; forwarding only from LAN to WAN; masquerading (NAT) on the uplink. The uplink is treated as untrusted.
4. **DHCP and DNS (dnsmasq):** addresses `10.42.0.100` to `.200`, gateway and DNS server `10.42.0.1`, upstream resolvers Quad9 and Cloudflare.

Both configurations were syntax-checked (`nft -c`, `dnsmasq --test`) before being handed over.

**Hiccup 1: dnsmasq not installed.** Enabling the service failed with "Unit dnsmasq.service does not exist". The package had not been installed; `apt install dnsmasq` fixed it.

**Hiccup 2: dnsmasq exited with status 2.** The generic systemd log did not show the cause. Checking the interface showed `eno1` had no IPv4 address at all, so dnsmasq could not bind to `10.42.0.1`.

- Two other netplan files were suspected of overriding the configuration. Reading them showed they configured other interfaces (`wlp2s0` and `enp1s0f0`) and did not conflict.
- `networkctl status eno1` revealed the real cause: state `no-carrier (configuring)`. With no cable plugged in, systemd-networkd held back the whole configuration, including the static address.
- Fix: the netplan option `ignore-carrier: true` (verified to generate `ConfigureWithoutCarrier=yes`). The address then appeared even without a cable, and it was kept so the gateway comes up cleanly on boot.

**Hiccup 3: port 53 already in use.** dnsmasq still failed. Running `dnsmasq --test` showed the configuration was valid, so the failure was at runtime. The service's own log lines finally stated "failed to create listening socket for port 53: Address already in use", and `ss` showed Ubuntu's `systemd-resolved` holding the port with its DNS stub listener. Fix: `DNSStubListener=no` in `/etc/systemd/resolved.conf`, which frees port 53 while systemd-resolved keeps running as the backing resolver. dnsmasq then started.

**Hiccup 4: dnsmasq ran but served no DHCP.** This only surfaced in the next phase, when the access point received no address (see Phase 6).

A side finding was also recorded: the installer's network file for the WiFi uplink contains two contradictory `dhcp4` lines. It was deliberately left unchanged, because editing it over a session that depends on that link risks losing access.

## 7. Phase 6: UniFi controller and access point adoption

The access point was adopted and broadcasting a test SSID after three problems were solved: missing DHCP configuration, remote access over the hotspot, and rootless container networking.

**Why a controller was needed.** A UniFi access point has no standalone configuration interface; a UniFi controller must adopt it and push the WiFi settings. Without a UniFi console, the controller had to run on the server itself, which also sits on the AP's subnet. Research showed that Ubiquiti announced in September 2026 that UniFi Network 10.6 is the last release of the standalone Network application, so the successor, **UniFi OS Server**, was used (it runs in a Podman container). The server's architecture was checked with `uname -m` to choose the right x64 build, and the installer file was downloaded and placed on the server.

**Hiccup: SSH from the laptop failed.** The laptop on the same hotspot could ping the hotspot gateway but not the server. Two causes were identified: the nftables policy dropped all new incoming traffic on the WiFi uplink (by design), and phone hotspots may isolate their clients from each other. Rules allowing SSH and ping on the uplink were added for the setup period.

**Hiccup: the AP did not appear for adoption, and no DHCP lease file existed.** A missing lease file meant dnsmasq had never handed out an address, so the AP had no IP and could not reach the controller. The dnsmasq startup log contained no "DHCP, IP range" line, confirming DHCP was inactive. Two stacked causes were found:

- The `conf-dir` line that loads files from `/etc/dnsmasq.d/` was not active in `/etc/dnsmasq.conf`, so drop-in files were ignored. It was appended.
- The drop-in file `tapgw.conf` did not exist at all; the directory contained only a README. The earlier creation step had not landed. Recreating the file finally produced the "DHCP, IP range 10.42.0.100 -- 10.42.0.200" log line, and the AP received a lease.

**Hiccup: adoption request sent, but the AP never adopted.** Manual adoption over SSH (`set-inform http://10.42.0.1:8080/inform`) reported "adoption request sent", but provisioning stalled, and a test request from the AP to port 8080 hung.

- Ports 8080 and 11443 were owned by `pasta`, Podman's rootless networking helper, because the controller had been installed under the normal user account.
- Opening the UniFi ports (8080, 8443, 11443, 3478, 10001) in the firewall did not help, which ruled out the firewall.
- Conclusion: rootless container networking breaks the bidirectional connection between AP and controller that adoption requires. It would also stop the controller when the user logs out.
- Recommended fix: reinstall UniFi OS Server with root privileges, so its ports bind directly on the host.

After this the AP was adopted, the SSID was created in the controller, and a test device connected and had internet access through the server.

## 8. Phase 7: Deploying packet capture and verification

Full packet capture ran on `eno1` with zero drops, and the recorded files contained the real client addresses, confirming per-client attribution.

**Hiccup: the project was not on the server.** Building failed because the `tapcap` source and service files existed only as downloads on the laptop. All files (Cargo manifest, source code, systemd service, directory rules) were recreated on the server with heredocs, then built with `cargo build --release` and installed to `/usr/local/bin`. The `libpcap-dev` package was installed for the build.

**Result.** The service `tapcap@eno1` started and logged its first statistics: 26 packets seen, and 0 drops in the kernel ring, the NIC and the queue. After about a minute, the first files rotated into `/var/lib/tapcap/ready/` (3.3 MB and 15 MB).

**Hiccup: the files could not be read.** Inspecting the newest file failed with "Permission denied" and "No such file or directory". The directory is readable only by the `tapcap` service user. In the command `sudo tcpdump -r "$(ls …)"`, only the outer command ran with root rights; the inner `ls` ran as the normal user, so the wildcard never expanded. Running the whole pipeline as root (`sudo bash -c '…'`) solved it.

**Verification.** The decoded capture showed:

- The test device's own address (`10.42.0.184`), captured before NAT. Capturing on the uplink would have shown only the server's single hotspot address.
- Outbound internet traffic, e.g. a time synchronisation (NTP) to an external server.
- Complete protocol detail: Ethernet, IP, TCP flags, ports and HTTP methods.
- Background traffic between the AP and the controller (port 8080), which can be filtered out later if it disturbs the analysis.

## 9. Phase 8: Metadata extraction and unified feed

A second service, `tapfeed`, writes one JSON line per event to `/var/lib/tapcap/meta/feed.ndjson`, combining DNS queries, TLS SNI, QUIC SNI and device hostnames per client, with no automatic deletion.

**Motivation.** The question "which domain belongs to IP 91.214.191.135?" showed the limits of reverse DNS: it returns the IP owner's infrastructure name, not the site a user requested. The reliable sources are the client's own name lookups and the hostname clients announce when opening encrypted connections.

**Signals collected.**

| Signal | Source | What it reveals |
| --- | --- | --- |
| DNS queries | dnsmasq query log (the server is every client's resolver) | Every domain a client looks up |
| TLS SNI | TLS ClientHello, sent in cleartext | Domain of each HTTPS connection |
| QUIC / HTTP/3 SNI | QUIC Initial packets, decryptable with public keys defined in RFC 9001; tshark 4.x decodes them automatically | Domain of each HTTP/3 connection |
| Hostnames | DHCP option 12 and mDNS announcements | Device names for attribution |

The extraction filter was first tested on a crafted test capture, which correctly yielded a TLS SNI (`example.com`), a DHCP hostname and an mDNS name.

**Design.** One script runs tshark for SNI and hostnames and follows dnsmasq's journal for DNS queries, normalising both into the same record: timestamp, client IP, MAC address, type (`dns`, `sni`, `hostname`) and value. It runs as a dedicated service user.

**Hiccups and fixes.**

- The first service file again existed only on the laptop; the unified script and service were created directly on the server instead.
- The service crashed in a loop with "mkdir: Permission denied". Changing the ownership of the `meta` folder did not help. The directory listing revealed the real cause: the parent folder `/var/lib/tapcap` (mode 750, owned by `tapcap`) could not be traversed by the `tapmeta` user. Fix: add `tapmeta` to the `tapcap` group.
- A `sed` command to make the script tolerant of the `mkdir` failure broke because its replacement text contained the `|` character used as delimiter; switching the delimiter to `#` fixed it.
- A direct write test as the service user failed with "This account is currently not available", because service accounts have no login shell. The running service itself served as the proof instead.
- After a restart throttle ("Start request repeated too quickly") was cleared with `systemctl reset-failed`, the service ran.

**Result.** The feed showed DNS and SNI events correlating per client, e.g. a DNS lookup for an Apple push server followed within a second by a TLS connection to it. Hostname events were initially missing because DHCP hostnames are only sent when a device joins or renews its lease; after reconnecting the test device, they appeared.

## 10. Phase 9: Persistence and reboot test

The system passed a full reboot test: all four services (`tapcap@eno1`, `tapfeed@eno1`, `dnsmasq`, `nftables`) came back active on their own, and all firewall rules survived.

**Risk addressed.** Several firewall rules had been added live during debugging (uplink SSH and ping, UniFi adoption ports). Rules added with `nft add` are lost on reboot, which would have silently disconnected the AP after the next restart.

**Fix.** All rules were consolidated into one syntax-checked `/etc/nftables.conf`, loaded at boot. It also added a small hardening (`ct state invalid drop`) and the remaining UniFi ports (8880, 8843). The uplink SSH rule was kept for administration but marked to be disabled once the box is managed only from the LAN side.

**Verification.** After `sudo reboot`, `systemctl is-active` reported all four services as active, and the UniFi port rule was present in the live ruleset.

## 11. Open issue: the iPhone's full device name

The feed records the test iPhone only as `iPhone`, not as its user-visible name "iPhone von Thierry"; this remains unresolved.

**Investigation so far.**

- DHCP hostnames are sanitised by iOS, which drops spaces and often shortens the name.
- A verbose mDNS capture showed only **queries** from the iPhone, asking for generic services such as AirPlay and companion-link. Queries never contain the device's own name.
- A capture filtered to mDNS **responses**, where a device would announce its own name, returned nothing, even when the test was repeated.

**Likely explanation.** Recent iOS versions deliberately limit self-identifying announcements on networks they do not trust (private Wi-Fi addresses, limited tracking), so the full name probably never reaches the wire. No passive capture can retrieve data the device does not send.

**Proposed solution.** Use the MAC address, which appears in SNI events and DHCP leases, as the stable identifier, and keep a small mapping file (MAC to a friendly name such as "Thierry's iPhone") that the analysis model reads. For informed test users this is more reliable than mDNS scraping. One caveat: private Wi-Fi addresses can rotate, so the mapping should be checked per test session.

## 12. Overview of problems and solutions

Seventeen problems were encountered and sixteen were solved; the iPhone's full name remains open.

| # | Phase | Problem | Root cause | Solution |
| --- | --- | --- | --- | --- |
| 1 | Capture tool | Process ignored shutdown signal | Blocking read never returns on an idle link | Non-blocking mode with back-off |
| 2 | Capture tool | No packets after first fix | Read timeout also drives kernel block delivery | Non-blocking mode plus 100 ms timeout |
| 3 | OS | No USB stick for installation | Hardware unavailable | Checked version; existing Ubuntu 26.04.1 LTS kept |
| 4 | OS | Config file missing on server | Files only downloaded to the laptop | Create files on the server with heredocs |
| 5 | OS | Permission denied reading config | Netplan files are root-only (600) | Read with `sudo` |
| 6 | Hardware | "Router" cannot mirror | U7 Lite is a single-port access point | Server as inline gateway (B2) |
| 7 | Hardware | Transparent bridge impossible | Uplink is WiFi | Routing gateway with NAT instead of bridge |
| 8 | Gateway | dnsmasq unit missing | Package not installed | `apt install dnsmasq` |
| 9 | Gateway | dnsmasq exit status 2 | No IP on `eno1` while cable unplugged | `ignore-carrier: true` |
| 10 | Gateway | Port 53 in use | systemd-resolved stub listener | `DNSStubListener=no` |
| 11 | Adoption | No SSH from laptop | Uplink firewall policy, hotspot isolation | Temporary uplink rules |
| 12 | Adoption | AP got no IP | `conf-dir` inactive and `tapgw.conf` missing | Enable `conf-dir`, recreate file |
| 13 | Adoption | AP never adopted | Rootless Podman networking (`pasta`) | Root installation of UniFi OS Server |
| 14 | Capture | Could not read capture files | Inner command ran without root rights | `sudo bash -c` for the whole pipeline |
| 15 | Feed | Service crash loop, mkdir denied | Parent folder not traversable by `tapmeta` | Add `tapmeta` to `tapcap` group |
| 16 | Persistence | Live firewall rules lost on reboot | `nft add` is not persistent | Consolidated `/etc/nftables.conf` |
| 17 | Feed | Full iPhone name missing | iOS likely withholds the name | Open; MAC-to-name mapping proposed |

## 13. Final architecture, limitations and lessons learned

The finished system is a self-contained, reboot-proof capture gateway; its data flow is shown below, followed by its limitations, the lessons learned and the next steps.

&#91;embedded content: data flow · internet → server → access point, with two capture outputs\]

**Limitations.**

- The internet uplink is a phone hotspot, which caps total bandwidth and makes the setup suitable for testing rather than production. A wired uplink (e.g. a USB 2.5G Ethernet adapter) would remove this.
- WiFi traffic between two clients on the same access point is forwarded inside the AP and never reaches the server, so it is not captured. Traffic to the internet or to wired devices is fully captured.
- Connection contents are encrypted and are not decrypted; only metadata (domains, hostnames, flow data) is extracted. Reading contents would require a TLS man-in-the-middle with a certificate installed on each device.
- Encrypted DNS (DoH/DoT) bypasses the server's resolver, and the emerging ECH standard hides the SNI; both reduce domain visibility where used.
- Nothing is deleted automatically (by request), so disk usage must be monitored.

**Lessons learned.**

- Identify the hardware precisely before designing: mistaking the access point for a router would have wasted significant effort, and the single-WiFi-uplink constraint reshaped the whole architecture.
- Create configuration files directly on the target machine; relying on downloads caused repeated "file not found" delays.
- Read the service's own log lines, not just the generic systemd message; the real causes (port 53 in use, no carrier, missing DHCP range) were only visible there.
- Many failures were permission and path issues (directory traversal, root-only files, shell quoting) rather than conceptual errors.
- Test tools before deployment: the capture tool's shutdown bug was found and fixed in a controlled test, not in production.

**Next steps.**

- Connect the existing analysis model to the two outputs (`ready/` pcaps and `feed.ndjson`), e.g. via a small file-watcher.
- Optionally add Zeek to turn pcaps into rich structured logs (certificates, JA3/JA4 fingerprints, full connection records), and GeoIP/ASN enrichment on destination addresses.
- Resolve the device-name mapping (Section 11) and disable uplink SSH once LAN-side administration is available.

## 14. Appendix: terminal commands used

This appendix lists the concrete commands run on the server (user `kathy`), grouped by task, in the order they were used. The full bodies of the two long files (the nftables ruleset and the `tapfeed` script) live in the deploy files and are referenced rather than repeated here.

**Base system: check and update**

```bash
lsb_release -a                         # confirm Ubuntu 26.04.1 LTS
systemctl get-default                  # server vs desktop target
sudo apt update && sudo apt full-upgrade -y
df -h /
systemctl is-active ssh
ip -br addr                            # interface names and IPs
ip -br link
```

**WiFi uplink to the internet (phone hotspot "Karla")**

The internet side runs over WiFi to a phone hotspot named "Karla". It was configured during the Ubuntu installation and lives in `/etc/netplan/00-installer-config.yaml`:

```yaml
network:
  version: 2
  wifis:
    wlp2s0:
      dhcp4: false
      addresses:
        - 172.20.10.10/28
      routes:
        - to: default
          via: 172.20.10.1
      nameservers:
        addresses: [172.20.10.1, 8.8.8.8]
      access-points:
        "Karla":
          password: "<hotspot-password>"
```

Apply after editing, and confirm the uplink is up:

```bash
sudo netplan apply
ip -br addr show wlp2s0                  # expect 172.20.10.10/28, state UP
ping -c2 8.8.8.8                         # confirm internet over the hotspot
```

Note: the Wi-Fi password is redacted here; the real one goes in the file. The installer-written file also held a duplicate `dhcp4` line (both `false` and `true`), left unchanged because editing it over the live uplink risked losing the connection (see Section 6).

**LAN interface (netplan)**

```bash
sudo tee /etc/netplan/60-tapgw.yaml > /dev/null <<'EOF'
network:
  version: 2
  ethernets:
    eno1:
      dhcp4: false
      dhcp6: false
      accept-ra: false
      addresses: [10.42.0.1/24]
      ignore-carrier: true
      optional: true
EOF
sudo chmod 600 /etc/netplan/60-tapgw.yaml
sudo netplan apply
ip -br addr show eno1                   # expect 10.42.0.1/24
networkctl status eno1                  # diagnosed the "no-carrier" state
```

**IP forwarding**

```bash
echo 'net.ipv4.ip_forward=1' | sudo tee /etc/sysctl.d/99-tapgw.conf
sudo sysctl --system | grep ip_forward
```

**Firewall and NAT (nftables)**

```bash
# full ruleset written to /etc/nftables.conf (see deploy files)
sudo nft -c -f /etc/nftables.conf       # syntax check
sudo systemctl enable nftables
sudo systemctl restart nftables
sudo nft list ruleset | grep -E '8080|8443|11443|dport 22'

# rules added live during debugging, later folded into /etc/nftables.conf:
sudo nft add rule inet filter input iifname "wlp2s0" tcp dport 22 ct state new accept
sudo nft add rule inet filter input iifname "wlp2s0" icmp type echo-request accept
sudo nft add rule inet filter input iifname "eno1" tcp dport { 8080, 8443, 11443 } accept
sudo nft add rule inet filter input iifname "eno1" udp dport { 3478, 10001 } accept
```

**DHCP and DNS (dnsmasq)**

```bash
sudo apt update && sudo apt install -y dnsmasq

sudo tee /etc/dnsmasq.d/tapgw.conf > /dev/null <<'EOF'
interface=eno1
bind-interfaces
except-interface=lo
dhcp-range=10.42.0.100,10.42.0.200,255.255.255.0,12h
dhcp-option=option:router,10.42.0.1
dhcp-option=option:dns-server,10.42.0.1
no-resolv
server=9.9.9.9
server=1.1.1.1
domain-needed
bogus-priv
dhcp-authoritative
log-dhcp
EOF

echo 'conf-dir=/etc/dnsmasq.d/,.bak' | sudo tee -a /etc/dnsmasq.conf   # load drop-ins
sudo sed -i 's/^#\?DNSStubListener=.*/DNSStubListener=no/' /etc/systemd/resolved.conf
sudo systemctl restart systemd-resolved
sudo systemctl enable --now dnsmasq
sudo systemctl restart dnsmasq

# diagnostics:
dnsmasq --test
sudo ss -ulpn 'sport = :53'
sudo journalctl -u dnsmasq -f
cat /var/lib/misc/dnsmasq.leases
```

**Mirror / capture-NIC check**

```bash
sudo ip link set eno1 up promisc on
sudo tcpdump -i eno1 -nn -e -c 30
```

**UniFi OS Server and AP adoption**

```bash
uname -m                                # confirm x86_64 build
sudo apt install -y podman uidmap curl
chmod +x ~/unifi-os-server.bin
sudo ~/unifi-os-server.bin              # root install (rootless broke adoption)
sudo ss -tlpn | grep -E '8080|11443'
sudo podman ps

# reach the controller UI from the laptop over the hotspot:
ssh -L 11443:localhost:11443 kathy@172.20.10.10   # then browse https://localhost:11443

# manual adoption, run on the access point:
ssh ubnt@<ap-ip>                        # ap-ip from dnsmasq.leases
curl -k http://10.42.0.1:8080/inform    # reachability test
set-inform http://10.42.0.1:8080/inform
```

**Rust capture tool (tapcap)**

```bash
curl --proto '=https' --tlsv1.2 -sSf https://sh.rustup.rs | sh
source ~/.cargo/env
sudo apt install -y build-essential pkg-config libpcap-dev

cd ~/tapcap
cargo build --release
sudo install -m 755 target/release/tapcap /usr/local/bin/
tapcap --help

sudo useradd --system --no-create-home --shell /usr/sbin/nologin tapcap
sudo cp deploy/tapcap.tmpfiles.conf /etc/tmpfiles.d/tapcap.conf
sudo systemd-tmpfiles --create
sudo cp deploy/tapcap@.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now tapcap@eno1
journalctl -u tapcap@eno1 -f
```

**Capture verification**

```bash
sudo ls -lh /var/lib/tapcap/tmp/ /var/lib/tapcap/ready/
sudo bash -c 'tcpdump -nn -r "$(ls -t /var/lib/tapcap/ready/*.pcap | head -1)" | head -20'
```

**Unified metadata feed (tapfeed)**

```bash
echo 'log-queries' | sudo tee /etc/dnsmasq.d/querylog.conf
sudo systemctl restart dnsmasq

sudo apt install -y tshark               # answer "No" to the non-root capture prompt
sudo groupadd -f wireshark
sudo useradd --system --no-create-home --shell /usr/sbin/nologin tapmeta
sudo usermod -aG wireshark,adm,systemd-journal tapmeta
sudo usermod -aG tapcap tapmeta          # fix: allow directory traversal
sudo chgrp wireshark /usr/bin/dumpcap && sudo chmod 750 /usr/bin/dumpcap
sudo setcap cap_net_raw,cap_net_admin+eip /usr/bin/dumpcap
sudo install -d -o tapmeta -g tapmeta /var/lib/tapcap/meta

# /usr/local/bin/tapfeed and /etc/systemd/system/tapfeed@.service created via heredoc
sudo chmod +x /usr/local/bin/tapfeed
sudo systemctl daemon-reload
sudo systemctl reset-failed tapfeed@eno1
sudo systemctl enable --now tapfeed@eno1
tail -f /var/lib/tapcap/meta/feed.ndjson
```

**Reboot / persistence test**

```bash
sudo reboot
systemctl is-active tapcap@eno1 tapfeed@eno1 dnsmasq nftables
sudo nft list ruleset | grep 8080
```

**Device-name investigation**

```bash
sudo tshark -i eno1 -n -Y 'mdns' -V 2>/dev/null | grep -iE 'name|iphone' | head -40
sudo tshark -i eno1 -n -Y 'mdns && dns.flags.response == 1' -T fields -e ip.src -e dns.a -e dns.resp.name -e dns.srv.target
```
