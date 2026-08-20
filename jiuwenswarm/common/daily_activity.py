# Copyright (c) Huawei Technologies Co., Ltd. 2026. All rights reserved.
"""Privacy-preserving JiuwenSwarm launch telemetry.

Only anonymous product/runtime metadata is collected.  Events are persisted
before a best-effort background upload so telemetry can never block startup and
short-lived/offline launches can be retried on the next run.
"""

from __future__ import annotations

import contextlib
import datetime as dt
import json
import locale
import os
import platform
import ssl
import sys
import threading
import urllib.request
import uuid
from importlib import resources
from pathlib import Path
from typing import Any, Iterator

from jiuwenswarm.common.version import __version__
from tzlocal import get_localzone_name


DEFAULT_TELEMETRY_URL = "https://4.145.114.205/v1/launches"
TELEMETRY_DISABLED_ENV = "JIUWENSWARM_TELEMETRY_DISABLED"
TELEMETRY_URL_ENV = "JIUWENSWARM_TELEMETRY_URL"
TELEMETRY_INSECURE_TLS_ENV = "JIUWENSWARM_TELEMETRY_INSECURE_TLS"
TELEMETRY_CHILD_ENV = "JIUWENSWARM_TELEMETRY_CHILD"
_MAX_PENDING_EVENTS = 2048
_REQUEST_TIMEOUT_SECONDS = 3.0

_process_guard = threading.Lock()
_reported_in_process = False

_MIDDLE_EAST_COUNTRIES = frozenset(
    {"AE", "BH", "CY", "EG", "IL", "IQ", "IR", "JO", "KW", "LB", "OM", "PS", "QA", "SA", "SY", "TR", "YE"}
)
_SOUTH_AMERICA_COUNTRIES = frozenset(
    {"AR", "BO", "BR", "CL", "CO", "EC", "FK", "GF", "GY", "PE", "PY", "SR", "UY", "VE"}
)


def telemetry_state_dir() -> Path:
    """Return the per-user telemetry state directory."""
    data_root = os.environ.get("JIUWENSWARM_DATA_DIR", "").strip()
    root = Path(data_root).expanduser() if data_root else Path.home() / ".jiuwenswarm"
    return root / "telemetry"


def _state_path() -> Path:
    return telemetry_state_dir() / "state.json"


def _lock_path() -> Path:
    return telemetry_state_dir() / "state.lock"


def _is_disabled() -> bool:
    return _env_flag(TELEMETRY_DISABLED_ENV)


def _env_flag(name: str) -> bool:
    return os.environ.get(name, "").strip().lower() in {
        "1",
        "true",
        "yes",
        "on",
    }


def _is_child_process() -> bool:
    return os.environ.get(TELEMETRY_CHILD_ENV, "").strip() == "1"


def _ensure_state_dir() -> None:
    directory = telemetry_state_dir()
    directory.mkdir(parents=True, exist_ok=True)
    if os.name != "nt":
        with contextlib.suppress(OSError):
            directory.chmod(0o700)


@contextlib.contextmanager
def _state_lock() -> Iterator[None]:
    """Serialize state changes across launcher processes."""
    _ensure_state_dir()
    try:
        import portalocker
    except ImportError:
        # portalocker is a JiuwenSwarm dependency, but retaining this fallback
        # keeps telemetry harmless in reduced/custom builds.
        yield
        return
    with portalocker.Lock(str(_lock_path()), mode="a", timeout=1.0):
        yield


def _new_state() -> dict[str, Any]:
    return {
        "schema_version": 1,
        "installation_id": str(uuid.uuid4()),
        "pending": [],
    }


def _valid_uuid(value: object) -> bool:
    try:
        uuid.UUID(str(value))
    except (ValueError, TypeError, AttributeError):
        return False
    return True


def _read_state_unlocked() -> dict[str, Any]:
    path = _state_path()
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError):
        return _new_state()

    if not isinstance(raw, dict) or not _valid_uuid(raw.get("installation_id")):
        return _new_state()
    pending = raw.get("pending")
    if not isinstance(pending, list):
        pending = []
    return {
        "schema_version": 1,
        "installation_id": str(raw["installation_id"]),
        "pending": [item for item in pending if isinstance(item, dict)][-_MAX_PENDING_EVENTS:],
    }


