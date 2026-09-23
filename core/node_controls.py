"""Allowlisted link controls with fresh App_Rpt result verification."""
import json
import re
import subprocess
import threading
import time
import uuid

import asterisk_observation
from runtime_io import append_bounded

_LOCK = threading.Lock()
VERIFY_SECONDS = 10
FAILURE_LOG = '/opt/nodesmart/logs/control-failures.jsonl'


def snapshot(evidence):
    """Keep structured link evidence, never raw CLI output or configuration."""
    evidence = evidence if isinstance(evidence, dict) else {}
    return {key: evidence.get(key) for key in
            ('status', 'observed_at', 'reason', 'links')}


def record_failure(record):
    try:
        append_bounded(FAILURE_LOG, json.dumps(record), maximum=1024 * 1024, backups=2)
        return True
    except (OSError, ValueError, TypeError):
        return False


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
    started = time.monotonic()
    initial = None
    latest = None
    observations = 0
    command_sent = False
    command_returncode = None

    def observed():
        nonlocal latest, observations
        evidence = asterisk_observation.node_evidence(local)
        latest = snapshot(evidence)
        observations += 1
        if evidence.get('status') != 'available' or not asterisk_observation.fresh(evidence):
            return None
        links = evidence.get('links')
        if not isinstance(links, list):
            return None
        if connect:
            return any(link['node'] == target and link['mode'] in ('T', 'R') for link in links)
        return not any(link['node'] == target for link in links)

    def pending():
        return bool(latest and latest.get('status') == 'available'
                    and asterisk_observation.fresh(latest)
                    and any(link['node'] == target and link['mode'] == 'C'
                            for link in (latest.get('links') or [])))

    def failure(code, outcome, message, reason):
        incident_id = uuid.uuid4().hex
        saved = record_failure({
            'id': incident_id, 'recorded_at': time.time(), 'action': action,
            'node': target, 'outcome': outcome, 'reason': reason,
            'elapsed_seconds': round(time.monotonic() - started, 3),
            'command_sent': command_sent, 'command_returncode': command_returncode,
            'observation_count': observations, 'before': initial, 'last': latest,
        })
        return code, {'ok': False, 'outcome': outcome, 'error': message,
                      'reason': reason, 'diagnostic_id': incident_id if saved else None,
                      'diagnostic_saved': saved}
    def success(outcome):
        state = 'connected' if connect else 'disconnected'
        return 200, {'ok': True, 'node': target, 'outcome': outcome,
                     'message': f'Node {target} is {state}; verified from App_Rpt state'}
    try:
        before = observed()
        initial = latest
        if before is None:
            return failure(503, 'unavailable', 'App_Rpt state unavailable; no command sent',
                           'observation_unavailable')
        if before:
            return success('already_satisfied')
        command = f"rpt fun {local} {'*3' if connect else '*1'}{target}"
        # A pending transport is already attempting this connection. Observe it
        # under the same lock instead of issuing duplicate DTMF commands.
        if not (connect and pending()):
            try:
                command_sent = True
                result = subprocess.run(['sudo', '-n', '/usr/local/sbin/bluenode-asterisk', '-rx', command],
                                        capture_output=True, text=True, timeout=15)
                command_returncode = result.returncode
            except subprocess.TimeoutExpired:
                return failure(504, 'timeout', 'Command timed out; resulting link state is unverified. Check before retrying',
                               'command_timeout')
            except OSError:
                command_sent = False
                return failure(503, 'failed', 'Unable to execute the permitted node control',
                               'execution_failed')
            if result.returncode != 0:
                return failure(502, 'failed', 'Asterisk rejected the node control; resulting state is unverified',
                               'command_rejected')
        deadline = time.monotonic() + VERIFY_SECONDS
        while True:
            state = observed()
            if state is True:
                return success('verified')
            if time.monotonic() >= deadline:
                if state is None:
                    reason = 'observation_lost'
                    message = 'App_Rpt state became unavailable; the resulting link state is unknown. Check before retrying'
                elif connect and pending():
                    reason = 'connection_pending'
                    message = 'The connection is still pending in App_Rpt. No duplicate connect command was sent; check before retrying'
                else:
                    reason = 'link_not_confirmed'
                    message = 'The requested link state was not confirmed before the verification deadline. Check before retrying'
                return failure(504, 'unverified', message, reason)
            time.sleep(1)
    finally:
        _LOCK.release()
