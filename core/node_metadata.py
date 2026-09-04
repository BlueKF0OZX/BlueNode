"""Cached AllStarLink public node-directory metadata."""

import json
import os
import tempfile
import threading
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

from config import load_config


CONFIG = load_config().get("node_metadata", {})
SOURCE_URL = str(CONFIG.get(
    "source_url", "https://allmondb.allstarlink.org/allmondb.php"))
SUCCESS_TTL_SECONDS = max(3600, int(CONFIG.get("success_ttl_seconds", 86400)))
NEGATIVE_TTL_SECONDS = max(300, int(CONFIG.get("negative_ttl_seconds", 3600)))
TIMEOUT_SECONDS = max(1.0, float(CONFIG.get("timeout_seconds", 5.0)))
MAX_BYTES = max(1_000_000, int(CONFIG.get("maximum_download_bytes", 8_000_000)))
REFRESH_RETRY_SECONDS = max(60, int(CONFIG.get("refresh_retry_seconds", 300)))
CACHE_FILE = Path("/opt/nodesmart/state/node_metadata.json")

_LOCK = threading.RLock()
_REFRESHING = False
_MEMORY_CACHE = None
_LAST_REFRESH_ATTEMPT = 0


def utc_now():
    return datetime.now(timezone.utc)


def _timestamp(value):
    try:
        return datetime.fromisoformat(value).timestamp()
    except (TypeError, ValueError):
        return 0


def _load_cache():
    global _MEMORY_CACHE
    with _LOCK:
        if _MEMORY_CACHE is not None:
            return _MEMORY_CACHE
        try:
            data = json.loads(CACHE_FILE.read_text(encoding="utf-8"))
            if not isinstance(data, dict) or not isinstance(data.get("nodes"), dict):
                data = {}
        except (OSError, json.JSONDecodeError):
            data = {}
        _MEMORY_CACHE = data
        return data


def _save_cache(data):
    global _MEMORY_CACHE
    CACHE_FILE.parent.mkdir(parents=True, exist_ok=True)
    fd, name = tempfile.mkstemp(prefix=".node-metadata-", suffix=".tmp",
                                dir=CACHE_FILE.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as file:
            json.dump(data, file, separators=(",", ":"))
            file.flush()
            os.fsync(file.fileno())
        os.replace(name, CACHE_FILE)
        with _LOCK:
            _MEMORY_CACHE = data
    except Exception:
        try:
            os.unlink(name)
        except Exception:
            pass
        raise


def parse_directory(text):
    """Parse the official node directory without guessing location fields."""
    nodes = {}
    for raw_line in text.splitlines():
        parts = raw_line.strip().split("|", 3)
        if len(parts) != 4 or not parts[0].isdigit():
            continue
        node, callsign, description, location = (part.strip() for part in parts)
        record = {"node": node}
        if callsign:
            record["callsign"] = callsign
        if description:
            record["description"] = description
        if location:
            record["location"] = location
            record["display_location"] = location
        nodes[node] = record
    return nodes


def fetch_directory():
    request = urllib.request.Request(
        SOURCE_URL, headers={"User-Agent": "BlueNode node-metadata cache"})
    with urllib.request.urlopen(request, timeout=TIMEOUT_SECONDS) as response:
        body = response.read(MAX_BYTES + 1)
    if len(body) > MAX_BYTES:
        raise ValueError("AllStarLink node directory exceeds configured size limit")
    nodes = parse_directory(body.decode("utf-8", errors="replace"))
    if len(nodes) < 100:
        raise ValueError("AllStarLink node directory response is malformed or incomplete")
    return nodes


def refresh(now=None, fetcher=None):
    """Refresh the whole public directory; callers may safely handle failure."""
    now = utc_now() if now is None else now
    nodes = (fetcher or fetch_directory)()
    data = {"version": 1, "source": SOURCE_URL, "fetched_at": now.isoformat(),
            "nodes": nodes, "negative": {}}
    _save_cache(data)
    return data


def _refresh_worker():
    global _REFRESHING
    try:
        refresh()
    except Exception as exc:
        print(f"BlueNode node metadata refresh error: {exc}", flush=True)
    finally:
        with _LOCK:
            _REFRESHING = False


def schedule_refresh():
    """Start at most one background refresh without blocking radio telemetry."""
    global _REFRESHING, _LAST_REFRESH_ATTEMPT
    with _LOCK:
        now = utc_now().timestamp()
        if _REFRESHING or now - _LAST_REFRESH_ATTEMPT < REFRESH_RETRY_SECONDS:
            return False
        _REFRESHING = True
        _LAST_REFRESH_ATTEMPT = now
        thread = threading.Thread(target=_refresh_worker, name="nodesmart-node-metadata",
                                  daemon=True)
        thread.start()
        return True


def lookup(node, now=None, start_refresh=True):
    now = utc_now() if now is None else now
    node = str(node)
    cache = _load_cache()
    fetched_at = cache.get("fetched_at")
    age = now.timestamp() - _timestamp(fetched_at)
    fresh = bool(fetched_at) and age <= SUCCESS_TTL_SECONDS
    record = cache.get("nodes", {}).get(node) if fresh else None
    if isinstance(record, dict) and record.get("node") == node:
        result = dict(record)
        result.update({"status": "available", "source": cache.get("source", SOURCE_URL),
                       "fetched_at": fetched_at})
        return result

    negative = cache.get("negative", {})
    negative_age = now.timestamp() - _timestamp(negative.get(node))
    if fresh and node in negative and negative_age <= NEGATIVE_TTL_SECONDS:
        return {"status": "not_found", "source": cache.get("source", SOURCE_URL)}

    if start_refresh:
        schedule_refresh()
    if fresh:
        # Remember a missing result briefly; a background refresh may replace it.
        updated = dict(cache)
        updated["negative"] = dict(negative)
        updated["negative"][node] = now.isoformat()
        try:
            _save_cache(updated)
        except Exception:
            pass
        return {"status": "not_found", "source": cache.get("source", SOURCE_URL)}
    return {"status": "unavailable", "source": SOURCE_URL}
