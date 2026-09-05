#!/usr/bin/python3
"""Fail before installation when onboarding values cannot start the runtime."""
import ipaddress
import json
import math
from pathlib import Path
import sys


def validate(config):
    if not isinstance(config, dict):
        raise ValueError("configuration must be a JSON object")
    node = str(config.get("node", ""))
    if not (node.isascii() and node.isdigit() and 1 <= len(node) <= 10) or node == "12345":
        raise ValueError("set node to your AllStar node number (replace the example)")
    callsign = config.get("callsign")
    if not isinstance(callsign, str) or not callsign.strip() or callsign == "N0CALL":
        raise ValueError("set callsign to your station callsign")
    web = config.get("web", {})
    ipaddress.IPv4Address(web.get("host", "127.0.0.1"))
    port = web.get("port", 8080)
    if type(port) is not int or not 1024 <= port <= 65535:
        raise ValueError("web.port must be an unprivileged integer port (1024..65535)")
    friendly = config.get("friendly_nodes", {})
    if not isinstance(friendly, dict) or any(
        not (str(k).isascii() and str(k).isdigit() and 1 <= len(str(k)) <= 10
             and isinstance(v, str)) for k, v in friendly.items()
    ):
        raise ValueError("friendly_nodes must map numeric node numbers to names")
    for section in ("health", "recovery", "automation", "radio_activity",
                    "node_behavior", "node_metadata", "connectivity"):
        if not isinstance(config.get(section, {}), dict):
            raise ValueError(section + " must be an object")
    example = json.loads((Path(__file__).resolve().parents[1] /
                          "config/nodesmart.example.json").read_text(encoding="utf-8"))
    for section in ("health", "recovery", "automation", "radio_activity",
                    "node_behavior", "node_metadata", "connectivity"):
        for key, default in example[section].items():
            if type(default) not in (int, float) or key not in config.get(section, {}):
                continue
            value = config[section][key]
            if type(value) not in (int, float) or not math.isfinite(value) or value < 0:
                raise ValueError(section + "." + key + " must be a nonnegative finite number")
    if type(config.get("recovery", {}).get("asterisk_enabled", False)) is not bool:
        raise ValueError("recovery.asterisk_enabled must be true or false")


if __name__ == "__main__":
    try:
        with open(sys.argv[1], encoding="utf-8") as handle:
            validate(json.load(handle))
    except (OSError, ValueError, TypeError, AttributeError) as exc:
        sys.exit("Invalid BlueNode configuration: " + str(exc))
