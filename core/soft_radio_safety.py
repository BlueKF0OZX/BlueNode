#!/usr/bin/env python3
"""Semantic Asterisk safety gates for broker-only Soft Radio startup."""

import argparse
import json
import re
import subprocess
from pathlib import Path


MODULES = (
    "res_sorcery_config.so",
    "res_http_websocket.so",
    "res_websocket_client.so",
    "chan_websocket.so",
)


def _run(command):
    result = subprocess.run(command, capture_output=True, text=True, timeout=5)
    if result.returncode:
        raise RuntimeError(f"state query failed: {command[0]}")
    return result.stdout


def _module_running(output, module):
    for line in output.splitlines():
        fields = line.split()
        if (fields and fields[0] == module and len(fields) >= 4
                and fields[-2] == "Running" and fields[-3].isdigit()):
            return True
    return False


def _keyed(output, key):
    match = re.search(rf"^\s*{re.escape(key)}\s*=\s*([^\s]+)", output,
                      re.MULTILINE)
    return match.group(1) if match else "unknown"


def _channels(output):
    """Return stable channel names, excluding CLI summaries and counters."""
    names = set()
    for line in output.splitlines():
        if "!" not in line:
            continue
        name = line.split("!", 1)[0].strip()
        if name:
            names.add(name)
    return sorted(names)


def _uptime(output):
    values = {}
    for label, key in (("System uptime", "uptime_seconds"),
                       ("Last reload", "reload_seconds")):
        match = re.search(rf"{label}:\s*(\d+)", output)
        values[key] = int(match.group(1)) if match else None
    return values


def _listeners(output, port):
    matches = []
    suffix = f":{port}"
    for line in output.splitlines():
        fields = line.split()
        if len(fields) < 4:
            continue
        address = fields[3]
        if address.endswith(suffix):
            matches.append(address)
    return sorted(set(matches))


def collect_state(node, runner=_run, broker_port=8767):
    variables = runner(["sudo", "-n", "asterisk", "-rx",
                        f"rpt show variables {node}"])
    modules = {
        module: _module_running(
            runner(["sudo", "-n", "asterisk", "-rx",
                    f"module show like {module}"]), module)
        for module in MODULES
    }
    state = {
        "asterisk_active": runner(
            ["systemctl", "is-active", "asterisk.service"]).strip() == "active",
        "pid": runner(["systemctl", "show", "asterisk.service", "-p",
                       "MainPID", "--value"]).strip(),
        "start_marker": runner(
            ["systemctl", "show", "asterisk.service", "-p",
             "ActiveEnterTimestampMonotonic", "--value"]).strip(),
        "tx_keyed": _keyed(variables, "RPT_TXKEYED"),
        "channels": _channels(runner(
            ["sudo", "-n", "asterisk", "-rx", "core show channels concise"])),
        "modules": modules,
        "listeners": _listeners(runner(["ss", "-H", "-ltn"]), broker_port),
    }
    state.update(_uptime(runner(
        ["sudo", "-n", "asterisk", "-rx", "core show uptime seconds"])))
    return state


def verify_broker_only(before, after, broker_port=8767):
    errors = []
    if not before.get("asterisk_active") or not after.get("asterisk_active"):
        errors.append("Asterisk is not active")
    if before.get("pid") != after.get("pid"):
        errors.append("Asterisk PID changed")
    if before.get("start_marker") != after.get("start_marker"):
        errors.append("Asterisk start marker changed")
    if before.get("tx_keyed") != "0" or after.get("tx_keyed") != "0":
        errors.append("RPT_TXKEYED is not zero")
    if before.get("channels") != after.get("channels"):
        errors.append("Asterisk channel set changed")
    if any(name.startswith("WebSocket/") or "BlueNode-RX" in name
           for name in after.get("channels", [])):
        errors.append("Soft Radio Asterisk channel exists")
    if before.get("modules") != after.get("modules"):
        errors.append("Soft Radio module state changed")
    before_reload = before.get("reload_seconds")
    after_reload = after.get("reload_seconds")
    if (before_reload is None or after_reload is None
            or after_reload < before_reload):
        errors.append("Asterisk reload state changed or is unavailable")
    expected_listener = f"127.0.0.1:{broker_port}"
    if after.get("listeners") != [expected_listener]:
        errors.append("broker is not listening exclusively on expected loopback")
    return errors


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("action", choices=("snapshot", "verify"))
    parser.add_argument("--node", required=True)
    parser.add_argument("--baseline", type=Path)
    parser.add_argument("--broker-port", type=int, default=8767)
    args = parser.parse_args()
    state = collect_state(args.node, broker_port=args.broker_port)
    if args.action == "snapshot":
        print(json.dumps(state, sort_keys=True))
        return
    if args.baseline is None:
        raise SystemExit("--baseline is required for verify")
    before = json.loads(args.baseline.read_text(encoding="utf-8"))
    errors = verify_broker_only(before, state, args.broker_port)
    if errors:
        raise SystemExit("FAIL soft-radio-safety: " + "; ".join(errors))
    print("PASS soft-radio-safety: broker-only Asterisk state unchanged")


if __name__ == "__main__":
    main()
