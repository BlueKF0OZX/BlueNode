"""Exercise real health -> events/incidents -> scheduling -> recovery, without effects."""
import copy
import subprocess
import time
import unittest
from contextlib import ExitStack, nullcontext
from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import patch

import asterisk_observation as observation
import automation
import health
import intelligence
import monitor
import recovery

VALID_NODE = 'RPT_RXKEYED=0\nRPT_TXKEYED=0\nRPT_ALINKS=0\n'


def service(active='active', sub='running', pid=123, loaded='loaded'):
    return subprocess.CompletedProcess([], 0,
        f'ActiveState={active}\nSubState={sub}\nMainPID={pid}\nLoadState={loaded}\n', '')


class ImmediateThread:
    def __init__(self, target, **kwargs): self.target = target
    def start(self): self.target()


class ObservationTests(unittest.TestCase):
    def setUp(self):
        self.stack = ExitStack(); self.addCleanup(self.stack.close)
        self.service_results = [service()]
        self.query = subprocess.CompletedProcess([], 0, 'Asterisk 22.0 fixture', '')
        self.node = subprocess.CompletedProcess([], 0, VALID_NODE, '')
        self.calls = []; self.events = []; self.state = {}; self.auto = automation.default_state()
        self.verified_results = []; self.after_restart = True
        self.previous = {'asterisk': 'online', 'status': 'healthy', 'health': {}}
        def save_auto(state):
            self.auto = copy.deepcopy(state)
            return copy.deepcopy(state)
        def emit(name, message):
            self.events.append({'event': name, 'message': message, 'timestamp': datetime.now(timezone.utc)})
        for obj, name, replacement in (
            (observation.subprocess, 'run', self.run_command),
            (health, 'get_allstar_state', lambda: {'links': [], 'connected_since': {}}),
            (health, 'check_skywarn', lambda: 'unknown'), (health, 'get_cpu_temp', lambda: 40),
            (health, 'get_uptime', lambda: 100), (health, 'get_memory_usage', lambda: 20),
            (health, 'get_disk_usage', lambda: 20), (health, 'summarize_connections', lambda: {}),
            (health.connectivity, 'public_state', lambda: {'status': 'healthy'}),
            (health.connectivity, 'legacy_internet_state', lambda _: 'online'),
            (health.weather_alerts, 'public_state', lambda _: {'status': 'unavailable'}),
            (health.radio_activity, 'public_state', lambda: {}),
            (monitor, 'load_previous_state', lambda: self.previous),
            (monitor, 'save_state', self.save_health),
            (monitor.node_behavior, 'observe', lambda *_: {}),
            (intelligence, 'load_json', lambda _: {}), (intelligence, 'load_events', lambda: self.events),
            (intelligence, 'load_recovery_state', lambda: {}), (intelligence, 'save_intelligence', lambda _: None),
            (automation, 'state_lock', lambda: nullcontext()),
            (automation, 'load_state', lambda: copy.deepcopy(self.auto)),
            (automation, 'save_state', save_auto), (automation, 'RECOVERY_ENABLED', True),
            (recovery, 'ASTERISK_RECOVERY_ENABLED', True), (recovery.time, 'sleep', lambda _: None),
            (recovery, 'load_system_state', lambda: self.state),
            (recovery, 'record_recovery_result', lambda *args: self.verified_results.append(args)),
            (recovery, 'load_json', lambda path: self.state if path == recovery.STATE_FILE else {}),
            (recovery, 'INTELLIGENCE_FILE', SimpleNamespace(exists=lambda: True,
                                                          stat=lambda: SimpleNamespace(st_mtime=time.time()))),
            (recovery, 'ALLSTAR_STATE_FILE', SimpleNamespace(exists=lambda: False)),
            (health, 'emit', emit), (automation, 'emit', emit), (recovery, 'emit', emit),
        ):
            self.stack.enter_context(patch.object(obj, name, replacement))

    def save_health(self, state):
        self.state = copy.deepcopy(state)

    def run_command(self, command, **kwargs):
        self.calls.append(command)
        if command[:3] == ['systemctl', 'show', 'asterisk']:
            value = self.service_results[0]
            if len(self.service_results) > 1: self.service_results.pop(0)
        elif 'restart' in command:
            if self.after_restart:
                self.service_results = [service()]
                self.query = subprocess.CompletedProcess([], 0, 'Asterisk 22.0 fixture', '')
                self.state = health.build_state()
            return subprocess.CompletedProcess(command, 0, '', '')
        elif command[-1] == 'core show version': value = self.query
        elif command[-1].startswith('rpt show variables '): value = self.node
        else: raise AssertionError('Unexpected external command: ' + repr(command))
        if isinstance(value, Exception): raise value
        return value

    def cycle(self):
        coordinator = monitor.RecoveryCoordinator(thread_factory=ImmediateThread)
        return monitor.run_health_cycle(coordinator)

    def assert_no_restart(self):
        self.assertFalse(any('restart' in command for command in self.calls))
        self.assertFalse(any(event['event'] == 'RECOVERY.ASTERISK.ATTEMPT' for event in self.events))

    def test_original_false_restart_matrix_real_pipeline(self):
        failures = [subprocess.CompletedProcess([], 1, '', reason) for reason in
                    ('CLI failed', 'socket unavailable', 'permission denied', 'sudo denied', 'broker denied')]
        failures += [subprocess.TimeoutExpired('fixture', 5), PermissionError('fixture'),
                     FileNotFoundError('fixture'), RuntimeError('unexpected collector failure'),
                     subprocess.CompletedProcess([], 0, '', ''),
                     subprocess.CompletedProcess([], 0, 'unexpected output', '')]
        for failure in failures:
            with self.subTest(failure=repr(failure)):
                self.query = failure; self.events.clear(); self.calls.clear()
                for _ in range(3):
                    state = self.cycle(); self.previous = state
                self.assert_no_restart()
                self.assertEqual(state['asterisk'], 'online')
                self.assertEqual(state['status'], 'degraded')
                self.assertIn('cannot query', state['intelligence']['summary'])
                self.assertEqual(state['health']['app_rpt'], 'unknown')
                self.assertFalse(any(e['event'] == 'ASTERISK.OFFLINE' for e in self.events))
                records = intelligence.build_incident_records(self.events)
                self.assertFalse(any(record['component'] == 'asterisk' for record in records))
                self.assertLessEqual(sum(e['event'] == 'HEALTH.ASTERISK_QUERY.WARNING' for e in self.events), 1)

    def test_unknown_service_and_positive_pid_never_restart(self):
        self.query = PermissionError('fixture')
        for result in (service('failed', 'failed', 123), service('active', 'running', 0),
                       service('inactive', 'dead', 0, 'not-found'), service('activating', 'start', 0),
                       subprocess.CompletedProcess([], 1, '', ''), PermissionError('fixture'),
                       subprocess.TimeoutExpired('fixture', 5), RuntimeError('fixture'),
                       subprocess.CompletedProcess([], 0, 'MainPID=invalid', '')):
            with self.subTest(result=repr(result)):
                self.service_results = [result]
                state = self.cycle()
                self.assertEqual(state['asterisk'], 'unknown')
                self.assert_no_restart()

    def test_genuine_stopped_and_failed_can_recover(self):
        for active, sub in [('inactive', 'dead'), ('failed', 'failed')]:
            with self.subTest(active=active):
                self.auto = automation.default_state(); self.calls.clear(); self.verified_results.clear()
                self.service_results = [service(active, sub, 0)]
                self.query = PermissionError('fixture')
                self.cycle()
                self.assertEqual(sum('restart' in c for c in self.calls), 1)
                self.assertEqual(self.verified_results[-1][0], 'success')

    def test_service_changes_during_confirmation_and_final_race(self):
        stopped = service('inactive', 'dead', 0)
        for stage in (1, 2, 3):  # Worker entry, after delay, final pre-action check.
            for changed in (service(), PermissionError('fixture')):
                with self.subTest(stage=stage, changed=repr(changed)):
                    self.auto = automation.default_state(); self.calls.clear(); self.events.clear()
                    self.service_results = [stopped] * stage + [changed]
                    self.query = PermissionError('fixture')
                    self.cycle()
                    self.assert_no_restart()
                    self.assertEqual(self.auto['consecutive_failures'], 0)
                    self.assertNotEqual(self.auto['mode'], 'recovering')

    def test_stale_saved_offline_cannot_authorize_worker(self):
        evidence = {'status': 'offline', 'main_pid': 0, 'active_state': 'inactive',
                    'sub_state': 'dead', 'load_state': 'loaded', 'observed_at': time.time() - 60}
        self.state = {'asterisk': 'offline', 'asterisk_evidence': {'service': evidence}}
        recovery.recover_asterisk()
        self.assert_no_restart()
        self.assertEqual(self.calls, [])

    def test_app_rpt_invalid_or_partial_is_not_an_outage(self):
        for output in ('No such node', 'No such command', '', 'garbage',
                       'RPT_RXKEYED=0\nRPT_TXKEYED=0\n',
                       VALID_NODE.replace('RPT_ALINKS=0', 'RPT_ALINKS=1'),
                       VALID_NODE.replace('RPT_TXKEYED=0', 'RPT_TXKEYED=invalid')):
            with self.subTest(output=output):
                self.node = subprocess.CompletedProcess([], 0, output, '')
                state = self.cycle()
                self.assertEqual(state['asterisk'], 'online')
                self.assertEqual(state['health']['app_rpt'], 'warning')
                self.assert_no_restart()
                self.assertFalse(recovery.allstar_reachable())
        self.assertEqual(observation.node_evidence('invalid')['reason'], 'invalid_node_configuration')

    def test_valid_empty_and_populated_upstream_links(self):
        for link_value, count in [('', '0'), ('0', '0'), ('1,23456TU', '1'), ('2,23456TU,34567RK', '2')]:
            with self.subTest(links=link_value):
                self.node = subprocess.CompletedProcess([], 0,
                    'RPT_RXKEYED=0\nRPT_TXKEYED=0\nRPT_ALINKS=' + link_value + '\nRPT_NUMALINKS=' + count + '\n', '')
                self.assertEqual(observation.node_evidence()['status'], 'available')
        self.node = subprocess.CompletedProcess([], 0, VALID_NODE + 'RPT_NUMALINKS=2\n', '')
        self.assertEqual(observation.node_evidence()['status'], 'unavailable')

    def test_wrong_numeric_node_and_stale_post_recovery_state(self):
        self.node = subprocess.CompletedProcess([], 0, 'No such node', '')
        with patch.object(observation, 'NODE', '23456'):
            state = self.cycle()
        self.assertEqual(state['asterisk_evidence']['node']['reason'], 'node_not_found')
        self.assertTrue(any(c[-1] == 'rpt show variables 23456' for c in self.calls))
        self.assert_no_restart()
        self.node = subprocess.CompletedProcess([], 0, VALID_NODE, '')
        self.state = health.build_state()
        self.state['asterisk_evidence']['service']['observed_at'] = time.time() - 60
        with patch.object(recovery.time, 'monotonic', side_effect=[0, 0, 2]):
            passed, _ = recovery.verify_recovery(0, timeout=1)
        self.assertFalse(passed)

    def test_query_restore_resolves_access_incident_not_process_outage(self):
        self.query = PermissionError('fixture'); self.previous = self.cycle()
        self.query = subprocess.CompletedProcess([], 0, 'Asterisk 22.0 fixture', '')
        state = self.cycle()
        records = state['intelligence']['incidents']
        self.assertTrue(any(r['component'] == 'asterisk_query' and r['resolved'] for r in records))
        self.assertFalse(any(e['event'] in ('ASTERISK.OFFLINE', 'ASTERISK.ONLINE') for e in self.events))
        self.assert_no_restart()

    def test_post_recovery_requires_service_and_node_evidence(self):
        self.state = health.build_state()
        for service_result, node_output in [(service('inactive', 'dead', 0), VALID_NODE),
                                            (service(), 'No such node')]:
            self.service_results = [service_result]
            self.node = subprocess.CompletedProcess([], 0, node_output, '')
            with patch.object(recovery.time, 'monotonic', side_effect=[0, 0, 2]):
                passed, _ = recovery.verify_recovery(0, timeout=1)
            self.assertFalse(passed)


if __name__ == '__main__': unittest.main()
