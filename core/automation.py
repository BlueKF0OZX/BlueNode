#!/usr/bin/env python3

"""Persist and coordinate BlueNode automated operations state."""

import copy
import json
import os
import tempfile
import threading
import time
from contextlib import contextmanager
from functools import wraps
from datetime import datetime, timezone
from pathlib import Path

from config import load_config
from event_logger import emit
import asterisk_observation

try:
    import fcntl
except ImportError:  # Windows test runtime
    fcntl = None


RECOVERY_ENABLED = load_config().get("recovery", {}).get("asterisk_enabled", False) is True
CONFIG = load_config().get("automation", {})
STATE_FILE = Path("/opt/nodesmart/state/automation.json")

ATTEMPT_WINDOW_SECONDS = int(CONFIG.get("attempt_window_seconds", 3600))
MAX_ATTEMPTS = int(CONFIG.get("max_attempts", 3))
MIN_COOLDOWN_SECONDS = int(CONFIG.get("minimum_cooldown_seconds", 600))
MAX_BACKOFF_SECONDS = int(CONFIG.get("maximum_backoff_seconds", 3600))
HEALTHY_RESET_SECONDS = int(CONFIG.get("healthy_reset_seconds", 900))

DEFAULT_STATE = {
    "version": 1,
    "mode": "active",
    "maintenance_mode": False,
    "recent_recovery_attempts": [],
    "consecutive_failures": 0,
    "cooldown_until": 0,
    "backoff_until": 0,
    "healthy_since": None,
    "last_automation_check": None,
    "last_action": None,
    "last_result": None,
    "last_verification": None,
    "escalation_reason": None,
    "connectivity_status": "unavailable",
    "connectivity_failure_domain": "unavailable",
    "connectivity_action": "monitoring_only",
    "recovery_safety_message": None,
}
MAX_STATE_BYTES = 256 * 1024
MAX_EPOCH = 253402214400  # Representable UTC timestamp, before the end of year 9999.
INVALID_STATE_REASON = 'Automatic recovery inhibited: automation safety state is missing or invalid; restore a verified state file.'
_THREAD_LOCK = threading.RLock()


@contextmanager
def state_lock():
    STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
    lock_file = STATE_FILE.with_suffix(".lock")
    with _THREAD_LOCK, lock_file.open("a+") as handle:
        if fcntl is not None:
            fcntl.flock(handle.fileno(), fcntl.LOCK_EX)
        try:
            yield
        finally:
            if fcntl is not None:
                fcntl.flock(handle.fileno(), fcntl.LOCK_UN)


def locked(function):
    @wraps(function)
    def wrapper(*args, **kwargs):
        with state_lock():
            return function(*args, **kwargs)
    return wrapper


def utc_now():
    return datetime.now(timezone.utc)


def default_state():
    return copy.deepcopy(DEFAULT_STATE)


def invalid_state():
    state = default_state()
    state.update(safety_state_valid=False, mode='attention', maintenance_mode=True,
                 recovery_safety_message=INVALID_STATE_REASON,
                 escalation_reason=INVALID_STATE_REASON, last_result=INVALID_STATE_REASON)
    return state


