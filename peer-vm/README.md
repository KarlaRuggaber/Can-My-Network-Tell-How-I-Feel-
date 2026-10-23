# peer-vm

Counterpart for the traffic runner's calls and games. A small VM **outside the home network**, so that call media and game traffic of the simulated devices flow through the gateway in both directions (activity catalog §2: "call … against a counterpart outside the home network").

```
gateway (br-sim)                               VM, e.g. 203-0-113-7.sslip.io
 runner container ──HTTPS 443──► Caddy (Let's Encrypt) ──► Jitsi web / prosody / jicofo
   video_call / voice_call ──UDP 10000───────────────────► Jitsi videobridge (media)
   gaming_session ──WSS 443 (20–60 msg/s each way)───────► peer: game server
   └ "join room X for N s" (HTTPS + token) ──────────────► peer: call API
                                                           peer: headless Chromium with fake
                                                           camera/mic joins room X
```

| Part | What it does |
|---|---|
| Jitsi (self-hosted) | Video conferencing server, no login. `jitsi-compose.yml` is the official compose file of docker-jitsi-meet `stable-11248`, unmodified ([JITSI_ORIGIN.md](JITSI_ORIGIN.md)). Settings are in `.env` (see below) |
| Caddy | Only public entry point (80/443). Automatic Let's Encrypt certificate for `<ip-with-dashes>.sslip.io`, which resolves to the VM's IP without registering a domain |
| `slackbot` | Reply bot "CMNTHIF Partner" for the runner's `messaging` (official Slack app, Socket Mode, outbound only). Answers every direct message after 5–40 s. Runs in the host network, because it needs internet; its traffic is therefore never recorded as a device. Tokens `SLACK_APP_TOKEN` / `SLACK_BOT_TOKEN` in `.env`; without them it idles |
| `peer` | One Python service (`peer/peer_service.py`). `POST /peer/join` (bearer token) lets a headless Chromium with fake camera/mic join a room for the call's duration. It leaves early once it has been alone in the room for 45 s, judged by Jitsi's participant count. Before 23.10 the rule was "no media for 45 s", which also fired on a muted runner without camera (`--mic-share`). `GET /game` + `/game/ws` is a toy multiplayer game: the client sends inputs and the server sends game states, 20–60 times per second each |

**Settings that keep a call on this VM** (generated into `.env` by `setup.sh`):

| Setting | Effect |
|---|---|
| `ENABLE_P2P=false` | Media always goes through our videobridge, never peer-to-peer |
| `JVB_DISABLE_STUN=true` + `JVB_ADVERTISE_IPS=<ip>` | The bridge does not ask external STUN servers |
| Opus DTX (in the call URL of runner and peer, no server setting exists) | A muted microphone sends ~5 instead of 50 packets/s |
| `ENABLE_PREJOIN_PAGE=false` | Server-side. Turning the prejoin page off *in the URL* makes Jitsi join without camera and microphone, as a safeguard against manipulated links (found while testing) |

Checked in the net-log: during a call, the runner's browser contacts only the VM.

## Gateway mode: on the mini-PC instead of a VM (decided 23.10)

The same stack also runs on the gateway itself, next to the runner. That uses no extra hardware, runs unattended, and costs no hotspot volume for media.

```
runner container ── br-sim ── gateway routing ── br-peer (10.43.0.0/24) ── Caddy 10.43.0.10, videobridge 10.43.0.13
   10.42.1.11          ▲ tapcap@br-sim records here (device IP)          peer.sim via dnsmasq
```

`gateway-compose.yml` is added as a third compose file (`./setup.sh --gateway`):