def _write_state_unlocked(state: dict[str, Any]) -> None:
    _ensure_state_dir()
    path = _state_path()
    temp_path = path.with_name(f".{path.name}.{os.getpid()}.{threading.get_ident()}.tmp")
    temp_path.write_text(
        json.dumps(state, ensure_ascii=False, separators=(",", ":")),
        encoding="utf-8",
    )
    if os.name != "nt":
        with contextlib.suppress(OSError):
            temp_path.chmod(0o600)
    os.replace(temp_path, path)


def _normalize_machine(machine: str) -> str:
    value = machine.strip().lower()
    if value in {"amd64", "x86_64"}:
        return "x64"
    if value in {"aarch64", "arm64"}:
        return "arm64"
    return value or "unknown"


def _distribution() -> str:
    if getattr(sys, "frozen", False):
        if sys.platform == "darwin":
            return "dmg"
        if os.name == "nt":
            return "exe"
        return "bundle"

    module_parts = {part.lower() for part in Path(__file__).resolve().parts}
    if "site-packages" in module_parts or "dist-packages" in module_parts:
        return "pypi"
    return "source"


def _timezone_name(now: dt.datetime) -> str:
    try:
        name = get_localzone_name().strip()
    except Exception:  # noqa: BLE001 - locale metadata must stay best-effort
        name = ""
    if name:
        return name[:64]
    tzinfo = now.tzinfo
    key = getattr(tzinfo, "key", "")
    if key:
        return str(key)[:64]
    return str(tzinfo or "UTC")[:64]


def _read_zone_tab() -> str:
    """Read the IANA timezone-to-country table without network access."""
    try:
        zone_tab = resources.files("tzdata").joinpath("zoneinfo/zone.tab")
        return zone_tab.read_text(encoding="utf-8")
    except (ImportError, ModuleNotFoundError, OSError, UnicodeError):
        pass
    for path in (
        Path("/usr/share/zoneinfo/zone.tab"),
        Path("/usr/share/lib/zoneinfo/tab/zone_sun.tab"),
    ):
        try:
            return path.read_text(encoding="utf-8")
        except (OSError, UnicodeError):
            continue
    return ""


def _country_code_from_timezone(
    timezone_name: str,
    zone_tab_text: str | None = None,
) -> str:
    """Return an ISO 3166-1 alpha-2 code for an exact IANA timezone."""
    table = _read_zone_tab() if zone_tab_text is None else zone_tab_text
    for raw_line in table.splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        columns = line.split("\t")
        if len(columns) >= 3 and columns[2] == timezone_name:
            return columns[0].split(",", 1)[0].upper()[:2]
    return ""


def _country_code_from_locale() -> str:
    """Best-effort ISO country code fallback for reduced/frozen builds."""
    locale_names: list[str] = []
    if os.name == "nt":
        try:
            import ctypes

            buffer = ctypes.create_unicode_buffer(85)
            if ctypes.windll.kernel32.GetUserDefaultLocaleName(buffer, len(buffer)):
                locale_names.append(buffer.value)
        except (AttributeError, OSError):
            pass
    current_locale = locale.getlocale()[0]
    if current_locale:
        locale_names.append(current_locale)
    locale_names.extend(
        os.environ.get(name, "") for name in ("LC_ALL", "LC_MESSAGES", "LANG")
    )
    for name in locale_names:
        normalized = name.split(".", 1)[0].split("@", 1)[0].replace("-", "_")
        candidate = normalized.rsplit("_", 1)[-1].upper()
        if len(candidate) == 2 and candidate.isalpha():
            return candidate
    return ""


def _region_from_timezone(timezone_name: str, country: str) -> str:
    """Return a coarse reporting region from timezone and country metadata."""
    if country in _MIDDLE_EAST_COUNTRIES:
        return "Middle East"
    if country in _SOUTH_AMERICA_COUNTRIES:
        return "South America"
    prefix = timezone_name.split("/", 1)[0]
    if prefix == "Africa":
        return "Africa"
    if prefix == "Europe":
        return "Europe"
    if prefix in {"America", "Atlantic"}:
        return "North America"
    if prefix in {"Asia", "Australia", "Indian", "Pacific"}:
        return "Asia Pacific"
    return ""


def _coarse_location(timezone_name: str) -> tuple[str, str]:
    country = _country_code_from_timezone(timezone_name) or _country_code_from_locale()
    return _region_from_timezone(timezone_name, country), country


