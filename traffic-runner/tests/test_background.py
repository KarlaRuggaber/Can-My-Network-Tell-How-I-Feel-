"""Background traffic (runner/background.py, config/background.yaml)."""

import http.server
import json
import random
import threading

import pytest

from runner import background, config
from runner.background import Profile, Source

DAY = 86400


def fake_hour(t):
    return int(t // 3600) % 24


def count_events(profile, days=7, seed=1):
    per_hour = [0] * 24
    for t, _ in background.schedule(profile, random.Random(seed), 0.0, fake_hour):
        if t >= days * DAY:
            break
        per_hour[fake_hour(t)] += 1
    return [n / days for n in per_hour]


@pytest.mark.parametrize("role", config.ROLES)
def test_config_has_low_rate_sources_for_every_role(role):
    p = background.load_profile(role)
    assert len(p.sources) >= 5
    assert 10 <= p.per_hour(12) <= 40          # a request every few minutes by day
    assert p.per_hour(3) < p.per_hour(12) / 2  # fewer at night, but never zero
    assert p.per_hour(3) > 2


def test_measured_rate_matches_the_configured_rate():
    p = background.load_profile("laptop")
    hourly = count_events(p, days=14)
    day = sum(hourly[8:20]) / 12
    night = sum(hourly[0:6]) / 6
    assert day == pytest.approx(p.per_hour(12), rel=0.12)
    assert night == pytest.approx(p.per_hour(3), rel=0.25)
    assert all(n > 0 for n in hourly)  # every hour of the day has background, also 00-06


def test_schedule_is_reproducible_and_in_time_order():
    p = background.load_profile("phone")
    a = background.schedule(p, random.Random(5), 0.0, fake_hour)
    b = background.schedule(p, random.Random(5), 0.0, fake_hour)
    ea = [next(a) for _ in range(200)]
    assert ea == [next(b) for _ in range(200)]
    times = [t for t, _ in ea]
    assert times == sorted(times)
    assert {s.name for _, s in ea} == {s.name for s in p.sources}


def test_night_window_can_wrap_midnight():
    p = Profile((), 3.0, (22, 6))
    assert [p.factor(h) for h in (21, 22, 2, 6)] == [1.0, 3.0, 3.0, 1.0]


@pytest.mark.parametrize("bad, message", [
    ({"kind": "ftp", "url": "x", "every": "5m"}, "kind must be"),
    ({"kind": "get", "url": "x", "every": "5m"}, "needs an http"),
    ({"kind": "get", "url": "https://a.example/", "every": "2s"}, "bad every"),
    ({"kind": "tls", "host": "a.example", "every": "5m"}, "needs host and port"),
])
def test_invalid_sources_are_rejected(tmp_path, bad, message):
    path = tmp_path / "background.yaml"
    path.write_text(json.dumps({"roles": {"phone": {"sources": [bad]}}}))
    with pytest.raises(config.ConfigError, match=message):
        background.load_profile("phone", path)


# --- requests (local only) -----------------------------------------------------------------

@pytest.fixture
def server():
    class Handler(http.server.BaseHTTPRequestHandler):
        def do_GET(self):
            code = 404 if self.path == "/missing" else 200
            body = b"x" * (200 * 1024 if self.path == "/big" else 10)
            self.send_response(code)
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, *args):
            pass

    httpd = http.server.HTTPServer(("127.0.0.1", 0), Handler)
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    yield f"http://127.0.0.1:{httpd.server_address[1]}"
    httpd.shutdown()


def test_get_reads_the_answer_and_counts_error_codes_as_a_normal_exchange(server):
    ok = background.perform(Source("t", "get", 60, url=server + "/"))
    missing = background.perform(Source("t", "get", 60, url=server + "/missing"))
    big = background.perform(Source("t", "get", 60, url=server + "/big"))
    assert (ok["ok"], ok["status"], ok["bytes"], ok["host"]) == (True, 200, 10, "127.0.0.1")
    assert (missing["ok"], missing["status"]) == (True, 404)
    assert big["bytes"] == background.READ_LIMIT  # never downloads more than 64 KiB


@pytest.mark.parametrize("source", [
    Source("t", "get", 60, url="http://127.0.0.1:9/"),
    Source("t", "tls", 60, host="127.0.0.1", port=9),
    Source("t", "get", 60, url="http://no-such-host.invalid/"),
])
def test_failed_requests_never_raise(source, monkeypatch):
    monkeypatch.setattr(background, "REQUEST_TIMEOUT", 2)
    row = background.perform(source)
    assert row["ok"] is False and row["error"]


def test_run_logs_every_request_and_keeps_going_after_failures(tmp_path):
    now = [1_000_000.0]
    naps = []

    def sleep(s):
        naps.append(s)
        now[0] += s

    calls = []

    def do(s):
        calls.append(s.name)
        return {"source": s.name, "ok": len(calls) % 2 == 0, "error": "boom"}

    device = config.Device("x_phone", "phone", "02:00:0a:2a:01:63", "10.42.1.99", "gw_x")
    log_path = tmp_path / "bg.jsonl"
    n = background.run(device, background.load_profile("phone"), log_path=log_path,
                       clock=lambda: now[0], sleep=sleep, do=do, hour_of=fake_hour, limit=20)
    rows = [json.loads(line) for line in log_path.read_text().splitlines()]
    assert n == 20 and len(rows) == 20 and len(calls) == 20
    assert all(r["device"] == "x_phone" and r["ts"] for r in rows)
    assert max(naps) <= 60


def test_main_keeps_the_container_alive_when_the_config_is_broken(monkeypatch):
    class Stop(Exception):
        pass

    def broken():
        raise config.ConfigError("broken devices.csv")

    def sleep(s):
        raise Stop  # the fallback loop was reached instead of an exit

    monkeypatch.setenv("RUNNER_DEVICE", "student_a_phone")
    monkeypatch.setattr(config, "load_devices", broken)
    monkeypatch.setattr(background.time, "sleep", sleep)
    monkeypatch.setattr(background.signal, "signal", lambda *a: None)
    with pytest.raises(Stop):
        background.main()


def test_extra_roots_are_added_to_the_default_store(monkeypatch):
    monkeypatch.setattr(background, "_tls", None)
    ctx = background.tls_context()
    names = {dict(x[0] for x in c["subject"]).get("commonName") for c in ctx.get_ca_certs()}
    assert {"Microsoft Root Certificate Authority 2011", "Microsoft ECC Product Root Certificate Authority 2018"} <= names
    assert ctx.verify_mode == background.ssl.CERT_REQUIRED and ctx.check_hostname
