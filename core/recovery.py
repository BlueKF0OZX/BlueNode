#!/usr/bin/env python3

"""Automatic Asterisk recovery with verified completion."""

import json
import subprocess
import time
from datetime import datetime, timezone
from pathlib import Path

import automation
import asterisk_observation
from config import load_config
from event_logger import emit

CONFIG = load_config()
RECOVERY_CONFIG = CONFIG.get("recovery", {})
NODE = str(CONFIG.get("node", ""))
DISPLAY_RESET_HOURS = int(RECOVERY_CONFIG.get("display_reset_hours", 6))
ASTERISK_RECOVERY_ENABLED = RECOVERY_CONFIG.get("asterisk_enabled", False) is True
VERIFY_TIMEOUT_SECONDS = int(RECOVERY_CONFIG.get("verification_timeout_seconds", 30))
VERIFY_STABLE_CHECKS = int(RECOVERY_CONFIG.get("verification_stable_checks", 2))
VERIFY_INTERVAL_SECONDS = int(RECOVERY_CONFIG.get("verification_interval_seconds", 2))
STATE_FILE = Path("/opt/nodesmart/state/system.json")
INTELLIGENCE_FILE = Path("/opt/nodesmart/state/intelligence.json")
ALLSTAR_STATE_FILE = Path("/opt/nodesmart/events/allstar_state.json")
RECOVERY_STATE_FILE = Path("/opt/nodesmart/state/recovery.json")


def asterisk_online():
    return asterisk_observation.query_evidence()["status"] == "available"


def allstar_reachable():
    return asterisk_observation.node_evidence(NODE)["status"] == "available"


def load_json(path):
    try:
        with path.open(encoding="utf-8") as file:
            value = json.load(file)
        return value if isinstance(value, dict) else None
    except (OSError, json.JSONDecodeError, TypeError, ValueError):
        return None


def load_system_state():
    return load_json(STATE_FILE)


def load_recovery_state():
    return load_json(RECOVERY_STATE_FILE) or {}


def save_recovery_state(data):
    data["display_reset_hours"] = DISPLAY_RESET_HOURS
    RECOVERY_STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
    temporary = RECOVERY_STATE_FILE.with_suffix(".tmp")
    with temporary.open("w", encoding="utf-8") as file:
        json.dump(data, file, indent=2)
    temporary.replace(RECOVERY_STATE_FILE)


def record_recovery_result(status, message):
    state = load_recovery_state()
    state["last_recovery"] = {
        "component": "asterisk", "status": status, "message": message,
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }
    save_recovery_state(state)


def clear_recovery_limits():
    state = load_recovery_state()
    state["asterisk_attempt_history"] = []
    state["asterisk_lockout_until"] = 0
    save_recovery_state(state)


def verify_recovery(started_at, timeout=None):
    """Require fresh BlueNode state and stable Asterisk health after restart."""
    timeout = VERIFY_TIMEOUT_SECONDS if timeout is None else timeout
    deadline = time.monotonic() + timeout
    stable = 0
    last_reason = "Waiting for post-recovery health state"
    while time.monotonic() <= deadline:
        service = asterisk_observation.service_evidence()
        if not (asterisk_observation.fresh(service) and service["status"] == "online"):
            stable = 0
            last_reason = "Independent Asterisk service health is not running"
        elif not asterisk_online():
            stable = 0
            last_reason = "Asterisk CLI is not reachable"
        else:
            system = load_json(STATE_FILE)
            intelligence = load_json(INTELLIGENCE_FILE)
            allstar_valid = not ALLSTAR_STATE_FILE.exists() or load_json(ALLSTAR_STATE_FILE) is not None
            try:
                observed = datetime.fromisoformat(system["last_health_check"]).timestamp()
            except (TypeError, KeyError, ValueError, AttributeError):
                observed = 0
            intelligence_fresh = (
                intelligence is not None and INTELLIGENCE_FILE.exists()
                and INTELLIGENCE_FILE.stat().st_mtime >= started_at
            )
            component_normal = (system or {}).get("health", {}).get("asterisk") == "normal"
            collected = (system or {}).get("asterisk_evidence", {})
            collected_service = collected.get("service", {})
            trustworthy = (asterisk_observation.fresh(collected_service)
                           and collected_service.get("status") == "online"
                           and collected_service.get("observed_at", 0) >= started_at
                           and collected.get("query", {}).get("status") == "available"
                           and collected.get("node", {}).get("status") == "available")
            if (system and trustworthy and system.get("asterisk") == "online" and component_normal
                    and allstar_reachable() and observed >= started_at
                    and intelligence_fresh and allstar_valid):
                stable += 1
                if stable >= max(1, VERIFY_STABLE_CHECKS):
                    return True, "Asterisk and fresh BlueNode state passed post-recovery verification"
                last_reason = "First healthy observation passed; checking for immediate recurrence"
            else:
                stable = 0
                last_reason = "Fresh health, Intelligence, or AllStar state is not yet verified"
        time.sleep(max(0, VERIFY_INTERVAL_SECONDS))
    return False, last_reason


def _failed(message):
    emit("RECOVERY.ASTERISK.FAILED", message)
    record_recovery_result("failed", message)
    automation.finish_recovery(False, message)


def recover_asterisk():
    if not ASTERISK_RECOVERY_ENABLED:
        return
    state = load_system_state()
    if not state or state.get("asterisk") != "offline":
        return
    if not automation.recovery_allowed(state):
        return
    if not asterisk_observation.confirmed_stopped(asterisk_observation.service_evidence()):
        return
    time.sleep(5)
    if (not asterisk_observation.confirmed_stopped(asterisk_observation.service_evidence())
            or asterisk_online()):
        message = "Independent outage confirmation no longer permits restart"
        emit("RECOVERY.ASTERISK.CANCELLED", message)
        record_recovery_result("cancelled", message)
        return
    if not automation.recovery_allowed(state):
        return
    attempt = automation.begin_recovery()
    if attempt is None:
        return
    started_at = time.time()
    try:
        # Last external observation immediately before the mutating command.
        if not asterisk_observation.confirmed_stopped(asterisk_observation.service_evidence()):
            message = "Final service evidence does not confirm an outage; restart cancelled"
            emit("RECOVERY.ASTERISK.CANCELLED", message)
            record_recovery_result("cancelled", message)
            automation.cancel_recovery(message)
            return
        emit("RECOVERY.ASTERISK.ATTEMPT",
             f"Independently confirmed stopped service; recovery attempt {attempt} started")
        result = subprocess.run(
            ["sudo", "-n", "systemctl", "restart", "asterisk"],
            capture_output=True, text=True, timeout=20,
        )
    except subprocess.TimeoutExpired:
        _failed("Asterisk restart command timed out")
        return
    except OSError as exc:
        _failed(f"Unable to execute restart: {exc}")
        return
    if result.returncode != 0:
        _failed(result.stderr.strip() or result.stdout.strip()
                or f"systemctl exited with status {result.returncode}")
        return
    verified, message = verify_recovery(started_at)
    if not verified:
        _failed(f"Restart completed but verification failed: {message}")
        return
    emit("RECOVERY.ASTERISK.SUCCESS", message)
    record_recovery_result("success", message)
    automation.finish_recovery(True, message)


if __name__ == "__main__":
    recover_asterisk()
