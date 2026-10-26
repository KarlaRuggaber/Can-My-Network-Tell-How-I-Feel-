"""Command line: python -m runner {run,validate,list,background}."""

from __future__ import annotations

import argparse
import logging
import os
import random
import re
import signal
import socket
import sys
import time

from . import background, config, discord, gtlog, sessions, steps
from .activities import ACTIVITIES, CATALOG_ONLY
from .context import NotImplementedActivity, PageError, RealClock, RunContext
from .steps import Aborted  # noqa: F401 - part of the CLI's interface

log = logging.getLogger("runner")

EXIT_OK, EXIT_ERROR, EXIT_USAGE, EXIT_NOT_IMPLEMENTED = 0, 1, 2, 3
STATUS_EXIT = {"ok": EXIT_OK, "error": EXIT_ERROR, "not_implemented": EXIT_NOT_IMPLEMENTED}
WATCHDOG_GRACE = 90  # seconds past the deadline before the run is aborted hard
CLOSE_TIMEOUT = 60   # seconds for closing the browser after the log row is written
GATEWAY = "10.42.1.1"

_DURATION_RE = re.compile(r"^(\d+(?:\.\d+)?)(s|m|h)?$")


class UsageError(Exception):
    pass


DRY_RUN_WEBHOOK = "https://discord.com/api/webhooks/100000000000000001/dry-run-token-not-a-secret"
DRY_RUN_CHANNEL = "200000000000000002"

def parse_duration(text: str) -> float:
    """'300', '90s', '5m', '2h' -> seconds."""
    m = _DURATION_RE.match(text.strip())
    if not m:
        raise UsageError(f"bad duration '{text}' (use e.g. 300, 90s, 5m, 2h)")
    return float(m.group(1)) * {"s": 1, None: 1, "m": 60, "h": 3600}[m.group(2)]


def parse_range(text: str, integer: bool = False) -> tuple[float, float]:
    """'20-90' or '1m-3m' -> (lo, hi)."""
    lo, sep, hi = text.partition("-")
    if not sep:
        lo = hi = text
    if integer:
        try:
            a, b = int(lo), int(hi)
        except ValueError:
            raise UsageError(f"bad range '{text}' (use e.g. 1-3)") from None
    else:
        a, b = parse_duration(lo), parse_duration(hi)
    if a <= 0 or a > b:
        raise UsageError(f"bad range '{text}'")
    return a, b


def parse_share(text: str) -> float:
    """'0.1' or '10%' -> 0.1, must be in (0, 1]."""
    t = text.strip()
    try:
        value = float(t[:-1]) / 100 if t.endswith("%") else float(t)
    except ValueError:
        raise UsageError(f"bad share '{text}' (use e.g. 0.1 or 10%)") from None
    if not 0 < value <= 1:
        raise UsageError(f"share must be > 0 and <= 1, got '{text}'")
    return value


def container_source_ip() -> str | None:
    """Source IP this container uses towards the gateway (no packet is sent)."""
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
            s.connect((GATEWAY, 53))
            return s.getsockname()[0]
    except OSError:
        return None


# --- run -----------------------------------------------------------------------------------

