#!/usr/bin/env python3
"""Capture the login session of a test account for one runner device (run on a laptop).

Opens a visible Chromium that looks like the runner device (same Playwright version, the
device's emulation, Swiss locale). You log in by hand; the script never sees or stores a
password. When you press Enter, it saves the session (cookies + local storage) to
    <out>/<device>.<platform>.json   (+ .meta.json)
Copy these files to the gateway (traffic-runner/sessions/, root-only). See README §9.

    python3 scripts/capture_session.py --device mdd_suicidality_a_phone --platform slack
    python3 scripts/capture_session.py --device student_a_phone --platform reddit

Needs Playwright 1.63.0 with its Chromium on the laptop (README: test accounts).
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from runner.activities import ACTIVITIES  # noqa: E402
from runner.config import load_accounts, load_devices, load_roles  # noqa: E402

PLATFORM_ACTIVITY = {"slack": "messaging", "reddit": "social_post"}
SLACK_DM = re.compile(r"^https://app\.slack\.com/client/T[A-Z0-9]+/D[A-Z0-9]+")


def main(argv=None) -> int:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--device", required=True, help="device from config/devices.csv")
    p.add_argument("--platform", required=True, choices=sorted(PLATFORM_ACTIVITY))
    p.add_argument("--out", default=str(ROOT / "sessions"), help="output folder (default: traffic-runner/sessions)")
    args = p.parse_args(argv)

    devices, roles, accounts = load_devices(), load_roles(), load_accounts()
    if args.device not in devices:
        p.error(f"unknown device {args.device}")
    device = devices[args.device]
    module = ACTIVITIES[PLATFORM_ACTIVITY[args.platform]]
    emulation = getattr(module, "PLAYWRIGHT_DEVICE", None) or roles[device.role]["playwright_device"]
    persona = (accounts.get("personas") or {}).get(device.dataset, {})
    cfg = accounts[args.platform]

    print(f"\nDevice {device.name} ({emulation}), dataset {device.dataset}, platform {args.platform}")
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
    with sync_playwright() as pw:
        descriptor = {k: v for k, v in pw.devices[emulation].items() if k != "default_browser_type"}
        browser = pw.chromium.launch(channel="chromium", headless=False)
        ctx = browser.new_context(**descriptor, **(roles.get("context") or {}))
        page = ctx.new_page()
        page.goto(cfg["start_url"])
        input("\nPress Enter when you are logged in (and, for Slack, in the bot's DM)... ")
        meta = {"device": device.name, "platform": args.platform, "url": page.url}
        if args.platform == "slack":
            if not SLACK_DM.match(page.url):
                print(f"\nThe browser is not on a Slack direct message: {page.url}\n"
                      f"Open the DM with '{cfg['bot_name']}' and run the script again.", file=sys.stderr)
                browser.close()
                return 1
            meta["dm_url"] = SLACK_DM.match(page.url).group(0)
        elif "/login" in page.url:
            print("\nStill on the Reddit login page. Log in first and run the script again.", file=sys.stderr)
            browser.close()
            return 1
        out = Path(args.out)
        out.mkdir(parents=True, exist_ok=True)
        state = out / f"{device.name}.{args.platform}.json"
        ctx.storage_state(path=str(state))
        (out / f"{device.name}.{args.platform}.meta.json").write_text(json.dumps(meta, indent=2))
        for f in (state, out / f"{device.name}.{args.platform}.meta.json"):
            os.chmod(f, 0o600)
        browser.close()
    print(f"\nsaved {state} (+ .meta.json). It is a login: treat it like a password.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
