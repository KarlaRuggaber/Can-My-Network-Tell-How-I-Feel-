"""docker-compose.yml is generated from devices.csv."""

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))

import gen_compose  # noqa: E402


def test_compose_is_up_to_date():
    if not gen_compose.COMPOSE.exists():
        pytest.skip("docker-compose.yml is not part of the image")
    assert gen_compose.main(["--check"]) == 0, "run python3 scripts/gen_compose.py"


def test_render_contains_every_device(tmp_path):
    csv_path = tmp_path / "devices.csv"
    csv_path.write_text(
        "device,role,mac,ip,dataset\n"
        "a_phone,phone,02:00:00:00:00:01,10.42.1.21,gw_a\n"
        "a_laptop,laptop,02:00:00:00:00:02,10.42.1.22,gw_a\n"
    )
    text = gen_compose.render(csv_path)
    assert text.count("ipv4_address:") == 2
    assert "ipv4_address: 10.42.1.22" in text and 'mac_address: "02:00:00:00:00:02"' in text
    assert text.count("build:") == 1
    assert "hostname: a-phone" in text
    assert "/app/config" not in text  # config is baked into the image, not mounted