def _build_event(installation_id: str, entrypoint: str) -> dict[str, Any]:
    now = dt.datetime.now().astimezone()
    system = platform.system() or "Unknown"
    release = platform.release()
    timezone_name = _timezone_name(now)
    region, country = _coarse_location(timezone_name)
    return {
        "schema_version": 1,
        "event_id": str(uuid.uuid4()),
        "installation_id": installation_id,
        "product": "jiuwenswarm",
        "event": "app_launch",
        "occurred_at": now.isoformat(),
        "timezone": timezone_name,
        "region": region,
        "country": country,
        "version": __version__,
        "os": f"{system} {release}".strip()[:128],
        "arch": _normalize_machine(platform.machine())[:32],
        "distribution": _distribution(),
        "entrypoint": entrypoint.strip().lower()[:32] or "unknown",
    }


def _enqueue_launch(entrypoint: str) -> str:
    with _state_lock():
        state = _read_state_unlocked()
        event = _build_event(state["installation_id"], entrypoint)
        state["pending"].append(event)
        state["pending"] = state["pending"][-_MAX_PENDING_EVENTS:]
        _write_state_unlocked(state)
    return str(event["event_id"])


def _pending_snapshot() -> list[dict[str, Any]]:
    with _state_lock():
        return list(_read_state_unlocked()["pending"])


def _remove_pending(event_id: str) -> None:
    with _state_lock():
        state = _read_state_unlocked()
        state["pending"] = [
            item for item in state["pending"] if item.get("event_id") != event_id
        ]
        _write_state_unlocked(state)


def _post_event(event: dict[str, Any]) -> bool:
    endpoint = os.environ.get(TELEMETRY_URL_ENV, DEFAULT_TELEMETRY_URL).strip()
    if not endpoint:
        return False
    tls_context = None
    if endpoint.lower().startswith("https://") and _env_flag(
        TELEMETRY_INSECURE_TLS_ENV
    ):
        # Explicit test-only escape hatch for self-signed monitoring stacks.
        # Production telemetry must leave this unset and use a trusted cert.
        tls_context = ssl.create_default_context()
        tls_context.check_hostname = False
        tls_context.verify_mode = ssl.CERT_NONE
    request = urllib.request.Request(
        endpoint,
        data=json.dumps(event, ensure_ascii=False).encode("utf-8"),
        headers={
            "Content-Type": "application/json",
            "User-Agent": f"JiuwenSwarm/{__version__}",
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(
            request,
            timeout=_REQUEST_TIMEOUT_SECONDS,
            context=tls_context,
        ) as response:
            return 200 <= int(response.status) < 300
    except Exception:  # noqa: BLE001 - telemetry must never affect the product
        return False


def flush_pending() -> int:
    """Best-effort upload of queued events; return the number acknowledged."""
    if _is_disabled() or _is_child_process():
        return 0
    sent = 0
    for event in _pending_snapshot():
        event_id = str(event.get("event_id") or "")
        if not event_id or not _post_event(event):
            break
        _remove_pending(event_id)
        sent += 1
    return sent


def _start_flush_thread() -> None:
    thread = threading.Thread(
        target=flush_pending,
        name="jiuwenswarm-telemetry",
        daemon=True,
    )
    thread.start()


def report_launch(entrypoint: str) -> str | None:
    """Queue one top-level launch and start a non-blocking upload attempt.

    The per-process guard protects callers that converge through more than one
    Python entry point.  Separate user launches still receive separate event
    IDs and therefore increment launch frequency independently.
    """
    global _reported_in_process
    if _is_disabled() or _is_child_process():
        return None
    with _process_guard:
        if _reported_in_process:
            return None
        try:
            event_id = _enqueue_launch(entrypoint)
        except Exception:  # noqa: BLE001 - telemetry must never affect startup
            return None
        _reported_in_process = True
    _start_flush_thread()
    return event_id


def child_process_env(env: dict[str, str] | None = None) -> dict[str, str]:
    """Return an environment marking a spawned process as non-user-facing."""
    result = dict(os.environ if env is None else env)
    result[TELEMETRY_CHILD_ENV] = "1"
    return result


def _reset_process_guard_for_tests() -> None:
    global _reported_in_process
    _reported_in_process = False
