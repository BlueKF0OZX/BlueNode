#!/usr/bin/env python3
"""Passive Node Behavior and Network Courtesy analysis."""

import copy
import json
import os
import re
import tempfile
import time
from datetime import datetime, timezone
from pathlib import Path

from config import load_config
from event_logger import emit


CONFIG = load_config().get("node_behavior", {})
STATE_FILE = Path("/opt/nodesmart/state/node_behavior.json")
EVENT_LOG = Path("/opt/nodesmart/logs/events.log")
ADMIN_AUDIT_LOG = Path("/opt/nodesmart/logs/admin-audit.jsonl")

EVALUATION_INTERVAL = max(5, int(CONFIG.get("evaluation_interval_seconds", 10)))
EVENT_WINDOW = max(60, int(CONFIG.get("event_window_seconds", 300)))
STALE_SECONDS = max(EVALUATION_INTERVAL * 3, int(CONFIG.get("stale_seconds", 60)))
LINK_SETTLE_SECONDS = max(5, int(CONFIG.get("link_settle_seconds", 20)))
RECONNECT_NOTICE = max(3, int(CONFIG.get("reconnect_notice_count", 5)))
RECONNECT_WARNING = max(RECONNECT_NOTICE + 1, int(CONFIG.get("reconnect_warning_count", 8)))
CHURN_NOTICE = max(4, int(CONFIG.get("churn_notice_count", 6)))
CHURN_WARNING = max(CHURN_NOTICE + 1, int(CONFIG.get("churn_warning_count", 10)))
FAILED_NOTICE = max(3, int(CONFIG.get("failed_link_notice_count", 4)))
FAILED_WARNING = max(FAILED_NOTICE + 1, int(CONFIG.get("failed_link_warning_count", 6)))
LOCAL_KEY_NOTICE = max(30, int(CONFIG.get("local_key_notice_seconds", 90)))
LOCAL_KEY_WARNING = max(LOCAL_KEY_NOTICE + 30, int(CONFIG.get("local_key_warning_seconds", 180)))
RAPID_WINDOW = max(30, int(CONFIG.get("rapid_key_window_seconds", 120)))
RAPID_NOTICE = max(6, int(CONFIG.get("rapid_key_notice_transitions", 10)))
RAPID_WARNING = max(RAPID_NOTICE + 2, int(CONFIG.get("rapid_key_warning_transitions", 16)))
CONTROL_NOTICE = max(6, int(CONFIG.get("control_notice_count", 12)))
CONTROL_WARNING = max(CONTROL_NOTICE + 2, int(CONFIG.get("control_warning_count", 20)))
AUTOMATION_WINDOW = max(300, int(CONFIG.get("automation_window_seconds", 3600)))
AUTOMATION_NOTICE = max(2, int(CONFIG.get("automation_notice_count", 2)))
AUTOMATION_WARNING = max(AUTOMATION_NOTICE + 1, int(CONFIG.get("automation_warning_count", 3)))
MAX_EVENT_BYTES = max(65536, int(CONFIG.get("maximum_event_bytes", 262144)))

DEFAULT_STATE = {
    "version": 1, "assessment": "normal", "reasons": [],
    "operator_review_recommended": False, "first_observed": None,
    "last_observed": None, "last_check": None, "freshness": "unavailable",
}
NODE_PATTERN = re.compile(r"(?:\bnode\s+|\()(\d+)\b", re.IGNORECASE)


def _iso(epoch):
    return datetime.fromtimestamp(epoch, timezone.utc).isoformat(timespec="seconds")


def default_state():
    return copy.deepcopy(DEFAULT_STATE)


def load_state():
    try:
        if STATE_FILE.is_symlink():
            return default_state()
        value = json.loads(STATE_FILE.read_text(encoding="utf-8"))
        return value if isinstance(value, dict) else default_state()
    except (OSError, ValueError, TypeError, json.JSONDecodeError):
        return default_state()


def save_state(state):
    STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8",
                                         dir=STATE_FILE.parent, delete=False,
                                         suffix=".tmp") as handle:
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


def _read_recent_events(now):
    try:
        with EVENT_LOG.open("rb") as handle:
            size = handle.seek(0, os.SEEK_END)
            handle.seek(max(0, size - MAX_EVENT_BYTES))
            raw = handle.read().decode("utf-8", errors="replace")
    except OSError:
        return []
    if size > MAX_EVENT_BYTES:
        raw = raw.split("\n", 1)[-1]
    events = []
    oldest = now - max(EVENT_WINDOW, AUTOMATION_WINDOW, RAPID_WINDOW)
    for line in raw.splitlines():
        parts = [part.strip() for part in line.split("|", 2)]
        if len(parts) != 3:
            continue
        try:
            stamp = datetime.fromisoformat(parts[0]).timestamp()
        except (ValueError, TypeError, OverflowError):
            continue
        if stamp >= oldest:
            events.append({"timestamp": stamp, "event": parts[1], "message": parts[2]})
    return events


