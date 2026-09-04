#!/usr/bin/env python3
"""Persist BlueNode's explicit operator-controlled Emergency Mode."""

import copy
import json
import os
import tempfile
import threading
import time
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path

from event_logger import emit

try:
    import fcntl
except ImportError:  # Windows test runtime
    fcntl = None


STATE_FILE = Path(os.environ.get(
    "BLUENODE_EMERGENCY_STATE_FILE",
    "/opt/nodesmart/state/emergency_mode.json",
))
_THREAD_LOCK = threading.RLock()
_SOURCES = {"local_dashboard", "remote_admin"}
DEFAULT_STATE = {
    "version": 1,
    "active": False,
    "mode": "normal",
    "activated_at": None,
    "activated_epoch": None,
    "activation_source": None,
    "last_transition_at": None,
}


def _iso(epoch):
    return datetime.fromtimestamp(epoch, timezone.utc).isoformat(timespec="seconds")


def default_state():
    return copy.deepcopy(DEFAULT_STATE)


def _normalized(value):
    if not isinstance(value, dict):
        return default_state()
    state = default_state()
    active = value.get("active") is True and value.get("mode") == "emergency"
    state["active"] = active
    state["mode"] = "emergency" if active else "normal"
    if active:
        try:
            epoch = int(value.get("activated_epoch"))
            if epoch < 0:
                raise ValueError
        except (TypeError, ValueError, OverflowError):
            return default_state()
        state["activated_epoch"] = epoch
        state["activated_at"] = _iso(epoch)
        source = value.get("activation_source")
        state["activation_source"] = source if source in _SOURCES else "local_dashboard"
    transition = value.get("last_transition_at")
    state["last_transition_at"] = transition if isinstance(transition, str) else None
    return state


@contextmanager
def state_lock():
    STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
    lock_path = STATE_FILE.with_suffix(".lock")
    with _THREAD_LOCK, lock_path.open("a+") as handle:
        if fcntl is not None:
            fcntl.flock(handle.fileno(), fcntl.LOCK_EX)
        try:
            yield
        finally:
            if fcntl is not None:
                fcntl.flock(handle.fileno(), fcntl.LOCK_UN)


def load_state():
    try:
        if STATE_FILE.is_symlink():
            return default_state()
        return _normalized(json.loads(STATE_FILE.read_text(encoding="utf-8")))
    except (OSError, TypeError, ValueError, json.JSONDecodeError):
        return default_state()


def save_state(state):
    state = _normalized(state)
    STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w", encoding="utf-8", dir=STATE_FILE.parent,
            delete=False, suffix=".tmp"
        ) as handle:
            temporary = Path(handle.name)
            json.dump(state, handle, indent=2)
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, STATE_FILE)
    finally:
        if temporary is not None and temporary.exists():
            temporary.unlink()
    return state


def public_state(state=None, now=None):
    state = load_state() if state is None else _normalized(state)
    now = int(time.time() if now is None else now)
    result = dict(state)
    result["elapsed_seconds"] = max(
        0, now - state["activated_epoch"]
    ) if state["active"] else 0
    return result


def set_emergency(active, source="local_dashboard", now=None):
    active = bool(active)
    source = source if source in _SOURCES else "local_dashboard"
    now = int(time.time() if now is None else now)
    with state_lock():
        state = load_state()
        if state["active"] == active:
            return public_state(state, now)
        state["active"] = active
        state["mode"] = "emergency" if active else "normal"
        state["last_transition_at"] = _iso(now)
        if active:
            state["activated_epoch"] = now
            state["activated_at"] = _iso(now)
            state["activation_source"] = source
        else:
            state["activated_epoch"] = None
            state["activated_at"] = None
            state["activation_source"] = None
        save_state(state)
    emit(
        "EMERGENCY.MODE.ACTIVATED" if active else "EMERGENCY.MODE.DEACTIVATED",
        "Operator entered Emergency Mode" if active else "Operator returned BlueNode to Normal Mode",
    )
    return public_state(state, now)
