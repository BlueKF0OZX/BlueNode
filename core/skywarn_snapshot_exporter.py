"""Optional observer copied beside SkywarnPlus.py; no weather/radio operations."""
import json
import os
from pathlib import Path
import tempfile
import threading
import time

try:
    import fcntl
except ImportError:  # Development fixtures on Windows.
    fcntl = None

MAX_BYTES = 1048576
_context = threading.local()


def zone_success():
    if hasattr(_context, 'successes'):
        _context.successes += 1


def publish(directory, snapshot):
    """Bounded atomic export; never let exporter failure alter upstream behavior."""
    temporary = None
    try:
        directory = Path(directory)
        payload = json.dumps(snapshot, allow_nan=False).encode('utf-8')
        if len(payload) > MAX_BYTES:
            return False
        flags = os.O_CREAT | os.O_RDWR | getattr(os, 'O_NOFOLLOW', 0)
        with os.fdopen(os.open(directory / 'bluenode-weather.lock', flags, 0o600), 'r+') as lock:
            if fcntl:
                fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
            target = directory / 'bluenode-weather.json'
            previous = {}
            try:
                with target.open('rb') as handle:
                    previous = json.loads(handle.read(MAX_BYTES + 1))
                if not isinstance(previous, dict):
                    previous = {}
                if previous.get('last_attempt', 0) > snapshot['last_attempt']:
                    return False  # An older overlapping cron run must not win.
            except (OSError, ValueError, TypeError):
                pass
            snapshot = dict(snapshot)
            if snapshot['collection_status'] != 'success':
                snapshot['last_success'] = previous.get('last_success')
            payload = json.dumps(snapshot, allow_nan=False).encode('utf-8')
            if len(payload) > MAX_BYTES:
                return False
            with tempfile.NamedTemporaryFile(dir=directory, prefix='.bluenode-weather-', delete=False) as handle:
                temporary = Path(handle.name)
                handle.write(payload)
                handle.flush()
                os.fsync(handle.fileno())
                os.chmod(temporary, 0o644)  # Public weather telemetry, never credentials.
            os.replace(temporary, target)
            temporary = None
        return True
    except Exception:
        return False
    finally:
        if temporary is not None:
            try:
                temporary.unlink()
            except OSError:
                pass


def collect(operation, counties, config, directory, county_names=None):
    """Return the exact upstream object and propagate its exceptions unchanged."""
    attempt = time.time()
    _context.successes = 0
    snapshot = {'schema_version': 1, 'source': 'SkywarnPlus',
                'last_attempt': attempt, 'last_success': None,
                'observed_at': attempt, 'collection_status': 'failure',
                'in_progress': True, 'configured_counties': len(counties),
                'successful_counties': 0, 'test_mode': bool(config.get('DEV', {}).get('INJECT', False)),
                'county_names': {str(code): str((county_names or {}).get(code, code)) for code in counties},
                'alerts': []}
    publish(directory, snapshot)
    try:
        alerts = operation(counties)
    except BaseException:
        snapshot.update(in_progress=False, observed_at=time.time())
        publish(directory, snapshot)
        raise
    try:
        completed = time.time()
        successes = _context.successes
        status = ('success' if len(counties) > 0 and successes == len(counties) else
                  'partial' if successes else 'failure')
        if snapshot['test_mode']:
            status = 'failure'
        snapshot.update(collection_status=status, in_progress=False,
                        observed_at=completed, successful_counties=successes,
                        last_success=completed if status == 'success' else None,
                        alerts=list(alerts.items()))
        publish(directory, snapshot)
    except Exception:
        pass
    return alerts
