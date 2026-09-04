"""Centralized App_Rpt radio-activity telemetry and transition tracking."""

import json
import os
import tempfile
from datetime import datetime, timezone
from pathlib import Path

from config import load_config
from event_logger import emit
import node_metadata


CONFIG = load_config()
NODE = str(CONFIG["node"])
NODE_NAMES = {str(key): value for key, value in CONFIG.get("friendly_nodes", {}).items()}
RADIO_CONFIG = CONFIG.get("radio_activity", {})
STALE_SECONDS = max(4, int(RADIO_CONFIG.get("stale_seconds", 6)))
STATE_FILE = Path("/opt/nodesmart/state/radio_activity.json")


def utc_now():
    return datetime.now(timezone.utc)


def parse_variables(output):
    """Parse App_Rpt variables, including direct-link K/U receive state."""
    values = {}
    for raw_line in output.splitlines():
        line = raw_line.strip()
        if line.startswith("RPT_") and "=" in line:
            key, value = line.split("=", 1)
            values[key] = value.strip()

    if "RPT_RXKEYED" not in values or "RPT_TXKEYED" not in values:
        return None

    def boolean(name):
        value = values.get(name)
        return value == "1" if value in ("0", "1") else None

    local_rx = boolean("RPT_RXKEYED")
    local_tx = boolean("RPT_TXKEYED")
    if local_rx is None or local_tx is None:
        return None

    links = []
    raw_links = values.get("RPT_ALINKS", "0")
    parts = [part.strip() for part in raw_links.split(",") if part.strip()]
    for encoded in parts[1:]:
        if len(encoded) < 3:
            continue
        node, mode, keyed = encoded[:-2], encoded[-2], encoded[-1]
        if node.isdigit() and mode in "TRC" and keyed in "KU":
            links.append({"node": node, "mode": mode, "keyed": keyed == "K"})

    return {"local_rx": local_rx, "local_tx": local_tx, "links": links}


def classify(sample):
    """Classify activity without treating mere connectivity as transmission."""
    if sample is None:
        return {"status": "unavailable", "telemetry_available": False,
                "local_rx": None, "local_tx": None, "connected_nodes": [],
                "remote_rx_nodes": []}

    connected = [link["node"] for link in sample["links"]]
    remote = [link["node"] for link in sample["links"]
              if link["keyed"] and link["mode"] != "C"]
    if sample["local_rx"]:
        status = "local_rx"
    elif len(remote) == 1:
        status = "remote_tx"
    elif len(remote) > 1:
        status = "ambiguous"
    elif sample["local_tx"]:
        status = "node_tx"
    else:
        status = "idle"

    result = {
        "status": status,
        "telemetry_available": True,
        "local_rx": sample["local_rx"],
        "local_tx": sample["local_tx"],
        "connected_nodes": connected,
        "remote_rx_nodes": remote,
    }
    if status == "local_rx":
        result.update({"node": NODE, "friendly_name": ""})
    elif status == "remote_tx":
        node = remote[0]
        result.update({"node": node, "friendly_name": NODE_NAMES.get(node, "")})
        metadata = node_metadata.lookup(node)
        result["metadata"] = {
            key: metadata[key] for key in ("status", "source", "fetched_at")
            if key in metadata
        }
        if metadata.get("status") == "available":
            for key in ("callsign", "description", "location", "display_location",
                        "latitude", "longitude"):
                if key in metadata:
                    result[key] = metadata[key]
    return result


def load_state():
    try:
        with STATE_FILE.open() as file:
            data = json.load(file)
        return data if isinstance(data, dict) else {}
    except (OSError, json.JSONDecodeError):
        return {}


def save_state(state):
    """Atomically publish current activity for the health loop and dashboard."""
    STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
    fd, name = tempfile.mkstemp(prefix=".radio-", suffix=".tmp", dir=STATE_FILE.parent)
    try:
        with os.fdopen(fd, "w") as file:
            json.dump(state, file, indent=2)
            file.flush()
            os.fsync(file.fileno())
        os.replace(name, STATE_FILE)
    except Exception:
        try:
            os.unlink(name)
        except OSError:
            pass
        raise


def _identity(state):
    status = state.get("status")
    if status == "remote_tx":
        return status, state.get("node")
    if status == "ambiguous":
        return status, tuple(state.get("remote_rx_nodes", []))
    return status, None


def _transition_event(state, transition):
    status = state.get("status")
    if status == "local_rx":
        return f"RADIO.LOCAL_RX.{transition}", f"Local receiver {transition.lower()}"
    if status == "remote_tx":
        node = state.get("node")
        name = state.get("friendly_name")
        label = f"{name} ({node})" if name else f"Node {node}"
        return f"RADIO.REMOTE_TX.{transition}", f"{label} audio {transition.lower()}"
    if status == "ambiguous":
        nodes = ", ".join(state.get("remote_rx_nodes", []))
        return f"RADIO.REMOTE_TX.{transition}", f"Multiple keyed links {transition.lower()}: {nodes}"
    return None


def update(sample, now=None):
    now = utc_now() if now is None else now
    previous = load_state()
    current = classify(sample)
    current["last_update"] = now.isoformat()
    current["stale_after_seconds"] = STALE_SECONDS

    previous_identity = _identity(previous)
    current_identity = _identity(current)
    if current_identity == previous_identity and current["status"] not in ("idle", "unavailable"):
        current["started_at"] = previous.get("started_at", now.isoformat())
    elif current["status"] not in ("idle", "unavailable"):
        current["started_at"] = now.isoformat()

    if previous_identity != current_identity:
        ended = _transition_event(previous, "END")
        started = _transition_event(current, "START")
        if ended:
            emit(*ended)
        if started:
            emit(*started)

    save_state(current)
    return current


def public_state(now=None):
    """Return state, clearing activity safely when its collector is stale."""
    now = utc_now() if now is None else now
    state = load_state()
    try:
        updated = datetime.fromisoformat(state["last_update"])
        age = (now - updated).total_seconds()
    except (KeyError, TypeError, ValueError):
        age = STALE_SECONDS + 1
    try:
        stale_after = max(1, int(state.get("stale_after_seconds", STALE_SECONDS)))
    except (TypeError, ValueError):
        stale_after = STALE_SECONDS
    if age > stale_after:
        return {"status": "unavailable", "telemetry_available": False,
                "local_rx": None, "local_tx": None, "connected_nodes": [],
                "remote_rx_nodes": [], "last_update": state.get("last_update"),
                "stale": True, "stale_after_seconds": STALE_SECONDS}
    state["stale"] = False
    return state
