"""devices.csv validation."""

import pytest

from runner.config import ConfigError, load_devices

HEADER = "device,role,mac,ip,dataset\n"
GOOD = (
    "student_a_phone,phone,02:00:0a:2a:01:0b,10.42.1.11,gw_student_a\n"
    "student_a_laptop,laptop,02:00:0a:2a:01:0c,10.42.1.12,gw_student_a\n"
)


def write(tmp_path, body, header=HEADER):
    p = tmp_path / "devices.csv"
    p.write_text(header + body)
    return p


def test_naming_convention_accepted(tmp_path):
    body = "insomnia_b_phone,phone,02:00:00:00:00:01,10.42.1.21,gw_insomnia_b\n9to5_a_phone,phone,02:00:00:00:00:02,10.42.1.22,gw_9to5_a\n"
    devices = load_devices(write(tmp_path, body))
    assert devices["9to5_a_phone"].dataset == "gw_9to5_a"


def test_repo_devices_file_is_valid():
    devices = load_devices()
    assert devices["student_a_phone"].ip == "10.42.1.11"
    assert devices["student_a_laptop"].dataset == devices["student_a_phone"].dataset


def test_good_file(tmp_path):
    devices = load_devices(write(tmp_path, GOOD))
    assert list(devices) == ["student_a_phone", "student_a_laptop"]
    assert devices["student_a_laptop"].role == "laptop"


@pytest.mark.parametrize("row, message", [
    ("x,phone,02:00:00:00:00:01,10.42.1.11,gw_a\n", "already used by"),                    # duplicate IP
    ("x,phone,02:00:0a:2a:01:0b,10.42.1.20,gw_a\n", "already used by"),                    # duplicate MAC
    ("student_a_phone,phone,02:00:00:00:00:01,10.42.1.20,gw_a\n", "duplicate device"),
    ("x,tablet,02:00:00:00:00:01,10.42.1.20,gw_a\n", "role"),
    ("x,phone,00:11:22:33:44:55,10.42.1.20,gw_a\n", "locally administered"),               # vendor MAC
    ("x,phone,03:00:00:00:00:01,10.42.1.20,gw_a\n", "multicast"),
    ("x,phone,02:00:00:00:00:0G,10.42.1.20,gw_a\n", "lower-case"),
    ("x,phone,02:00:00:00:00:AB,10.42.1.20,gw_a\n", "lower-case"),
    ("x,phone,02:00:00:00:00:01,10.42.1.5,gw_a\n", "must be within"),                      # below .10
    ("x,phone,02:00:00:00:00:01,10.42.0.20,gw_a\n", "must be within"),                     # real LAN
    ("x,phone,02:00:00:00:00:01,10.42.1.255,gw_a\n", "must be within"),
    ("x,phone,02:00:00:00:00:01,10.42.1.999,gw_a\n", "not a valid"),
    ("Bad-Name,phone,02:00:00:00:00:01,10.42.1.20,gw_a\n", "must match"),
    ("x,phone,02:00:00:00:00:01,10.42.1.20,\n", "dataset"),
    ("x,phone,02:00:00:00:00:01,10.42.1.20,gw_student_01\n", "must not end with a digit"),
    ("x,phone,02:00:00:00:00:01,10.42.1.20,student_b\n", "must start with gw_"),
    ("x,phone,02:00:00:00:00:01,10.42.1.20,gw_bonus_a\n", "must not contain 'onu'"),
    ("x,phone,02:00:00:00:00:01,10.42.1.20,gw_brass_a\n", "must not contain 'bras'"),
    ("x,phone,02:00:00:00:00:01, 10.42.1.20,gw_a\n", "whitespace"),
    ("x,phone,02:00:00:00:00:01,10.42.1.20\n", "columns"),
])
def test_invalid_rows(tmp_path, row, message):
    with pytest.raises(ConfigError, match=message):
        load_devices(write(tmp_path, GOOD + row))


def test_wrong_header(tmp_path):
    with pytest.raises(ConfigError, match="header"):
        load_devices(write(tmp_path, GOOD, header="device,role,mac,ip\n"))


def test_all_errors_reported_at_once(tmp_path):
    body = "a,phone,00:11:22:33:44:55,10.42.1.20,gw_a\nb,tablet,02:00:00:00:00:02,10.42.0.5,gw_a\n"
    with pytest.raises(ConfigError) as e:
        load_devices(write(tmp_path, body))
    assert str(e.value).count("\n") >= 2


def test_comment_and_blank_lines(tmp_path):
    body = "# simulated devices\n" + GOOD.replace("\n", "\n\n", 1) + "  # trailing comment\n"
    devices = load_devices(write(tmp_path, body, header="# devices.csv shared with the ingest\n" + HEADER))
    assert list(devices) == ["student_a_phone", "student_a_laptop"]


def test_line_numbers_count_comments(tmp_path):
    body = "# one\n# two\nx,tablet,02:00:00:00:00:01,10.42.1.20,gw_a\n"
    with pytest.raises(ConfigError, match=r"devices.csv:4: role"):
        load_devices(write(tmp_path, body))