def _read_admin_events(now):
    try:
        with ADMIN_AUDIT_LOG.open("rb") as handle:
            size = handle.seek(0, os.SEEK_END)
            handle.seek(max(0, size - MAX_EVENT_BYTES))
            raw = handle.read().decode("utf-8", errors="replace")
    except OSError:
        return []
    if size > MAX_EVENT_BYTES:
        raw = raw.split("\n", 1)[-1]
    events = []
    for line in raw.splitlines():
        try:
            record = json.loads(line)
            stamp = datetime.fromisoformat(record["timestamp"]).timestamp()
            action = str(record["action"])
            outcome = str(record["outcome"])
        except (KeyError, TypeError, ValueError, json.JSONDecodeError):
            continue
        if now - stamp <= EVENT_WINDOW and outcome == "success" and action not in {
                "login", "logout", "view-logs-bluenode", "view-logs-asterisk"}:
            events.append({"timestamp": stamp, "event": "ADMIN.CONTROL",
                           "message": action})
    return events


def _node(event):
    match = NODE_PATTERN.search(event.get("message", ""))
    return match.group(1) if match else None


def _finding(code, level, summary, evidence, now, **extra):
    result = {"code": code, "level": level, "summary": summary,
              "evidence": evidence, "last_observed": _iso(now)}
    result.update(extra)
    return result


def _level(count, notice, warning):
    return "warning" if count >= warning else "notice" if count >= notice else None


def analyze(events, radio, automation, connectivity, now=None):
    """Analyze supplied snapshots without taking any operational action."""
    now = float(time.time() if now is None else now)
    recent = [item for item in events if now - item["timestamp"] <= EVENT_WINDOW]
    findings = []

    # Accepted connection commands are attempts; matching NODE.CONNECTED events
    # prove establishment. No inference is made about why an attempt failed.
    attempts = [item for item in recent if item["event"] == "CONTROL.NODE.CONNECT"]
    by_node = {}
    failed = {}
    for attempt in attempts:
        node = _node(attempt)
        if not node:
            continue
        by_node.setdefault(node, []).append(attempt)
        if now - attempt["timestamp"] < LINK_SETTLE_SECONDS:
            continue
        established = any(
            item["event"] == "NODE.CONNECTED" and _node(item) == node
            and attempt["timestamp"] <= item["timestamp"]
            <= attempt["timestamp"] + LINK_SETTLE_SECONDS
            for item in recent
        )
        if not established:
            failed.setdefault(node, []).append(attempt)

    for node, node_attempts in by_node.items():
        count = len(node_attempts)
        level = _level(count, RECONNECT_NOTICE, RECONNECT_WARNING)
        if level:
            findings.append(_finding(
                "repeated_connection_attempts", level,
                "Repeated connection attempts observed",
                f"Node {node}: {count} attempts within {EVENT_WINDOW // 60} minutes",
                now, node=node, count=count, window_seconds=EVENT_WINDOW))
    for node, node_failures in failed.items():
        count = len(node_failures)
        level = _level(count, FAILED_NOTICE, FAILED_WARNING)
        if level:
            suffix = ""
            if connectivity.get("diagnosis") == "healthy":
                suffix = "; local connectivity and Asterisk are healthy"
            findings.append(_finding(
                "repeated_link_failures", level,
                "Repeated link establishment failures observed",
                f"Node {node}: {count} unconfirmed attempts within {EVENT_WINDOW // 60} minutes{suffix}",
                now, node=node, count=count, window_seconds=EVENT_WINDOW,
                confidence="accepted_command_without_observed_establishment"))

    transitions = [item for item in recent if item["event"] in
                   ("NODE.CONNECTED", "NODE.DISCONNECTED")]
    level = _level(len(transitions), CHURN_NOTICE, CHURN_WARNING)
    if level:
        findings.append(_finding(
            "connection_churn", level, "Rapid connection churn observed",
            f"{len(transitions)} connect/disconnect transitions within {EVENT_WINDOW // 60} minutes",
            now, count=len(transitions), window_seconds=EVENT_WINDOW))

    radio_fresh = radio.get("telemetry_available") is True and not radio.get("stale", False)
    if radio_fresh and radio.get("local_rx") is True:
        try:
            started = datetime.fromisoformat(radio["started_at"]).timestamp()
            duration = max(0, int(now - started))
        except (KeyError, TypeError, ValueError, OverflowError):
            duration = None
        if duration is not None:
            level = "warning" if duration >= LOCAL_KEY_WARNING else "notice" if duration >= LOCAL_KEY_NOTICE else None
            if level:
                findings.append(_finding(
                    "extended_local_rf", level, "Extended local RF activity",
                    f"Local receiver has remained keyed for {duration} seconds",
                    now, duration_seconds=duration))

    key_events = [item for item in events if now - item["timestamp"] <= RAPID_WINDOW
                  and item["event"] in ("RADIO.LOCAL_RX.START", "RADIO.LOCAL_RX.END")]
    level = _level(len(key_events), RAPID_NOTICE, RAPID_WARNING)
    if level:
        findings.append(_finding(
            "rapid_local_keying", level, "Rapid local RF key/unkey cycling observed",
            f"{len(key_events)} local receiver transitions within {RAPID_WINDOW} seconds",
            now, count=len(key_events), window_seconds=RAPID_WINDOW))

    controls = [item for item in recent if item["event"].startswith("CONTROL.")
                or item["event"] == "ADMIN.CONTROL"]
    level = _level(len(controls), CONTROL_NOTICE, CONTROL_WARNING)
    if level:
        findings.append(_finding(
            "frequent_controls", level, "Unusually frequent BlueNode control activity",
            f"{len(controls)} control actions within {EVENT_WINDOW // 60} minutes",
            now, count=len(controls), window_seconds=EVENT_WINDOW))

    automation_events = [item for item in events if now - item["timestamp"] <= AUTOMATION_WINDOW
                         and item["event"] in ("AUTOMATION.RECOVERY.STARTED",
                                              "RECOVERY.ASTERISK.ATTEMPT")]
    count = max(len(automation_events), len([
        stamp for stamp in automation.get("recent_recovery_attempts", [])
        if isinstance(stamp, (int, float)) and now - stamp <= AUTOMATION_WINDOW
    ]))
    level = _level(count, AUTOMATION_NOTICE, AUTOMATION_WARNING)
    if level:
        findings.append(_finding(
            "frequent_automation", level, "Repeated BlueNode recovery activity observed",
            f"{count} recovery attempts within {AUTOMATION_WINDOW // 60} minutes",
            now, count=count, window_seconds=AUTOMATION_WINDOW))

    rank = {"notice": 1, "warning": 2}
    assessment = max((item["level"] for item in findings),
                     key=lambda value: rank[value], default="normal")
    return {"assessment": assessment, "reasons": findings,
            "operator_review_recommended": assessment == "warning",
            "evidence_status": "observed" if findings else
            ("current" if radio_fresh else "partial"),
            "ambiguity": None if radio_fresh else
            "Local RF telemetry is unavailable or stale; RF behavior was not assessed"}


