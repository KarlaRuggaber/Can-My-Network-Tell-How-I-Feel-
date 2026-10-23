"""CLI end to end without network: stubs, idle, usage errors, log rows."""

import csv

import pytest

from runner import cli


@pytest.fixture
def logdir(tmp_path, monkeypatch):
    monkeypatch.setenv("RUNNER_LOG_DIR", str(tmp_path))
    monkeypatch.delenv("RUNNER_DEVICE", raising=False)
    monkeypatch.delenv("RUNNER_STRICT_IP", raising=False)
    return tmp_path


def rows(logdir):
    return list(csv.DictReader((logdir / "ground_truth.csv").open()))


BASE = ["run", "--device", "student_a_phone", "--seed", "42", "--profile", "student", "--block-id", "b001"]


def test_stub_logs_not_implemented(logdir):
    assert cli.main(BASE + ["--activity", "messaging"]) == cli.EXIT_NOT_IMPLEMENTED
    r = rows(logdir)[0]
    assert (r["activity_id"], r["status"], r["domains"]) == ("messaging", "not_implemented", "")


def test_catalog_only_activity_logs_not_implemented(logdir):
    assert cli.main(BASE + ["--activity", "away"]) == cli.EXIT_NOT_IMPLEMENTED
    assert rows(logdir)[0]["status"] == "not_implemented"


def test_login_only_mix_logs_not_implemented(logdir):
    assert cli.main(BASE + ["--activity", "phone_check", "--mix", "messaging"]) == cli.EXIT_NOT_IMPLEMENTED


def test_idle_connected_real_clock(logdir):
    assert cli.main(BASE + ["--activity", "idle_connected", "--duration", "1"]) == cli.EXIT_OK
    r = rows(logdir)[0]
    assert r["status"] == "ok" and r["device"] == "student_a_phone" and r["seed"] == "42"


@pytest.mark.parametrize("extra", [
    ["--activity", "nonsense"],
    ["--activity", "browse", "--mix", "news"],                 # as block: needs --duration
    ["--activity", "browse", "--duration", "60"],              # needs --mix
    ["--activity", "browse", "--duration", "60", "--mix", "nope"],
    ["--activity", "browse", "--duration", "5x", "--mix", "news"],
])
def test_usage_errors_write_no_row(logdir, extra):
    assert cli.main(BASE + extra) == cli.EXIT_USAGE
    assert not (logdir / "ground_truth.csv").exists()


def test_container_device_mismatch(logdir, monkeypatch):
    monkeypatch.setenv("RUNNER_DEVICE", "student_a_laptop")
    assert cli.main(BASE + ["--activity", "idle_connected", "--duration", "1"]) == cli.EXIT_USAGE


def test_dry_run_writes_no_row(logdir, capsys):
    assert cli.main(BASE + ["--activity", "phone_check", "--mix", "news", "--dry-run"]) == cli.EXIT_OK
    assert "open https://" in capsys.readouterr().out
    assert not (logdir / "ground_truth.csv").exists()


def test_parse_duration():
    assert cli.parse_duration("300") == 300
    assert cli.parse_duration("5m") == 300
    assert cli.parse_duration("2h") == 7200
    assert cli.parse_range("1m-3m") == (60, 180)
    assert cli.parse_range("1-3", integer=True) == (1, 3)


@pytest.mark.parametrize("activity", ["video_call", "voice_call", "gaming_session"])
def test_peer_activities_without_vm_log_not_implemented(logdir, monkeypatch, activity):
    monkeypatch.delenv("RUNNER_PEER_URL", raising=False)
    monkeypatch.delenv("RUNNER_PEER_TOKEN", raising=False)
    assert cli.main(BASE + ["--activity", activity, "--duration", "60"]) == cli.EXIT_NOT_IMPLEMENTED
    assert rows(logdir)[0]["status"] == "not_implemented"
