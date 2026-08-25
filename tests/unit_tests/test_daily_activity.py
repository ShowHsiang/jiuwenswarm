from __future__ import annotations

import json
import ssl
import uuid

from jiuwenswarm.common import daily_activity


def _state(tmp_path, monkeypatch):
    monkeypatch.setenv("JIUWENSWARM_DATA_DIR", str(tmp_path))
    return tmp_path / "telemetry" / "state.json"


def test_separate_launches_keep_installation_id_and_get_unique_events(tmp_path, monkeypatch):
    state_path = _state(tmp_path, monkeypatch)
    first = daily_activity._enqueue_launch("cli")
    second = daily_activity._enqueue_launch("desktop")

    state = json.loads(state_path.read_text(encoding="utf-8"))
    uuid.UUID(state["installation_id"])
    assert first != second
    assert [item["entrypoint"] for item in state["pending"]] == ["cli", "desktop"]
    assert {item["installation_id"] for item in state["pending"]} == {
        state["installation_id"]
    }


def test_coarse_location_uses_iana_timezone_without_network(monkeypatch):
    zone_tab = "\n".join(
        [
            "SG\t+0117+10351\tAsia/Singapore",
            "BR\t-2332-04637\tAmerica/Sao_Paulo",
            "FR\t+4852+00220\tEurope/Paris",
        ]
    )
    monkeypatch.setattr(daily_activity, "_read_zone_tab", lambda: zone_tab)

    assert daily_activity._coarse_location("Asia/Singapore") == (
        "Asia Pacific",
        "SG",
    )
    assert daily_activity._coarse_location("America/Sao_Paulo") == (
        "South America",
        "BR",
    )
    assert daily_activity._coarse_location("Europe/Paris") == ("Europe", "FR")
    monkeypatch.setattr(daily_activity, "_country_code_from_locale", lambda: "")
    assert daily_activity._coarse_location("UTC") == ("", "")


def test_coarse_location_falls_back_to_locale_country(monkeypatch):
    monkeypatch.setattr(daily_activity, "_read_zone_tab", lambda: "")
    monkeypatch.setattr(daily_activity, "_country_code_from_locale", lambda: "US")

    assert daily_activity._coarse_location("America/New_York") == (
        "North America",
        "US",
    )


def test_launch_event_contains_coarse_location(monkeypatch):
    monkeypatch.setattr(daily_activity, "_timezone_name", lambda _now: "Asia/Singapore")
    monkeypatch.setattr(
        daily_activity,
        "_coarse_location",
        lambda _timezone: ("Asia Pacific", "SG"),
    )

    event = daily_activity._build_event(str(uuid.uuid4()), "cli")

    assert event["timezone"] == "Asia/Singapore"
    assert event["region"] == "Asia Pacific"
    assert event["country"] == "SG"


def test_report_launch_only_once_inside_same_process(tmp_path, monkeypatch):
    state_path = _state(tmp_path, monkeypatch)
    monkeypatch.setattr(daily_activity, "_start_flush_thread", lambda: None)
    daily_activity._reset_process_guard_for_tests()

    assert daily_activity.report_launch("cli") is not None
    assert daily_activity.report_launch("cli") is None
    state = json.loads(state_path.read_text(encoding="utf-8"))
    assert len(state["pending"]) == 1


def test_disabled_and_child_processes_do_not_write(tmp_path, monkeypatch):
    state_path = _state(tmp_path, monkeypatch)
    monkeypatch.setenv("JIUWENSWARM_TELEMETRY_DISABLED", "1")
    daily_activity._reset_process_guard_for_tests()
    assert daily_activity.report_launch("cli") is None
    assert not state_path.exists()

    monkeypatch.delenv("JIUWENSWARM_TELEMETRY_DISABLED")
    monkeypatch.setenv("JIUWENSWARM_TELEMETRY_CHILD", "1")
    daily_activity._reset_process_guard_for_tests()
    assert daily_activity.report_launch("app") is None
    assert not state_path.exists()


