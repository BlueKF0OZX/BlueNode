"""Reconcile cached App_Rpt variables with actual direct-link transport state."""
import re


def reconcile(sample, output):
    """Return unavailable on malformed/racing observations; retain pending links as C."""
    lines = [line.strip() for line in output.splitlines() if line.strip()]
    if len(lines) < 2 or lines[0].split() != [
            'NODE', 'PEER', 'RECONNECTS', 'DIRECTION', 'CONNECT', 'TIME', 'CONNECT', 'STATE']:
        return None
    if not re.fullmatch(r'[-\s]+', lines[1]):
        return None
    states = {}
    for line in lines[2:]:
        fields = line.split()
        if (len(fields) != 6 or not re.fullmatch(r'[0-9]{1,10}', fields[0])
                or not fields[2].isdigit() or fields[3] not in ('IN', 'OUT')
                or fields[5] not in ('ESTABLISHED', 'CONNECTING') or fields[0] in states):
            return None
        states[fields[0]] = fields[5]
    variable_nodes = {link['node'] for link in sample['links']}
    transport_only = set(states) - variable_nodes
    # App_Rpt omits a not-yet-established outbound transport from RPT_ALINKS.
    # Retain it as pending, never as an established or keyed connection.
    if variable_nodes - set(states) or any(states[node] != 'CONNECTING' for node in transport_only):
        return None
    return dict(sample, links=[
        dict(link, mode='C', keyed=False) if states[link['node']] != 'ESTABLISHED' else dict(link)
        for link in sample['links']] + [
        {'node': node, 'mode': 'C', 'keyed': False} for node in sorted(transport_only)])