def cmd_run(args) -> int:
    try:
        devices = config.load_devices()
        roles = config.load_roles()
        mixes = config.load_mixes()
    except config.ConfigError as e:
        log.error("configuration invalid:\n%s", e)
        return EXIT_USAGE

    env_device = os.environ.get("RUNNER_DEVICE")
    device_name = args.device or env_device
    if not device_name:
        raise UsageError("--device is required (or set RUNNER_DEVICE)")
    if env_device and device_name != env_device:
        raise UsageError(f"this container is '{env_device}', refusing to run as '{device_name}'")
    if device_name not in devices:
        raise UsageError(f"unknown device '{device_name}' (see config/devices.csv)")
    device = devices[device_name]
    if os.environ.get("RUNNER_STRICT_IP") == "1" and not args.dry_run:
        ip = container_source_ip()
        if ip != device.ip:
            raise UsageError(f"container IP is {ip}, devices.csv says {device.ip} for {device.name}")

    activity_id = args.activity
    module = ACTIVITIES.get(activity_id)
    if module is None and activity_id not in CATALOG_ONLY:
        raise UsageError(f"unknown activity '{activity_id}' (see: python -m runner list)")
    implemented = module is not None and module.IMPLEMENTED
    if module is not None and device.role not in module.ROLES:
        log.warning("catalog intends %s for %s, running it on a %s", activity_id, "/".join(module.ROLES), device.role)

    rng = random.Random(f"{args.seed}/{args.block_id}")

    # Duration: given, or drawn from the catalog default, or required ("as block").
    if args.duration:
        duration = parse_duration(args.duration)
        default = module.DEFAULT_DURATION if module else None
        if default and not default[0] <= duration <= default[1]:
            log.warning("duration %.0f s is outside the catalog default %d-%d s for %s",
                        duration, default[0], default[1], activity_id)
    elif implemented and module.DEFAULT_DURATION:
        duration = float(rng.randint(*module.DEFAULT_DURATION))
    elif implemented:
        raise UsageError(f"{activity_id} runs 'as block': --duration is required")
    else:
        duration = 0.0
    if duration <= 0 and implemented:
        raise UsageError("--duration must be > 0")

    overrides = {}
    if args.pages:
        overrides["pages"] = parse_range(args.pages, integer=True)
    if args.dwell:
        overrides["dwell"] = parse_range(args.dwell)
    if args.lookups:
        overrides["lookups"] = parse_range(args.lookups, integer=True)
    if args.mic_share:
        overrides["mic_share"] = parse_share(args.mic_share)
        if activity_id not in ("video_call", "voice_call"):
            log.warning("--mic-share only affects video_call and voice_call")

    mix = None
    status = None
    if implemented and module.NEEDS_MIX:
        spec = args.mix or module.DEFAULT_MIX
        if not spec:
            raise UsageError(f"{activity_id} needs --mix (categories: {', '.join(mixes.categories)})")
        try:
            mix = config.parse_mix(spec, mixes, kind=module.MIX_KIND)
        except config.ConfigError as e:
            raise UsageError(str(e)) from None
        except config.MixUnavailable as e:
            log.warning("%s", e)
            status = "not_implemented"
        else:
            if mix.skipped:
                log.warning("skipped mix categories without usable sites (login needed): %s", ", ".join(mix.skipped))

    # Test-account activities: the device's login session (not_implemented if not captured).
    session_platform = getattr(module, "SESSION_PLATFORM", None) if implemented else None
    storage_state, session_meta = None, {}
    if session_platform and status is None:
        if args.dry_run:
            session_meta = {"dm_url": "https://app.slack.com/client/TDRYRUN/DDRYRUN"}
        else:
            try:
                state_path, session_meta = sessions.load(device.name, session_platform)
                storage_state = str(state_path)
            except NotImplementedActivity as e:
                log.warning("%s", e)
                status = "not_implemented"

    # social_post: the Discord webhook (not_implemented while the server is not set up).
    webhook_platform = getattr(module, "WEBHOOK_PLATFORM", None) if implemented else None
    accounts = config.load_accounts() if (session_platform or webhook_platform) else {}
    webhook_url = ""
    if webhook_platform and status is None:
        if args.dry_run:
            webhook_url = DRY_RUN_WEBHOOK
            accounts = {**accounts, "discord": {"webhook_id": DRY_RUN_WEBHOOK.split("/")[-2],
                                                "channel_id": DRY_RUN_CHANNEL}}
        else:
            try:
                webhook_url = discord.load_webhook(accounts.get("discord") or {})
            except NotImplementedActivity as e:
                log.warning("%s", e)
                status = "not_implemented"
            except PageError as e:
                log.error("%s", e)
                status = "error"

    if args.dry_run:
        from .fake import FakeClock, FakeDriver
        clock = FakeClock()
        driver = FakeDriver(clock)
        driver.webhook_channel_id = DRY_RUN_CHANNEL
    else:
        from .browser import BrowserDriver
        role_cfg = roles[device.role]
        clock = RealClock()
        # An activity may need another browser profile than the role (Slack refuses phones).
        browser_device = getattr(module, "PLAYWRIGHT_DEVICE", None) or role_cfg["playwright_device"]
        driver = BrowserDriver(browser_device, roles.get("context") or {},
                               mixes.consent.get("reject_buttons") or [], headless=not args.headed,
                               consent_settings_buttons=mixes.consent.get("settings_buttons") or [],
                               call_mode=getattr(module, "BROWSER_MODE", None) == "call",
                               ignore_https_errors=os.environ.get("RUNNER_PEER_INSECURE_TLS") == "1",
                               storage_state=storage_state)

    ctx = RunContext(driver, clock, duration, overrides)
    ctx.mixes = mixes
    ctx.run_key = f"{args.profile}/{args.seed}/{args.block_id}"
    ctx.session_meta = session_meta
    ctx.accounts = accounts
    ctx.webhook_url = webhook_url

    start = gtlog.now_iso()
    log.info("start %s on %s (%s, %s), %.0f s, mix=%s, seed=%s, block=%s",
             activity_id, device.name, device.role, device.ip, duration,
             ",".join(mix.categories) if mix else "-", args.seed, args.block_id)
    guard = _install_signal_handlers(duration if implemented and not args.dry_run else None)
    if not args.dry_run:
        ctx.guard = guard  # time limit per browser step, shared alarm with the watchdog
    try:
        if status is None:
            if module is None:
                raise NotImplementedActivity(f"{activity_id} is in the catalog but not implemented yet")
            module.run(ctx, rng, duration, mix)  # stubs raise NotImplementedActivity with a reason
            if module.NEEDS_BROWSER and not ctx.visited:
                log.error("no page could be loaded")
                status = "error"
            else:
                status = "ok"
    except NotImplementedActivity as e:
        log.warning("%s", e)
        status = "not_implemented"
    except (Exception, KeyboardInterrupt, Aborted) as e:  # noqa: BLE001 - every outcome gets a log row
        log.error("%s failed: %s: %s", activity_id, type(e).__name__, e,
                  exc_info=not isinstance(e, (KeyboardInterrupt, Aborted)))
        status = "error"
    finally:
        signal.alarm(0)
        # The log row comes first: a browser that hangs while closing (25.10: a Reddit page stuck
        # in its JS challenge) must not cost the row or keep the run alive for hours.
        row = {
            "start": start,
            "end": gtlog.now_iso(),
            "device": device.name,
            "activity_id": activity_id,
            "domains": ";".join(ctx.visited),
            "profile": args.profile,
            "seed": args.seed,
            "block_id": args.block_id,
            "status": status or "error",
        }
        if args.dry_run:
            for call in driver.calls:
                print("  " + " ".join(str(c) for c in call))
            print(f"simulated duration: {ctx.elapsed():.0f} s (not logged, dry run)")
            print(row)
        else:
            gtlog.append(row)
            log.info("logged %s: %s, domains=%s", row["status"], activity_id, row["domains"] or "-")
        _close_with_timeout(driver)
    return STATUS_EXIT[row["status"]]