def _normalized(data):
    # No coercion or missing-field defaults for fields that authorize recovery.
    required = {'version', 'mode', 'maintenance_mode', 'recent_recovery_attempts',
                'consecutive_failures', 'cooldown_until', 'backoff_until', 'healthy_since'}
    if not isinstance(data, dict) or not required.issubset(data):
        return invalid_state()
    if data.get('safety_state_valid', True) is not True:
        return invalid_state()
    if type(data['version']) is not int or data['version'] != 1:
        return invalid_state()
    if data['mode'] not in ('active', 'maintenance', 'recovering', 'recovered', 'attention'):
        return invalid_state()
    if type(data['maintenance_mode']) is not bool:
        return invalid_state()
    if data['mode'] == 'maintenance' and not data['maintenance_mode']:
        return invalid_state()
    for key in ('cooldown_until', 'backoff_until', 'consecutive_failures'):
        value = data[key]
        limit = 1000 if key == 'consecutive_failures' else MAX_EPOCH
        if type(value) is not int or not 0 <= value <= limit:
            return invalid_state()
    attempts = data['recent_recovery_attempts']
    if (not isinstance(attempts, list) or len(attempts) > 4096 or
            any(type(stamp) is not int or not 0 <= stamp <= MAX_EPOCH for stamp in attempts)):
        return invalid_state()
    for key in ('healthy_since', 'last_automation_check'):
        value = data.get(key)
        if value is not None:
            try:
                if not isinstance(value, str):
                    return invalid_state()
                datetime.fromisoformat(value).timestamp()
            except (ValueError, OverflowError, OSError):
                return invalid_state()
    for key, default in DEFAULT_STATE.items():
        if (key not in required and key not in ('last_verification', 'last_automation_check')
                and data.get(key) is not None and not isinstance(data[key], str)):
            return invalid_state()
    verification = data.get('last_verification')
    if verification is not None and (not isinstance(verification, dict) or
            type(verification.get('passed')) is not bool or
            not isinstance(verification.get('message'), str) or
            not isinstance(verification.get('timestamp'), str)):
        return invalid_state()
    state = default_state()
    state.update({key: copy.deepcopy(data[key]) for key in state if key in data})
    state['safety_state_valid'] = True
    return state


def load_state():
    try:
        with STATE_FILE.open('rb') as file:
            raw = file.read(MAX_STATE_BYTES + 1)
        if len(raw) > MAX_STATE_BYTES:
            return invalid_state()
        return _normalized(json.loads(raw.decode('utf-8')))
    except (OSError, ValueError, TypeError, RecursionError):
        return invalid_state()


def save_state(state):
    state = _normalized(state)
    if not state['safety_state_valid']:
        return state  # Never overwrite corrupt evidence with permissive defaults.
    STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w", encoding="utf-8", dir=STATE_FILE.parent,
            delete=False, suffix=".tmp"
        ) as file:
            temporary = Path(file.name)
            json.dump(state, file, indent=2)
            file.flush()
            os.fsync(file.fileno())
        os.replace(temporary, STATE_FILE)
    finally:
        if temporary is not None and temporary.exists():
            temporary.unlink()
    return state


def _prune(state, now):
    state["recent_recovery_attempts"] = [
        stamp for stamp in state["recent_recovery_attempts"]
        if now - stamp < max(86400, ATTEMPT_WINDOW_SECONDS)
    ]


def _window_attempts(state, now):
    return [stamp for stamp in state["recent_recovery_attempts"]
            if now - stamp < ATTEMPT_WINDOW_SECONDS]


def _iso(epoch):
    return datetime.fromtimestamp(epoch, timezone.utc).isoformat() if epoch else None


def public_state(state=None, now=None):
    state = load_state() if state is None else _normalized(state)
    now = int(time.time() if now is None else now)
    _prune(state, now)
    attempts_today = sum(1 for stamp in state["recent_recovery_attempts"]
                         if now - stamp < 86400)
    result = dict(state)
    result.update({
        "recovery_enabled": RECOVERY_ENABLED,
        "automation_armed": (
            RECOVERY_ENABLED and state['safety_state_valid'] and not state["maintenance_mode"]
            and state["backoff_until"] <= now and state["cooldown_until"] <= now
        ),
        "repeated_failure_protection": True,
        "recovery_attempts_today": attempts_today,
        "cooldown_until_iso": _iso(state["cooldown_until"]),
        "backoff_until_iso": _iso(state["backoff_until"]),
        "operator_attention_required": state["mode"] == "attention",
    })
    if not state['safety_state_valid']:
        result.update(maintenance_mode=None, recovery_attempts_today=None,
                      repeated_failure_protection=False)
        result.pop('cooldown_until_iso', None)
        result.pop('backoff_until_iso', None)
    return result