def observe(radio=None, automation=None, connectivity=None, now=None, events=None):
    now = float(time.time() if now is None else now)
    previous = load_state()
    try:
        prior_check = datetime.fromisoformat(previous.get("last_check", "")).timestamp()
    except (TypeError, ValueError):
        prior_check = 0
    if events is None and now - prior_check < EVALUATION_INTERVAL:
        return public_state(previous, now)
    collected = (_read_recent_events(now) + _read_admin_events(now)) if events is None else events
    result = analyze(collected,
                     radio or {}, automation or {}, connectivity or {}, now)
    previous_codes = {item.get("code") for item in previous.get("reasons", [])}
    current_codes = {item.get("code") for item in result["reasons"]}
    changed = previous.get("assessment") != result["assessment"] or previous_codes != current_codes
    if changed or not previous.get("first_observed"):
        result["first_observed"] = _iso(now)
    else:
        result["first_observed"] = previous.get("first_observed")
    result.update({"version": 1, "last_observed": _iso(now),
                   "last_check": _iso(now), "freshness": "current",
                   "stale_after_seconds": STALE_SECONDS})
    save_state(result)
    if changed:
        old = str(previous.get("assessment", "normal")).upper()
        new = result["assessment"].upper()
        summary = result["reasons"][0]["summary"] if result["reasons"] else "No unusual local or network activity detected"
        emit(f"BEHAVIOR.{new}", f"{old} -> {new} | {summary}")
    return public_state(result, now)


def public_state(state=None, now=None):
    state = load_state() if state is None else copy.deepcopy(state)
    now = float(time.time() if now is None else now)
    try:
        age = max(0, int(now - datetime.fromisoformat(state["last_check"]).timestamp()))
    except (KeyError, TypeError, ValueError, OverflowError):
        age = STALE_SECONDS + 1
    state["age_seconds"] = age
    state["stale"] = age > int(state.get("stale_after_seconds", STALE_SECONDS))
    if state["stale"]:
        state["freshness"] = "stale" if state.get("last_check") else "unavailable"
        state["operator_review_recommended"] = False
    return state
