#!/usr/bin/env python3

import json
import os
from pathlib import Path

DEFAULT_CONFIG_FILE = Path("/opt/nodesmart/config/nodesmart.json")

CONFIG_FILE = Path(
    os.environ.get("NODESMART_CONFIG", DEFAULT_CONFIG_FILE)
)

def load_config():
    if not CONFIG_FILE.exists():
        raise RuntimeError(
            f"BlueNode configuration file not found: {CONFIG_FILE}\n"
            "Create it from config/nodesmart.example.json before starting BlueNode."
        )

    try:
        with CONFIG_FILE.open("r", encoding="utf-8") as file:
            config = json.load(file)
    except json.JSONDecodeError as exc:
        raise RuntimeError(
            f"Invalid JSON in BlueNode configuration file "
            f"{CONFIG_FILE}: line {exc.lineno}, column {exc.colno}"
        ) from exc
    except OSError as exc:
        raise RuntimeError(
            f"Unable to read BlueNode configuration file "
            f"{CONFIG_FILE}: {exc}"
        ) from exc

    if not isinstance(config, dict):
        raise RuntimeError(
            f"BlueNode configuration file {CONFIG_FILE} "
            "must contain a JSON object."
        )

    return config
