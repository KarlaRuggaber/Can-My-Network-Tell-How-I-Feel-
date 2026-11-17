"""tapingest's device lookup: MAC first, IP only when the MAC fits, several devices files.

Run from app_pcap_to_dsm5/:  python -m pytest tests
"""

import os
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "ingest"))

import tapingest  # noqa: E402

HEADER = "device,role,mac,ip,dataset\n"
GW_MAC = "aa:aa:aa:aa:aa:01"          # the gateway's own interface: in no devices file
PHONE_MAC, PHONE_IP = "a2:4f:00:00:00:01", "10.42.0.21"
SIM_MAC, SIM_IP = "02:00:0a:2a:01:0b", "10.42.1.11"


@pytest.fixture
def files(tmp_path):
    sim = tmp_path / "devices.csv"
    sim.write_text(HEADER + f"student_a_phone,phone,{SIM_MAC},{SIM_IP},gw_student_a\n")
    real = tmp_path / "devices.real.csv"
    real.write_text(HEADER + "# real devices: gateway-local, not in git\n"
                    f"karla_iphone,phone,{PHONE_MAC},{PHONE_IP},gw_karla_a\n")
    return sim, real


def lookup(files):
    m = tapingest.DeviceMap(list(files))
    m.refresh()
    return m


def pkt(src_ip, dst_ip):
    return {"Source IP": src_ip, "Destination IP": dst_ip}


def test_simulated_device_unchanged(files):
    m = lookup(files)
    assert m.dataset_for(pkt(SIM_IP, "151.101.1.1"), SIM_MAC, GW_MAC) == "gw_student_a"
    assert m.dataset_for(pkt("151.101.1.1", SIM_IP), GW_MAC, SIM_MAC) == "gw_student_a"   # routed reply


def test_phone_keeps_its_person_after_a_dhcp_change(files):
    m = lookup(files)
    new_ip = "10.42.0.157"
    assert m.dataset_for(pkt(new_ip, "17.1.1.1"), PHONE_MAC, GW_MAC) == "gw_karla_a"
    assert m.dataset_for(pkt("17.1.1.1", new_ip), GW_MAC, PHONE_MAC) == "gw_karla_a"


def test_old_address_on_another_device_is_not_credited(files):
    m = lookup(files)
    other = "3e:11:22:33:44:55"            # unregistered device that got the phone's old address
    assert m.dataset_for(pkt(PHONE_IP, "17.1.1.1"), other, GW_MAC) is None
    assert m.dataset_for(pkt("17.1.1.1", PHONE_IP), GW_MAC, other) is None


def test_ip_still_counts_without_a_mac_or_without_a_registered_mac(files, tmp_path):
    m = lookup(files)
    assert m.dataset_for(pkt(PHONE_IP, "17.1.1.1"), None, None) == "gw_karla_a"
    nomac = tmp_path / "nomac.csv"
    nomac.write_text(HEADER + "old_laptop,laptop,,10.42.0.30,gw_karla_a\n")
    m = lookup([*files, nomac])
    assert m.dataset_for(pkt("10.42.0.30", "17.1.1.1"), "3e:00:00:00:00:09", GW_MAC) == "gw_karla_a"


def test_dhcp_broadcast_from_zero_address(files):
    m = lookup(files)
    assert m.dataset_for(pkt("0.0.0.0", "255.255.255.255"), PHONE_MAC, "ff:ff:ff:ff:ff:ff") == "gw_karla_a"


def test_duplicates_across_files_are_rejected(files, tmp_path):
    dup = tmp_path / "dup.csv"
    dup.write_text(HEADER + f"someone_else,phone,{PHONE_MAC},10.42.0.99,gw_other_a\n")
    with pytest.raises(ValueError, match="duplicate mac"):
        tapingest.load_devices([*files, dup])


def test_reloads_when_the_real_devices_file_changes(files):
    sim, real = files
    m = lookup(files)
    laptop_mac = "a2:4f:00:00:00:02"
    assert m.dataset_for(pkt("10.42.0.22", "17.1.1.1"), laptop_mac, GW_MAC) is None
    real.write_text(real.read_text() + f"karla_laptop,laptop,{laptop_mac},10.42.0.22,gw_karla_a\n")
    os.utime(real, (real.stat().st_atime, real.stat().st_mtime + 5))
    m.refresh()
    assert m.dataset_for(pkt("10.42.0.22", "17.1.1.1"), laptop_mac, GW_MAC) == "gw_karla_a"


def test_command_line_takes_several_devices_files(files, tmp_path):
    import subprocess
    watch = tmp_path / "ready"
    watch.mkdir()
    args = [sys.executable, str(Path(tapingest.__file__)), "--watch", str(watch), "--once",
            "--out", str(tmp_path / "parquet"), "--state", str(tmp_path / "state.sqlite")]
    for f in files:
        args += ["--devices", str(f)]
    r = subprocess.run(args, capture_output=True, text=True, timeout=120, env={**os.environ, "TZ": "Europe/Zurich"})
    assert r.returncode == 0, r.stderr
    assert "Loaded 2 device(s)" in r.stderr + r.stdout
