"""Paths and environment. Everything can be overridden with environment variables."""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[3]


@dataclass(frozen=True)
class Settings:
    data_dir: Path       # ~/cmn-data: processed_parquet/ and run/ copied from the gateway
    processed_dir: Path  # <data_dir>/processed_parquet/<dataset>/<dataset>__YYYYMMDD_HHMM.parquet
    run_dir: Path        # <data_dir>/run: plans (<dataset>.csv) and runner state (<dataset>.state.jsonl)
    daily_tables: Path   # evaluation's daily metric tables: <dataset>.daily.csv (preferred source)
    cache_dir: Path      # per-day results of this frontend (separate from the Streamlit feature_cache)
    app_dir: Path        # app_pcap_to_dsm5/app (metric code + fasl_config.json), read-only
    fasl_config: Path
    devices_csv: Path    # traffic-runner/config/devices.csv: IP -> device name
    web_dist: Path       # built React app, served by the API when present
    home: Path | None = None  # logins, person profiles, session key (default <data_dir>/frontend)

    @property
    def home_dir(self) -> Path:
        return self.home or self.data_dir / "frontend"


def load_settings() -> Settings:
    data_dir = Path(os.environ.get("CMN_DATA", "~/cmn-data")).expanduser()
    app_dir = Path(os.environ.get("CMN_APP_DIR", REPO_ROOT / "app_pcap_to_dsm5" / "app")).expanduser()
    return Settings(
        data_dir=data_dir,
        processed_dir=Path(os.environ.get("CMN_PROCESSED", data_dir / "processed_parquet")).expanduser(),
        run_dir=Path(os.environ.get("CMN_RUN", data_dir / "run")).expanduser(),
        daily_tables=Path(os.environ.get("CMN_DAILY_TABLES", data_dir / "eval")).expanduser(),
        cache_dir=Path(os.environ.get("CMN_CACHE", data_dir / "frontend_cache")).expanduser(),
        app_dir=app_dir,
        fasl_config=Path(os.environ.get("CMN_FASL_CONFIG", app_dir / "fasl_config.json")).expanduser(),
        devices_csv=Path(os.environ.get(
            "CMN_DEVICES", REPO_ROOT / "traffic-runner" / "config" / "devices.csv")).expanduser(),
        web_dist=REPO_ROOT / "frontend" / "web" / "dist",
        home=Path(os.environ.get("CMN_HOME", data_dir / "frontend")).expanduser(),
    )
