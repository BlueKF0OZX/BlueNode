"""Independent service evidence and read-only Asterisk observability."""
import re
import subprocess
import time

from config import load_config
from radio_activity import parse_variables

NODE = str(load_config().get('node', ''))
MAX_AGE_SECONDS = 30


def _run(command):
    try:
        return subprocess.run(command, capture_output=True, text=True, timeout=5), None
    except subprocess.TimeoutExpired:
        return None, 'timeout'
    except PermissionError:
        return None, 'permission_denied'
    except FileNotFoundError:
        return None, 'executable_unavailable'
    except Exception:
        # Observation failure is never affirmative evidence of an outage.
        return None, 'execution_failed'


def service_evidence():
    evidence = {'status': 'unknown', 'observed_at': time.time(), 'main_pid': None,
                'active_state': None, 'sub_state': None, 'load_state': None}
    result, error = _run(['systemctl', 'show', 'asterisk', '-p', 'ActiveState',
                          '-p', 'SubState', '-p', 'MainPID', '-p', 'LoadState'])
    if result is None or result.returncode != 0:
        return dict(evidence, reason=error or 'service_probe_failed')
    try:
        fields = dict(line.split('=', 1) for line in result.stdout.splitlines() if '=' in line)
        pid = fields['MainPID']
        if not re.fullmatch(r'[0-9]+', pid):
            return dict(evidence, reason='invalid_service_response')
        evidence.update(main_pid=int(pid), active_state=fields['ActiveState'],
                        sub_state=fields['SubState'], load_state=fields['LoadState'])
        if fields['LoadState'] != 'loaded':
            return dict(evidence, reason='service_not_loaded')
        if fields['ActiveState'] == 'active' and fields['SubState'] == 'running' and int(pid) > 0:
            evidence['status'] = 'online'
        elif int(pid) == 0 and ((fields['ActiveState'], fields['SubState']) in
                               (('inactive', 'dead'), ('failed', 'failed'))):
            evidence['status'] = 'offline'
        return evidence
    except (KeyError, TypeError, ValueError, OverflowError):
        return dict(evidence, reason='invalid_service_response')


def fresh(evidence, now=None):
    now = time.time() if now is None else now
    try:
        return isinstance(evidence, dict) and 0 <= now - evidence['observed_at'] <= MAX_AGE_SECONDS
    except (KeyError, TypeError, ValueError, OverflowError):
        return False


def confirmed_stopped(evidence, now=None):
    return (fresh(evidence, now) and evidence.get('status') == 'offline'
            and evidence.get('main_pid') == 0 and evidence.get('load_state') == 'loaded'
            and (evidence.get('active_state'), evidence.get('sub_state')) in
            (('inactive', 'dead'), ('failed', 'failed')))


def query_evidence():
    result, error = _run(['sudo', '-n', '/usr/local/sbin/bluenode-asterisk', '-rx', 'core show version'])
    available = bool(result is not None and result.returncode == 0 and
                     re.search(r'^Asterisk\s+[0-9]+(?:\.[0-9]+)', result.stdout, re.MULTILINE))
    return {'status': 'available' if available else 'unavailable', 'observed_at': time.time(),
            'reason': None if available else error or 'invalid_or_failed_cli_response'}


def node_evidence(node=None):
    node = NODE if node is None else node
    base = {'status': 'unavailable', 'observed_at': time.time()}
    if not re.fullmatch(r'[0-9]{1,10}', node):
        return dict(base, reason='invalid_node_configuration')
    result, error = _run(['sudo', '-n', '/usr/local/sbin/bluenode-asterisk', '-rx', 'rpt show variables ' + node])
    if result is None or result.returncode != 0:
        return dict(base, reason=error or 'node_query_failed')
    output = result.stdout
    values = dict(line.strip().split('=', 1) for line in output.splitlines()
                  if line.strip().startswith('RPT_') and '=' in line)
    sample = parse_variables(output)
    links = values.get('RPT_ALINKS', '').split(',')
    # Require complete RX/TX/link structure, not merely command execution.
    # Upstream rpt_update_links emits an explicitly empty RPT_ALINKS for zero
    # links (apps/app_rpt/rpt_link.c). Absence of the field remains incomplete.
    valid_links = ('RPT_ALINKS' in values and (values['RPT_ALINKS'] == '' or (
        links[0].isdigit() and int(links[0]) == len(links) - 1
        and all(re.fullmatch(r'[0-9]{1,10}[TRC][KU]', value) for value in links[1:]))))
    if 'RPT_NUMALINKS' in values:
        expected = 0 if values.get('RPT_ALINKS') == '' else len(links) - 1
        valid_links = valid_links and values['RPT_NUMALINKS'].isdigit() and int(values['RPT_NUMALINKS']) == expected
    if sample is None or not valid_links:
        if re.search(r'no such node|node .*not found|node .*not configured', output, re.I):
            reason = 'node_not_found'
        elif re.search(r'no such command', output, re.I):
            reason = 'app_rpt_unavailable'
        else:
            reason = 'invalid_or_incomplete_node_response'
        return dict(base, reason=reason)
    return dict(base, status='available', reason=None)


def collect():
    service = service_evidence()
    query = query_evidence()
    node = node_evidence() if query['status'] == 'available' else {
        'status': 'unknown', 'reason': 'query_unavailable', 'observed_at': time.time()}
    if service['status'] == 'offline' and query['status'] == 'available':
        service = dict(service, status='unknown', reason='conflicting_service_and_query_evidence')
    return {'service': service, 'query': query, 'node': node, 'max_age_seconds': MAX_AGE_SECONDS}


def warning(evidence):
    service = evidence.get('service', {}).get('status')
    if service == 'offline':
        return 'Asterisk service is stopped or failed.'
    if service != 'online':
        return 'Asterisk service state is unknown; automatic restart is prohibited.'
    if evidence.get('query', {}).get('status') != 'available':
        return 'Asterisk is running, but BlueNode cannot query it.'
    if evidence.get('node', {}).get('status') != 'available':
        return 'Asterisk is running, but the configured App_Rpt node is not observable.'
    return None