@locked
def observe_health(health, now=None):
    now = int(time.time() if now is None else now)
    state = load_state()
    if not state.get('safety_state_valid', True):
        return public_state(state, now)
    _prune(state, now)
    state["last_automation_check"] = datetime.fromtimestamp(now, timezone.utc).isoformat()
    connectivity = health.get("connectivity") or {}
    state["connectivity_status"] = connectivity.get("status", "unavailable")
    state["connectivity_failure_domain"] = connectivity.get("failure_domain", "unavailable")
    state["connectivity_action"] = "monitoring_only"
    evidence = health.get("asterisk_evidence")
    state["recovery_safety_message"] = None
    if evidence and asterisk_observation.warning(evidence) and health.get("asterisk") != "offline":
        state["recovery_safety_message"] = "Automatic restart prohibited: no confirmed stopped-service evidence."
    healthy = (health.get("asterisk") == "online"
               and health.get("health", {}).get("asterisk_query", "normal") == "normal"
               and health.get("health", {}).get("app_rpt", "normal") == "normal")
    if healthy:
        if not state.get("healthy_since"):
            state["healthy_since"] = state["last_automation_check"]
        try:
            since = datetime.fromisoformat(state["healthy_since"]).timestamp()
        except (TypeError, ValueError):
            since = now
            state["healthy_since"] = state["last_automation_check"]
        if now - since >= HEALTHY_RESET_SECONDS and (
            state["recent_recovery_attempts"] or state["consecutive_failures"]
            or state["backoff_until"] or state["cooldown_until"]
        ):
            state["recent_recovery_attempts"] = []
            state["consecutive_failures"] = 0
            state["backoff_until"] = 0
            state["cooldown_until"] = 0
            state["escalation_reason"] = None
            state["mode"] = "maintenance" if state["maintenance_mode"] else "active"
            state["last_action"] = "Backoff reset"
            state["last_result"] = "Sustained healthy operation restored normal automation"
            emit("AUTOMATION.BACKOFF.RESET", state["last_result"])
        elif state["mode"] == "recovered" and now - since >= HEALTHY_RESET_SECONDS:
            state["mode"] = "maintenance" if state["maintenance_mode"] else "active"
    else:
        state["healthy_since"] = None
    if state["maintenance_mode"]:
        state["mode"] = "maintenance"
    return public_state(save_state(state), now)


@locked
def set_maintenance(enabled, now=None):
    state = load_state()
    if not state.get('safety_state_valid', True):
        return public_state(state, now)
    enabled = bool(enabled)
    if state["maintenance_mode"] != enabled:
        state["maintenance_mode"] = enabled
        state["mode"] = "maintenance" if enabled else "active"
        state["last_action"] = "Maintenance mode enabled" if enabled else "Maintenance mode disabled"
        state["last_result"] = (
            "Monitoring continues; automatic actions are suspended" if enabled
            else "Maintenance ended; configured automatic-recovery policy applies"
        )
        emit("AUTOMATION.MAINTENANCE.ENABLED" if enabled else
             "AUTOMATION.MAINTENANCE.DISABLED", state["last_result"])
    return public_state(save_state(state), now)


@locked
def recovery_allowed(health, now=None):
    observation_now = time.time() if now is None else now
    now = int(observation_now)
    state = load_state()
    if not state.get('safety_state_valid', True):
        return False
    _prune(state, now)
    evidence = health.get("asterisk_evidence", {})
    if (not asterisk_observation.confirmed_stopped(evidence.get("service"), observation_now)
            or evidence.get("query", {}).get("status") == "available"):
        return False
    if health.get("asterisk") != "offline" or state["maintenance_mode"]:
        return False
    if state["backoff_until"] > now or state["cooldown_until"] > now:
        return False
    window = _window_attempts(state, now)
    if len(window) >= MAX_ATTEMPTS:
        state["backoff_until"] = now + MAX_BACKOFF_SECONDS
        state["mode"] = "attention"
        state["escalation_reason"] = (
            f"{len(window)} recovery attempts within "
            f"{ATTEMPT_WINDOW_SECONDS // 60} minutes"
        )
        state["last_action"] = "Automatic recovery backed off"
        state["last_result"] = state["escalation_reason"]
        save_state(state)
        emit("AUTOMATION.RECOVERY.ESCALATED", state["escalation_reason"])
        emit("AUTOMATION.BACKOFF.ENTERED",
             f"Recovery paused for up to {MAX_BACKOFF_SECONDS // 60} minutes")
        return False
    return True


