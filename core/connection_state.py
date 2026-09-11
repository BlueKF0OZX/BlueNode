"""Bounded validation of persisted AllStar connection observations."""
import json
import re
from datetime import datetime, timezone
from pathlib import Path

MAX_BYTES = 1024 * 1024


def timestamp(value):
    if not isinstance(value, str) or not 1 <= len(value) <= 64:
        return None
    try:
        parsed = datetime.fromisoformat(value)
        return parsed.replace(tzinfo=timezone.utc) if parsed.tzinfo is None else parsed.astimezone(timezone.utc)
    except (ValueError, OverflowError, OSError):
        return None


def numeric(value):
    return isinstance(value, str) and re.fullmatch(r'[0-9]{1,10}', value) is not None


def unavailable():
    return {'links': [], 'connected_since': {}, 'state_available': False}


def load(path):
    try:
        with Path(path).open('rb') as handle:
            raw = handle.read(MAX_BYTES + 1)
        if len(raw) > MAX_BYTES:
            return unavailable()
        data = json.loads(raw.decode('utf-8'))
        if not isinstance(data, dict):
            return unavailable()
        links, since = data.get('links'), data.get('connected_since')
        if (not isinstance(links, list) or not isinstance(since, dict) or
                not all(numeric(node) for node in links) or len(set(links)) != len(links) or
                set(links) != set(since)):
            return unavailable()
        now = datetime.now(timezone.utc)
        for node, value in since.items():
            parsed = timestamp(value)
            if not numeric(node) or parsed is None or parsed > now:
                return unavailable()
        return {'links': links, 'connected_since': since, 'state_available': True}
    except (OSError, ValueError, TypeError, RecursionError):
        return unavailable()