def test_flush_removes_acknowledged_events_and_stops_on_failure(tmp_path, monkeypatch):
    state_path = _state(tmp_path, monkeypatch)
    first = daily_activity._enqueue_launch("cli")
    second = daily_activity._enqueue_launch("desktop")
    outcomes = iter([True, False])
    monkeypatch.setattr(daily_activity, "_post_event", lambda _event: next(outcomes))

    assert daily_activity.flush_pending() == 1
    state = json.loads(state_path.read_text(encoding="utf-8"))
    assert [item["event_id"] for item in state["pending"]] == [second]
    assert first != second


def test_insecure_tls_is_explicit_and_only_disables_https_verification(monkeypatch):
    captured = {}

    class _Response:
        status = 201

        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return False

    def _urlopen(_request, **kwargs):
        captured.update(kwargs)
        return _Response()

    monkeypatch.setenv(
        "JIUWENSWARM_TELEMETRY_URL",
        "https://monitor.example.com/v1/launches",
    )
    monkeypatch.setenv("JIUWENSWARM_TELEMETRY_INSECURE_TLS", "1")
    monkeypatch.setattr(daily_activity.urllib.request, "urlopen", _urlopen)

    assert daily_activity._post_event({"event_id": str(uuid.uuid4())}) is True
    context = captured["context"]
    assert isinstance(context, ssl.SSLContext)
    assert context.check_hostname is False
    assert context.verify_mode == ssl.CERT_NONE


def test_tls_verification_stays_enabled_by_default(monkeypatch):
    captured = {}

    class _Response:
        status = 201

        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return False

    def _urlopen(_request, **kwargs):
        captured.update(kwargs)
        return _Response()

    monkeypatch.setenv(
        "JIUWENSWARM_TELEMETRY_URL",
        "https://monitor.example.com/v1/launches",
    )
    monkeypatch.delenv("JIUWENSWARM_TELEMETRY_INSECURE_TLS", raising=False)
    monkeypatch.setattr(daily_activity.urllib.request, "urlopen", _urlopen)

    assert daily_activity._post_event({"event_id": str(uuid.uuid4())}) is True
    assert captured["context"] is None


def test_builtin_monitor_accepts_its_generated_self_signed_certificate(monkeypatch):
    captured = {}

    class _Response:
        status = 201

        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return False

    def _urlopen(request, **kwargs):
        captured["url"] = request.full_url
        captured.update(kwargs)
        return _Response()

    monkeypatch.delenv("JIUWENSWARM_TELEMETRY_URL", raising=False)
    monkeypatch.delenv("JIUWENSWARM_TELEMETRY_INSECURE_TLS", raising=False)
    monkeypatch.setattr(daily_activity.urllib.request, "urlopen", _urlopen)

    assert daily_activity._post_event({"event_id": str(uuid.uuid4())}) is True
    assert captured["url"] == "https://117.78.11.91/v1/launches"
    context = captured["context"]
    assert isinstance(context, ssl.SSLContext)
    assert context.check_hostname is False
    assert context.verify_mode == ssl.CERT_NONE


def test_builtin_monitor_can_require_strict_tls_explicitly(monkeypatch):
    captured = {}

    class _Response:
        status = 201

        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return False

    def _urlopen(_request, **kwargs):
        captured.update(kwargs)
        return _Response()

    monkeypatch.delenv("JIUWENSWARM_TELEMETRY_URL", raising=False)
    monkeypatch.setenv("JIUWENSWARM_TELEMETRY_INSECURE_TLS", "0")
    monkeypatch.setattr(daily_activity.urllib.request, "urlopen", _urlopen)

    assert daily_activity._post_event({"event_id": str(uuid.uuid4())}) is True
    assert captured["context"] is None


def test_child_process_env_preserves_values_and_sets_marker(monkeypatch):
    monkeypatch.setenv("EXISTING_VALUE", "yes")
    env = daily_activity.child_process_env()
    assert env["EXISTING_VALUE"] == "yes"
    assert env["JIUWENSWARM_TELEMETRY_CHILD"] == "1"