def _kill_run() -> None:
    """End this run and everything below it (Playwright driver, Chromium). Chromium runs in its
    own process group, so the process tree is used, not the group (runner/steps.py)."""
    logging.shutdown()
    steps.kill_descendants()
    os.kill(os.getpid(), signal.SIGKILL)


def _close_with_timeout(driver) -> None:
    def hung(signum, frame):
        log.error("browser did not close within %d s, ending the run's processes", CLOSE_TIMEOUT)
        _kill_run()

    previous = signal.signal(signal.SIGALRM, hung)
    signal.alarm(CLOSE_TIMEOUT)
    try:
        driver.close()
    except Exception:  # noqa: BLE001
        log.warning("browser did not close cleanly")
    finally:
        signal.alarm(0)
        signal.signal(signal.SIGALRM, previous)


def _install_signal_handlers(duration: float | None) -> "steps.Guard":
    """SIGTERM aborts the run. SIGALRM belongs to the Guard: the watchdog (duration + grace)
    and the limit of the current browser step share it, the watchdog wins."""
    def abort(signum, frame):
        raise Aborted(f"signal {signum}")

    signal.signal(signal.SIGTERM, abort)
    guard = steps.Guard(time.monotonic() + duration + WATCHDOG_GRACE if duration else None)
    guard.install()
    return guard


