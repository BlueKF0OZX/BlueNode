"""Allowlisted link controls with fresh App_Rpt result verification."""
import re
import subprocess
import threading
import time

import asterisk_observation

_LOCK = threading.Lock()
VERIFY_SECONDS = 10


def numeric(value):
    return isinstance(value, str) and re.fullmatch(r'[0-9]{1,10}', value) is not None


def perform(action, payload, config):
    if action not in ('node-connect', 'node-disconnect', 'dodropin-connect', 'dodropin-disconnect'):
        return 403, {'ok': False, 'error': 'Action not permitted'}
    manual = action.startswith('node-')
    if not isinstance(payload, dict) or set(payload) != ({'node'} if manual else set()):
        return 400, {'ok': False, 'error': 'Unexpected control parameters'}
    if manual:
        target = payload['node']
    else:
        mapping = config.get('friendly_nodes', {})
        targets = [str(k) for k, v in mapping.items() if str(v).upper() == 'DODROPIN'] if isinstance(mapping, dict) else []
        if len(targets) != 1:
            return 503, {'ok': False, 'error': 'Configure one DODROPIN friendly-node mapping; manual node controls remain available'}
        target = targets[0]
    local = str(config.get('node', ''))
    if not numeric(target) or not numeric(local) or target == local:
        return 400, {'ok': False, 'error': 'Enter a valid remote AllStar node number'}
    if not _LOCK.acquire(blocking=False):
        return 409, {'ok': False, 'error': 'Another node control is being verified; wait before retrying'}
    connect = action.endswith('-connect')
    def observed():
        evidence = asterisk_observation.node_evidence(local)
        if evidence.get('status') != 'available' or not asterisk_observation.fresh(evidence):
            return None
        links = evidence.get('links')
        if not isinstance(links, list):
            return None
        if connect:
            return any(link['node'] == target and link['mode'] in ('T', 'R') for link in links)
        return not any(link['node'] == target for link in links)
    def success(outcome):
        state = 'connected' if connect else 'disconnected'
        return 200, {'ok': True, 'node': target, 'outcome': outcome,
                     'message': f'Node {target} is {state}; verified from App_Rpt state'}
    try:
        before = observed()
        if before is None:
            return 503, {'ok': False, 'error': 'App_Rpt state unavailable; no command sent'}
        if before:
            return success('already_satisfied')
        command = f"rpt fun {local} {'*3' if connect else '*1'}{target}"
        try:
            result = subprocess.run(['sudo', '-n', '/usr/local/sbin/bluenode-asterisk', '-rx', command],
                                    capture_output=True, text=True, timeout=15)
        except subprocess.TimeoutExpired:
            return 504, {'ok': False, 'outcome': 'timeout', 'error': 'Command timed out; resulting link state is unverified. Check before retrying'}
        except OSError:
            return 503, {'ok': False, 'outcome': 'failed', 'error': 'Unable to execute the permitted node control'}
        if result.returncode != 0:
            return 502, {'ok': False, 'outcome': 'failed', 'error': 'Asterisk rejected the node control; resulting state is unverified'}
        deadline = time.monotonic() + VERIFY_SECONDS
        while True:
            if observed() is True:
                return success('verified')
            if time.monotonic() >= deadline:
                return 504, {'ok': False, 'outcome': 'unverified', 'error': 'Command sent but resulting link state was not verified. Check before retrying'}
            time.sleep(1)
    finally:
        _LOCK.release()
