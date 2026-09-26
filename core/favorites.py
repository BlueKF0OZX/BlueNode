"""Node-scoped dashboard favorites; never invokes radio controls."""
import json
import re
import threading
from pathlib import Path

from runtime_io import atomic_json

_LOCK = threading.RLock()
MAX_FAVORITES = 20


def valid_node(value):
    return isinstance(value, str) and re.fullmatch(r'[0-9]{1,10}', value) is not None


def valid_item(item, local):
    return (isinstance(item, dict) and set(item) == {'node', 'label'}
            and valid_node(item['node']) and item['node'] != local
            and isinstance(item['label'], str) and len(item['label']) <= 48
            and not any(ord(c) < 32 for c in item['label']))


def _read(root, local):
    if not valid_node(local):
        raise ValueError('Invalid local node')
    path = Path(root) / 'state/favorites.json'
    try:
        with path.open('rb') as handle:
            raw = handle.read(32769)
    except FileNotFoundError:
        return {'local_node': local, 'revision': 0, 'favorites': []}
    if len(raw) > 32768:
        raise ValueError('Oversized favorites')
    data = json.loads(raw)
    if (not isinstance(data, dict) or set(data) != {'local_node', 'revision', 'favorites'}
            or data['local_node'] != local or type(data['revision']) is not int
            or data['revision'] < 0 or not isinstance(data['favorites'], list)
            or len(data['favorites']) > MAX_FAVORITES
            or any(not valid_item(item, local) for item in data['favorites'])
            or len({item['node'] for item in data['favorites']}) != len(data['favorites'])):
        raise ValueError('Invalid favorites state')
    return data


def read(root, local):
    with _LOCK:
        try:
            return 200, {'ok': True, **_read(root, local)}
        except (OSError, ValueError, UnicodeError):
            return 503, {'ok': False, 'error': 'Shared favorites unavailable; saved data was preserved.'}


def update(root, local, payload):
    if (not isinstance(payload, dict) or payload.get('local_node') != local
            or type(payload.get('revision')) is not int or payload['revision'] < 0):
        return 400, {'ok': False, 'error': 'Invalid favorites request.'}
    operation = payload.get('operation')
    fields = {'local_node', 'revision', 'operation'}
    if operation == 'save':
        valid = set(payload) == fields | {'item'} and valid_item(payload['item'], local)
    elif operation == 'remove':
        valid = set(payload) == fields | {'node'} and valid_node(payload['node']) and payload['node'] != local
    elif operation == 'import':
        items = payload.get('items')
        valid = (set(payload) == fields | {'items'} and isinstance(items, list)
                 and len(items) <= MAX_FAVORITES and all(valid_item(item, local) for item in items)
                 and len({item['node'] for item in items}) == len(items))
    else:
        valid = False
    if not valid:
        return 400, {'ok': False, 'error': 'Invalid favorites request.'}
    with _LOCK:
        status, current = read(root, local)
        if status != 200:
            return status, current
        if payload['revision'] != current['revision']:
            return 409, {'ok': False, 'error': 'Favorites changed on another device. Review the refreshed list and retry.'}
        items = [dict(item) for item in current['favorites']]
        if operation == 'save':
            item = dict(payload['item']); item['label'] = item['label'].strip()
            match = next((i for i, old in enumerate(items) if old['node'] == item['node']), None)
            if match is None:
                items.append(item)
            else:
                items[match] = item
        elif operation == 'remove':
            items = [item for item in items if item['node'] != payload['node']]
        else:
            for item in payload['items']:
                if not any(old['node'] == item['node'] for old in items):
                    items.append({'node': item['node'], 'label': item['label'].strip()})
        if len(items) > MAX_FAVORITES:
            return 400, {'ok': False, 'error': 'Favorites is full. Remove a node before adding or importing more.'}
        saved = {'local_node': local, 'revision': current['revision'] + 1, 'favorites': items}
        try:
            atomic_json(Path(root) / 'state/favorites.json', saved)
        except OSError:
            return 503, {'ok': False, 'error': 'Favorites could not be saved. Retry after storage is available.'}
        return 200, {'ok': True, **saved}