# --- validate / list -----------------------------------------------------------------------

def cmd_validate(args) -> int:
    try:
        devices = config.load_devices()
        config.load_roles()
        mixes = config.load_mixes()
        for role in config.ROLES:
            background.load_profile(role)
    except config.ConfigError as e:
        print(f"INVALID:\n{e}", file=sys.stderr)
        return EXIT_ERROR
    datasets = sorted({d.dataset for d in devices.values()})
    print(f"OK: {len(devices)} devices in {len(datasets)} dataset(s), {len(mixes.categories)} mix categories")
    return EXIT_OK


def cmd_list(args) -> int:
    for aid, m in ACTIVITIES.items():
        dur = "as block" if m.DEFAULT_DURATION is None else f"{m.DEFAULT_DURATION[0]}-{m.DEFAULT_DURATION[1]} s"
        state = "ok  " if m.IMPLEMENTED else "stub"
        print(f"{state} {aid:<22} {'/'.join(m.ROLES):<13} {dur}")
    for aid in CATALOG_ONLY:
        print(f"stub {aid:<22} (catalog only)")
    return EXIT_OK


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="python -m runner", description="Scripted traffic runner")
    sub = p.add_subparsers(dest="cmd", required=True)

    r = sub.add_parser("run", help="run one activity and append a ground-truth log row")
    r.add_argument("--device", help="device from devices.csv (default: $RUNNER_DEVICE)")
    r.add_argument("--activity", required=True, help="activity ID from the catalog")
    r.add_argument("--duration", help="300, 90s, 5m, 2h (default: catalog default)")
    r.add_argument("--mix", help="news,social_passive or news:.2,social_passive:.4")
    r.add_argument("--seed", required=True, type=int, help="profile instance seed")
    r.add_argument("--profile", required=True, help="profile name for the log, e.g. student")
    r.add_argument("--block-id", required=True, help="block ID for the log, e.g. b001")
    r.add_argument("--pages", help="override page count range, e.g. 2-4")
    r.add_argument("--dwell", help="override dwell range, e.g. 20-90 or 1m-3m")
    r.add_argument("--platform", help="call platform from the plan (zoom/teams/jitsi/discord); all calls use the peer VM")
    r.add_argument("--mic-share", help="calls: share of the time the microphone is on, e.g. 0.1 or 10%% (profile option mic_share)")
    r.add_argument("--lookups", help="override lookup count range (sh_adjacent_lookup), e.g. 1-3")
    r.add_argument("--dry-run", action="store_true", help="no network: print the planned sequence")
    r.add_argument("--headed", action="store_true", help="show the browser (needs a display)")
    r.set_defaults(func=cmd_run)

    sub.add_parser("validate", help="validate config files").set_defaults(func=cmd_validate)
    sub.add_parser("list", help="list activities").set_defaults(func=cmd_list)
    sub.add_parser("background", help="send the device's OS/browser background traffic until stopped "
                   "(the container's main process)").set_defaults(func=lambda args: background.main())
    return p


def main(argv: list[str] | None = None) -> int:
    logging.basicConfig(level=os.environ.get("RUNNER_LOG_LEVEL", "INFO"),
                        format="%(asctime)s %(levelname)s %(message)s", datefmt="%H:%M:%S")
    args = build_parser().parse_args(argv)
    try:
        return args.func(args)
    except UsageError as e:
        log.error("%s", e)
        return EXIT_USAGE
