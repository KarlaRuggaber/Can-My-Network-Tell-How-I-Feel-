"""Tiny synthetic run: two days of partitions, a plan and a runner state log."""

from __future__ import annotations

import json
from datetime import datetime, timedelta
from pathlib import Path

import numpy as np
import pandas as pd

from cmn_frontend.settings import REPO_ROOT, Settings

DS = "gw_test_a"
PHONE_IP = "10.42.1.21"


def write_partition(processed: Path, start: datetime, n: int = 40, seed: int = 0) -> Path:
    rng = np.random.default_rng(seed)
    ts = [start + timedelta(seconds=float(s)) for s in sorted(rng.uniform(0, 290, n))]
    rows = []
    for i, t in enumerate(ts):
        out = i % 2 == 0
        dns = i % 5 == 0
        rows.append({
            "Timestamp": pd.Timestamp(t), "Date": t.date().isoformat(), "Hour": t.hour,
            "Protocol": "UDP" if dns else "TCP",
            "Source IP": PHONE_IP if out else ("10.42.1.1" if dns else "151.101.66.114"),
            "Destination IP": ("10.42.1.1" if dns else "151.101.66.114") if out else PHONE_IP,
            "Source Port": 40000 if out else (53 if dns else 443),
            "Destination Port": (53 if dns else 443) if out else 40000,
            "TCP Flags": None if dns else "PA", "Length": int(rng.integers(60, 1500)),
            "IsDNS": dns, "DNS_QNAME": "www.nzz.ch" if dns and out else None,
            "DNS_QTYPE": 1.0 if dns and out else np.nan, "Capture File": "cap-test.pcap",
            "DNS_ANS_IPS": "151.101.66.114" if dns and not out else None,
            "DNS_ANS_NAME": "www.nzz.ch" if dns and not out else None,
        })
    d = processed / DS
    d.mkdir(parents=True, exist_ok=True)
    p = d / f"{DS}__{start:%Y%m%d_%H%M}.parquet"
    pd.DataFrame(rows).to_parquet(p, index=False)
    return p


def make_run(tmp: Path) -> Settings:
    processed, run, cache = tmp / "processed_parquet", tmp / "run", tmp / "cache"
    for day, hours in (("2026-11-08", (8, 12, 23)), ("2026-11-09", (1, 9, 20))):
        for h in hours:
            write_partition(processed, datetime.fromisoformat(f"{day}T{h:02d}:00"), seed=h)
    run.mkdir(parents=True)
    plan = pd.DataFrame([
        {"start": "2026-11-08T08:00:00+01:00", "end": "2026-11-08T08:05:00+01:00",
         "device": "test_a_phone", "activity_id": "phone_check", "block_id": "b1", "day": "2026-11-08",
         "phase": "baseline", "profile_block": "wake_check", "mix": "news:1", "flag": "", "profile": "student",
         "companion_of": ""},
        {"start": "2026-11-08T23:50:00+01:00", "end": "2026-11-09T00:30:00+01:00",
         "device": "test_a_phone", "activity_id": "social_passive", "block_id": "b2", "day": "2026-11-08",
         "phase": "baseline", "profile_block": "evening_stream", "mix": "", "flag": "", "profile": "student",
         "companion_of": ""},
        {"start": "2026-11-09T01:00:00+01:00", "end": "2026-11-09T01:10:00+01:00",
         "device": "test_a_phone", "activity_id": "crisis_resource_visit", "block_id": "b3",
         "day": "2026-11-08", "phase": "profile", "profile_block": "suicidality", "mix": "",
         "flag": "sensitive", "profile": "mdd", "companion_of": ""},
        {"start": "2030-01-01T09:00:00+01:00", "end": "2030-01-01T09:10:00+01:00",
         "device": "test_a_phone", "activity_id": "browse", "block_id": "b4", "day": "2030-01-01",
         "phase": "profile", "profile_block": "day_checks", "mix": "", "flag": "", "profile": "mdd",
         "companion_of": ""},
    ])
    plan.to_csv(run / f"{DS}.csv", index=False)
    events = [
        {"t": "2026-11-08T07:00:03+00:00", "event": "start", "block_id": "b1", "late_s": 3},
        {"t": "2026-11-08T07:05:00+00:00", "event": "exit", "block_id": "b1", "code": 0},
        {"t": "2026-11-08T22:50:00+00:00", "event": "start", "block_id": "b2", "late_s": 0},
        {"t": "2026-11-08T23:30:00+00:00", "event": "exit", "block_id": "b2", "code": 1},
    ]
    (run / f"{DS}.state.jsonl").write_text("\n".join(json.dumps(e) for e in events) + "\nnot json\n")
    devices = tmp / "devices.csv"
    devices.write_text("# comment\ndevice,role,mac,ip,dataset\n"
                       f"test_a_phone,phone,02:00:00:00:00:01,{PHONE_IP},{DS}\n"
                       "other_phone,phone,02:00:00:00:00:02,10.42.1.99,gw_other_a\n")
    app_dir = REPO_ROOT / "app_pcap_to_dsm5" / "app"
    return Settings(data_dir=tmp, processed_dir=processed, run_dir=run, cache_dir=cache,
                    daily_tables=tmp / "eval",
                    app_dir=app_dir, fasl_config=app_dir / "fasl_config.json",
                    devices_csv=devices, web_dist=tmp / "no-dist")