| Setting | Why |
|---|---|
| **No published host ports** | 8080/8443 belong to the UniFi controller. The runner reaches the stack only through the gateway's routing, which nftables limits to 443/tcp (Caddy) and 10000/udp (videobridge) |
| **Own addresses on `br-peer`, never the gateway's** | The ingest filter drops traffic to the gateway's own IPs (10.42.0.1, 10.42.1.1) except DNS. Traffic to 10.43.0.x is kept |
| **`gw_priority` on `br-peer`** | Caddy and the videobridge send their replies back through `br-peer` |
| **Fixed subnet 10.43.1.0/24 for Jitsi's internal network** | Docker never picks 172.20.0.0/16, which overlaps the hotspot |
| **Memory caps** | videobridge 1 GB, jicofo 512 MB, peer 2 GB, for the 7 GB mini-PC |
| **`peer.sim` with Caddy's internal CA** | The runner sets `RUNNER_PEER_INSECURE_TLS=1` |

**Difference to a cloud VM.** The call partner has a private address (10.43.0.x) and the media does not cross the hotspot uplink. For the capture on `br-sim` and the metrics this makes no difference: the call host was in no thesis list anyway (like jit.si). Document it as a modelling difference.

The gateway changes are in [`gateway/`](gateway/) and described step by step in the runner README §7.

## Setting up the VM

**Requirements**
- Ubuntu VM with 2 vCPU, 4 GB RAM and 20 GB disk, e.g. SWITCHengines, Exoscale or Hetzner (about 5–10 €/month)
- A public IPv4 address
- Inbound ports open in the provider's firewall:
  - **80/tcp** (Let's Encrypt)
  - **443/tcp** (web, API, game)
  - **10000/udp** (call media)

```bash
# on the VM (Docker from the official repository, see Docker's install guide), then:
git clone https://github.com/KarlaRuggaber/Can-My-Network-Tell-How-I-Feel-.git can-my-network
cd can-my-network/peer-vm
./setup.sh <public-ip>              # writes .env with secrets, prints the gateway settings
sudo docker compose up -d --build
curl -s https://<ip-with-dashes>.sslip.io/peer/health     # {"calls": 0}
```

`setup.sh` prints two lines for the gateway. Put them into `/opt/can-my-network/traffic-runner/peer.env`, a root-owned file with mode 600 that is not in git:

```bash
sudo install -m 600 /dev/null /opt/can-my-network/traffic-runner/peer.env
sudo nano /opt/can-my-network/traffic-runner/peer.env   # RUNNER_PEER_URL=… and RUNNER_PEER_TOKEN=…
sudo /opt/can-my-network/traffic-runner/scripts/deploy.sh
```

Without `peer.env`, `video_call`, `voice_call` and `gaming_session` log `not_implemented`.

## Local test (laptop)

```bash
./setup.sh --local                  # DOMAIN=peer.test, Caddy's internal CA
docker compose up -d --build
# runner container in the same Docker network:
docker run --rm --shm-size 1g --network peer-vm_meet.jitsi \
  -e RUNNER_PEER_URL=https://peer.test -e RUNNER_PEER_TOKEN=<PEER_TOKEN from .env> -e RUNNER_PEER_INSECURE_TLS=1 \
  traffic-runner:0.1.0 python3 -m runner run --device student_a_laptop --activity video_call \
  --duration 2m --seed 1 --profile test --block-id local1
docker compose down                 # when done
```

## Measured (laptop, 23.10.2026)

| Run | Up | Down | Notes |
|---|---|---|---|
| `video_call`, 2 min | 13 MB | 9.4 MB | ≈ 0.9 Mbit/s up, upload-heavy. The download includes ~2 MB for loading the Jitsi page |
| `voice_call`, 90 s | 0.5 MB | 2.5 MB | ≈ 40 kbit/s audio plus the page |
| `gaming_session` game phase | ≈ 50 kbit/s | ≈ 60 kbit/s | many small packets in both directions; the store pages before it dominate the volume |

Roughly 1 h of video call ≈ 0.6 GB up + 0.4 GB down through the hotspot.

## Security and limits

- **Join API:** needs the bearer token. Room names are an HMAC of the run (`profile/seed/block_id`) with the token, so they cannot be guessed.
- **Limits:** at most 3 calls at a time and 4 h per call.
- **Game page:** public, but it only exchanges toy game states. It can be abused at most as a small echo service.
- **Secrets:** `.env` holds the Jitsi passwords and the token. Mode 600, never committed (`.gitignore`).
