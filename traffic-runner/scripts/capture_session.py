#!/usr/bin/env python3
"""Capture the login session of a test account for one runner device (run on a laptop).

Opens your normal Google Chrome with a separate, empty profile. You log in by hand; the
script never sees or stores a password. Slack's sign-in check rejects browsers started by
Playwright, so the login happens in a plain Chrome window; only after you press Enter does the
script connect to that window (Chrome DevTools protocol, localhost only) and save the session
(cookies + local storage) to
    <out>/<device>.<platform>.json   (+ .meta.json)
Copy these files to the gateway (traffic-runner/sessions/, root-only). See README §9.

    python3 scripts/capture_session.py --device mdd_suicidality_a_phone --platform slack
    python3 scripts/capture_session.py --device student_a_phone --platform reddit

Needs Google Chrome and Playwright 1.63.0 on the laptop (README: test accounts). The temporary
Chrome profile is deleted afterwards.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import socket
import subprocess
import sys
import tempfile
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from runner.config import load_accounts, load_devices  # noqa: E402

PLATFORM_ACTIVITY = {"slack": "messaging", "reddit": "social_post"}
SLACK_DM = re.compile(r"^https://app\.slack\.com/client/T[A-Z0-9]+/D[A-Z0-9]+")
CHROME = "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"


def free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def start_chrome(chrome: str, profile: str, port: int, url: str) -> subprocess.Popen:
    """Plain Chrome (no automation flags) with its own profile; DevTools only on localhost."""
    return subprocess.Popen([
        chrome, f"--user-data-dir={profile}", f"--remote-debugging-port={port}",
        "--remote-debugging-address=127.0.0.1", "--no-first-run", "--no-default-browser-check",
        "--new-window", url], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)


def main(argv=None) -> int:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--device", required=True, help="device from config/devices.csv")
    p.add_argument("--platform", required=True, choices=sorted(PLATFORM_ACTIVITY))
    p.add_argument("--chrome", default=CHROME, help="path to Google Chrome")
    p.add_argument("--out", default=str(ROOT / "sessions"), help="output folder (default: traffic-runner/sessions)")
    args = p.parse_args(argv)

    devices, accounts = load_devices(), load_accounts()
    if args.device not in devices:
        p.error(f"unknown device {args.device}")
    device = devices[args.device]
    persona = (accounts.get("personas") or {}).get(device.dataset, {})
    cfg = accounts[args.platform]

    print(f"\nDevice {device.name}, dataset {device.dataset}, platform {args.platform}")
    if args.platform == "slack":
        print(f"  1. Sign in to the Slack workspace as {persona.get('name', '?')}:")
        print(f"     email cmnthif+{persona.get('tag', '?')}@… (code from the mailbox). Not 'Sign in with Google'.")
        print(f"  2. Open the direct message with '{cfg['bot_name']}' (left sidebar, Apps).")
        print("  3. Come back here and press Enter.")
    else:
        print("  1. Log in to Reddit with the shared account u/CMNTHIF (password, 2FA code).")
        print(f"  2. Open https://www.reddit.com/r/{cfg['subreddit']}/ to check the login.")
        print("  3. Come back here and press Enter.")

    from playwright.sync_api import sync_playwright
    if not Path(args.chrome).exists():
        print(f"Google Chrome not found at {args.chrome} (use --chrome)", file=sys.stderr)
        return 1
    profile = tempfile.mkdtemp(prefix="cmnthif-capture-")
    port = free_port()
    chrome = start_chrome(args.chrome, profile, port, cfg["start_url"])
    try:
        input("\nA separate Chrome window opened. Press Enter here when you are logged in"
              " (and, for Slack, in the bot's DM)... ")
        with sync_playwright() as pw:
            browser = pw.chromium.connect_over_cdp(f"http://127.0.0.1:{port}")
            ctx = browser.contexts[0]
            meta = {"device": device.name, "platform": args.platform, "browser": "chrome"}
            while True:  # wrong tab: let the user fix it instead of losing the login
                urls = [pg.url for pg in ctx.pages]
                if args.platform == "slack":
                    dm = next((SLACK_DM.match(u).group(0) for u in urls if SLACK_DM.match(u)), None)
                    if dm:
                        meta["dm_url"] = meta["url"] = dm
                        break
                    problem = (f"No tab is on a Slack direct message (the URL must contain /D…, "
                               f"channels are /C…): {urls}\nClick '{cfg['bot_name']}' under Apps in the "
                               f"sidebar, open its Messages tab")
                else:
                    page_urls = [u for u in urls if "reddit.com" in u and "/login" not in u]
                    if page_urls:
                        meta["url"] = page_urls[0]
                        break
                    problem = f"No logged-in Reddit tab: {urls}\nLog in to Reddit"
                answer = input(f"\n{problem}, then press Enter again (or type q to quit)... ")
                if answer.strip().lower() == "q":
                    return 1
            out = Path(args.out)
            out.mkdir(parents=True, exist_ok=True)
            state = out / f"{device.name}.{args.platform}.json"
            ctx.storage_state(path=str(state))
            (out / f"{device.name}.{args.platform}.meta.json").write_text(json.dumps(meta, indent=2))
            for f in (state, out / f"{device.name}.{args.platform}.meta.json"):
                os.chmod(f, 0o600)
            browser.close()
    finally:
        chrome.terminate()
        try:
            chrome.wait(10)
        except subprocess.TimeoutExpired:
            chrome.kill()
        time.sleep(1)
        shutil.rmtree(profile, ignore_errors=True)  # the profile holds the login too
    print(f"\nsaved {state} (+ .meta.json). It is a login: treat it like a password.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
