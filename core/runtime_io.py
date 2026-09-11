"""Bounded runtime logs and atomic JSON publication."""
import json
import os
from pathlib import Path
import tempfile
import threading

try:
    import fcntl
except ImportError:
    fcntl = None

_LOCK = threading.RLock()
LOG_BYTES = 4 * 1024 * 1024
HISTORY_BYTES = 16 * 1024 * 1024


def tail_lines(path, maximum=LOG_BYTES, backups=0):
    path = Path(path)
    lines = []
    for index in range(backups, -1, -1):
        source = path.with_name(path.name + '.' + str(index)) if index else path
        try:
            with source.open('rb') as handle:
                size = handle.seek(0, os.SEEK_END)
                start = max(0, size - maximum)
                handle.seek(start)
                raw = handle.read(maximum)
            if start:
                raw = raw.split(b'\n', 1)[-1]
            lines.extend(raw.decode('utf-8', errors='replace').splitlines())
        except OSError:
            continue
    return lines


def atomic_json(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(mode='w', encoding='utf-8', dir=path.parent,
                                         delete=False, suffix='.tmp') as handle:
            temporary = Path(handle.name)
            json.dump(value, handle)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
    finally:
        if temporary is not None and temporary.exists():
            temporary.unlink()


def append_bounded(path, line, maximum=LOG_BYTES, backups=2):
    path = Path(path)
    raw = (line.rstrip('\n') + '\n').encode('utf-8')
    if len(raw) > maximum:
        raise ValueError('Runtime record exceeds retention limit')
    path.parent.mkdir(parents=True, exist_ok=True)
    with _LOCK, path.with_name(path.name + '.lock').open('a') as lock:
        if fcntl is not None:
            fcntl.flock(lock.fileno(), fcntl.LOCK_EX)
        try:
            size = path.stat().st_size if path.exists() else 0
            if size + len(raw) > maximum:
                # Bound a legacy oversized file before retaining its latest tail.
                if size > maximum:
                    retained = ('\n'.join(tail_lines(path, maximum)) + '\n').encode('utf-8')
                    path.write_bytes(retained[-maximum:])
                for index in range(backups, 0, -1):
                    source = path if index == 1 else path.with_name(path.name + '.' + str(index - 1))
                    if source.exists():
                        os.replace(source, path.with_name(path.name + '.' + str(index)))
            with path.open('ab') as handle:
                handle.write(raw)
        finally:
            if fcntl is not None:
                fcntl.flock(lock.fileno(), fcntl.LOCK_UN)
