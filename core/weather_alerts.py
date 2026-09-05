"""Bounded read-only adapter for the SkywarnPlus observer snapshot."""
import json
import math
import os
from pathlib import Path
import stat
import time
from datetime import datetime

from config import load_config

SETTINGS = load_config().get('weather_alerts', {})
SETTINGS = SETTINGS if isinstance(SETTINGS, dict) else {}
_path = SETTINGS.get('snapshot_path')
SNAPSHOT_FILE = Path(_path if isinstance(_path, str) and _path else '/tmp/SkywarnPlus/bluenode-weather.json')
MAX_BYTES = 1048576
STALE_SECONDS = 180
_cache = (None, None)


def read_snapshot(path):
    global _cache
    info = path.lstat()
    if not stat.S_ISREG(info.st_mode):
        raise ValueError('Snapshot must be a regular file')
    key = (str(path), info.st_ino, info.st_mtime_ns, info.st_size)
    if key == _cache[0]:
        return _cache[1]
    flags = os.O_RDONLY | getattr(os, 'O_NONBLOCK', 0) | getattr(os, 'O_NOFOLLOW', 0)
    with os.fdopen(os.open(path, flags), 'rb') as handle:
        if not stat.S_ISREG(os.fstat(handle.fileno()).st_mode) or info.st_size > MAX_BYTES:
            raise ValueError('Snapshot must be a bounded regular file')
        raw = handle.read(MAX_BYTES + 1)
    if len(raw) > MAX_BYTES:
        raise ValueError('Snapshot too large')
    value = json.loads(raw)
    _cache = (key, value)
    return value


def number(value):
    return type(value) in (int, float) and math.isfinite(value)


def require(condition):
    if not condition:
        raise ValueError('Invalid snapshot')


def normalize(snapshot, enabled, now):
    result = {'status': 'unavailable', 'alerts': [], 'last_attempt': None,
              'last_success': None, 'collection_status': None,
              'reason': 'Alert information unavailable', 'stale_after_seconds': STALE_SECONDS}
    if enabled != 'enabled':
        result['reason'] = 'SkywarnPlus disabled' if enabled == 'disabled' else 'SkywarnPlus status unavailable'
        return result
    try:
        s = snapshot
        require(type(s['schema_version']) is int and s['schema_version'] == 1 and s['source'] == 'SkywarnPlus')
        require(s['collection_status'] in ('success', 'partial', 'failure'))
        require(isinstance(s['alerts'], list) and len(s['alerts']) <= 256)
        for field in ['last_attempt', 'observed_at']:
            require(number(s[field]) and 0 < s[field] <= now + 30)
        require(s['last_attempt'] <= s['observed_at'])
        result.update(last_attempt=s['last_attempt'], last_success=s.get('last_success'),
                      collection_status=s['collection_status'])
        if s['collection_status'] != 'success' or s.get('in_progress') is not False or s.get('test_mode') is not False:
            result['reason'] = 'Partial SkywarnPlus collection' if s['collection_status'] == 'partial' else 'SkywarnPlus collection unavailable'
            return result
        require(number(s['last_success']) and s['last_success'] == s['observed_at'])
        require(type(s['configured_counties']) is int and s['configured_counties'] > 0)
        require(type(s['successful_counties']) is int and s['successful_counties'] == s['configured_counties'])
        if now - s['last_success'] > STALE_SECONDS:
            result.update(status='stale', reason='Alert information stale')
            return result
        alerts = []
        areas = s.get('county_names', {})
        require(isinstance(areas, dict))
        for event, instances in s['alerts']:
            require(isinstance(event, str) and 0 < len(event) <= 200)
            require(isinstance(instances, list) and len(instances) <= 512)
            for instance in instances:
                county, description = instance['county_code'], instance.get('description', '')
                severity = instance['severity']
                require(isinstance(county, str) and 0 < len(county) <= 32)
                require(isinstance(description, str) and len(description) <= 32000)
                require(type(severity) is int and 0 <= severity <= 4)
                area = areas.get(county, county)
                require(isinstance(area, str) and len(area) <= 200)
                end = datetime.fromisoformat(instance['end_time_utc'].replace('Z', '+00:00'))
                require(end.tzinfo is not None)
                if end.timestamp() <= now:
                    continue
                alerts.append({'event': event, 'county_code': county, 'area': area, 'severity': severity,
                               'description': description, 'end_time': end.timestamp()})
                require(len(alerts) <= 512)
        result.update(status='current', reason='', alerts=alerts)
    except (AssertionError, KeyError, TypeError, ValueError, AttributeError, OverflowError):
        result.update(status='unavailable', reason='Malformed SkywarnPlus snapshot', alerts=[])
    return result


def public_state(enabled, now=None):
    now = time.time() if now is None else now
    try:
        return normalize(read_snapshot(SNAPSHOT_FILE), enabled, now)
    except (OSError, ValueError, TypeError, RecursionError):
        return normalize({}, enabled, now)