@locked
def begin_recovery(now=None):
    now = int(time.time() if now is None else now)
    state = load_state()
    if not state.get('safety_state_valid', True):
        return None
    _prune(state, now)
    if state["maintenance_mode"] or state["backoff_until"] > now or state["cooldown_until"] > now:
        return None
    state["recent_recovery_attempts"].append(now)
    attempt = len(_window_attempts(state, now))
    state["mode"] = "recovering"
    state["healthy_since"] = None
    state["last_action"] = f"Recovery attempt {attempt} of {MAX_ATTEMPTS}"
    state["last_result"] = "Verifying service health"
    save_state(state)
    emit("AUTOMATION.RECOVERY.STARTED", state["last_action"])
    return attempt


@locked
def cancel_recovery(message):
    """Release a reserved attempt without claiming a restart or failed verification."""
    state = load_state()
    if not state.get('safety_state_valid', True):
        return public_state(state)
    if state["recent_recovery_attempts"]:
        state["recent_recovery_attempts"].pop()
    state["mode"] = "maintenance" if state["maintenance_mode"] else "active"
    state["last_action"] = "Recovery cancelled"
    state["last_result"] = message
    save_state(state)
    emit("AUTOMATION.RECOVERY.CANCELLED", message)


@locked
def finish_recovery(verified, message, now=None):
    now = int(time.time() if now is None else now)
    state = load_state()
    if not state.get('safety_state_valid', True):
        return public_state(state, now)
    state["last_verification"] = {
        "passed": bool(verified), "message": message,
        "timestamp": datetime.fromtimestamp(now, timezone.utc).isoformat(),
    }
    state["last_action"] = "Recovery verification passed" if verified else "Recovery verification failed"
    state["last_result"] = message
    if verified:
        state["healthy_since"] = state["last_verification"]["timestamp"]
        state["consecutive_failures"] = 0
        state["cooldown_until"] = now + MIN_COOLDOWN_SECONDS
        emit("AUTOMATION.RECOVERY.VERIFICATION.PASSED", message)
        window = _window_attempts(state, now)
        if len(window) >= MAX_ATTEMPTS:
            state["mode"] = "attention"
            state["backoff_until"] = now + MAX_BACKOFF_SECONDS
            state["escalation_reason"] = (
                f"{len(window)} recovery attempts within "
                f"{ATTEMPT_WINDOW_SECONDS // 60} minutes"
            )
            emit("AUTOMATION.RECOVERY.ESCALATED", state["escalation_reason"])
            emit("AUTOMATION.BACKOFF.ENTERED",
                 f"Recovery paused for up to {MAX_BACKOFF_SECONDS // 60} minutes")
        else:
            state["mode"] = "recovered"
    else:
        state["consecutive_failures"] += 1
        backoff = min(MAX_BACKOFF_SECONDS,
                      MIN_COOLDOWN_SECONDS * (2 ** min(30, max(0, state["consecutive_failures"] - 1))))
        state["cooldown_until"] = now + backoff
        if state["consecutive_failures"] >= 2 or len(_window_attempts(state, now)) >= MAX_ATTEMPTS:
            state["mode"] = "attention"
            state["backoff_until"] = now + backoff
            state["escalation_reason"] = "Repeated or failed recovery verification"
            emit("AUTOMATION.RECOVERY.ESCALATED", state["escalation_reason"])
            emit("AUTOMATION.BACKOFF.ENTERED", f"Recovery paused for {backoff} seconds")
        else:
            state["mode"] = "active"
        emit("AUTOMATION.RECOVERY.VERIFICATION.FAILED", message)
    return public_state(save_state(state), now)
