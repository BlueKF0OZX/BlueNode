import subprocess
import json
from pathlib import Path
import tempfile
import time
import unittest
from unittest.mock import patch

import node_controls as controls

CONFIG = {'node': '23456', 'friendly_nodes': {'50241': 'DODROPIN'}}


def evidence(mode=None):
    return {'status': 'available', 'observed_at': time.time(),
            'links': [] if mode is None else [{'node': '50241', 'mode': mode}]}


class NodeControlTests(unittest.TestCase):
    def setUp(self):
        self.probe = patch.object(controls.asterisk_observation, 'node_evidence').start()
        self.run = patch.object(controls.subprocess, 'run', return_value=subprocess.CompletedProcess([], 0)).start()
        self.record = patch.object(controls, 'record_failure', return_value=True).start()
        self.addCleanup(patch.stopall)

    def test_connect_and_disconnect_verify_result(self):
        for action, samples, dtmf in [('node-connect', [evidence(), evidence('T')], '*350241'),
                                      ('dodropin-disconnect', [evidence('T'), evidence()], '*150241')]:
            self.probe.side_effect = samples
            code, result = controls.perform(action, {'node': '50241'} if action.startswith('node-') else {}, CONFIG)
            self.assertEqual((code, result['outcome']), (200, 'verified'))
            self.assertEqual(self.run.call_args.args[0][-1], 'rpt fun 23456 ' + dtmf)

    def test_already_satisfied_does_not_send_command(self):
        for action, sample in [('dodropin-connect', evidence('T')), ('dodropin-disconnect', evidence())]:
            self.probe.return_value = sample
            self.assertEqual(controls.perform(action, {}, CONFIG)[1]['outcome'], 'already_satisfied')
        self.run.assert_not_called()

    def test_unavailable_or_stale_observation_blocks_command(self):
        for sample in ({'status': 'unavailable'}, dict(evidence(), observed_at=0)):
            self.probe.return_value = sample
            self.assertEqual(controls.perform('dodropin-connect', {}, CONFIG)[0], 503)
        self.run.assert_not_called()

    def test_command_success_is_not_link_success(self):
        self.probe.return_value = evidence('C')
        with patch.object(controls, 'VERIFY_SECONDS', 0):
            code, result = controls.perform('dodropin-connect', {}, CONFIG)
        self.assertEqual((code, result['outcome']), (504, 'unverified'))

    def test_pending_connection_is_observed_without_duplicate_command(self):
        self.probe.side_effect = [evidence('C'), evidence('T')]
        code, result = controls.perform('dodropin-connect', {}, CONFIG)
        self.assertEqual((code, result['outcome']), (200, 'verified'))
        self.run.assert_not_called()
        self.record.assert_not_called()

    def test_pending_timeout_preserves_link_evidence(self):
        self.probe.return_value = evidence('C')
        with patch.object(controls, 'VERIFY_SECONDS', 0):
            code, result = controls.perform('dodropin-connect', {}, CONFIG)
        self.assertEqual(code, 504)
        self.assertEqual(result['reason'], 'connection_pending')
        self.assertTrue(result['diagnostic_saved'])
        record = self.record.call_args.args[0]
        self.assertEqual(record['id'], result['diagnostic_id'])
        self.assertEqual(record['before']['links'], evidence('C')['links'])
        self.assertEqual(record['last']['links'], evidence('C')['links'])
        self.assertEqual(record['observation_count'], 2)
        self.assertFalse(record['command_sent'])
        self.run.assert_not_called()

    def test_observation_loss_is_not_reported_as_remote_outage(self):
        self.probe.side_effect = [evidence(), {'status': 'unavailable', 'reason': 'timeout'}]
        with patch.object(controls, 'VERIFY_SECONDS', 0):
            code, result = controls.perform('dodropin-connect', {}, CONFIG)
        self.assertEqual(code, 504)
        self.assertEqual(result['reason'], 'observation_lost')
        record = self.record.call_args.args[0]
        self.assertTrue(record['command_sent'])
        self.assertEqual(record['command_returncode'], 0)
        self.run.assert_called_once()

    def test_missing_link_does_not_trigger_blind_retry(self):
        self.probe.return_value = evidence()
        with patch.object(controls, 'VERIFY_SECONDS', 0):
            code, result = controls.perform('dodropin-connect', {}, CONFIG)
        self.assertEqual((code, result['reason']), (504, 'link_not_confirmed'))
        self.run.assert_called_once()

    def test_disconnect_pending_link_still_sends_disconnect(self):
        self.probe.side_effect = [evidence('C'), evidence()]
        self.assertEqual(controls.perform('dodropin-disconnect', {}, CONFIG)[0], 200)
        self.assertEqual(self.run.call_args.args[0][-1], 'rpt fun 23456 *150241')

    def test_busy_control_sends_nothing(self):
        with controls._LOCK:
            self.assertEqual(controls.perform('dodropin-connect', {}, CONFIG)[0], 409)
        self.probe.assert_not_called()
        self.run.assert_not_called()

    def test_diagnostic_failure_does_not_hide_control_result_or_hold_lock(self):
        self.record.return_value = False
        self.probe.return_value = {'status': 'unavailable'}
        code, result = controls.perform('dodropin-connect', {}, CONFIG)
        self.assertEqual(code, 503)
        self.assertFalse(result['diagnostic_saved'])
        self.assertIsNone(result['diagnostic_id'])
        self.probe.return_value = evidence('T')
        self.assertEqual(controls.perform('dodropin-connect', {}, CONFIG)[0], 200)

    def test_timeout_and_rejection_are_not_success(self):
        self.probe.return_value = evidence()
        self.run.side_effect = subprocess.TimeoutExpired('fixture', 15)
        self.assertEqual(controls.perform('dodropin-connect', {}, CONFIG)[0], 504)
        self.run.side_effect = None
        self.run.return_value = subprocess.CompletedProcess([], 1)
        self.assertEqual(controls.perform('dodropin-connect', {}, CONFIG)[0], 502)

    def test_invalid_targets_and_missing_mapping_do_not_execute(self):
        for target in ('23456', '１２３', '5;id', '', 50241):
            self.assertEqual(controls.perform('node-connect', {'node': target}, CONFIG)[0], 400)
        self.assertEqual(controls.perform('dodropin-connect', {}, {'node': '23456'})[0], 503)
        self.assertEqual(controls.perform('node-connect', [], CONFIG)[0], 400)
        self.run.assert_not_called()


class SwitchTests(unittest.TestCase):
    setUp = NodeControlTests.setUp

    def samples(self, *nodes):
        return dict(evidence(), links=[{'node': node, 'mode': mode} for node, mode in nodes])

    def request(self):
        return controls.perform('node-switch', {'from_node': '11111', 'node': '50241'}, CONFIG)

    def test_switch_serializes_steps_and_preserves_unrelated_links(self):
        unrelated = ('33333', 'T')
        self.probe.side_effect = [self.samples(('11111', 'T'), unrelated),
                                 self.samples(unrelated), self.samples(unrelated),
                                 self.samples(('50241', 'T'), unrelated),
                                 self.samples(('50241', 'T'), unrelated)]
        def execute(*args, **kwargs):
            self.assertEqual(controls.perform('node-connect', {'node': '44444'}, CONFIG)[0], 409)
            return subprocess.CompletedProcess([], 0)
        self.run.side_effect = execute
        code, result = self.request()
        self.assertEqual((code, result['phase']), (200, 'complete'))
        self.assertEqual([call.args[0][-1] for call in self.run.call_args_list],
                         ['rpt fun 23456 *111111', 'rpt fun 23456 *350241'])

    def test_disconnect_failure_never_connects(self):
        self.probe.return_value = self.samples(('11111', 'T'))
        with patch.object(controls, 'VERIFY_SECONDS', 0):
            code, result = self.request()
        self.assertEqual((code, result['phase']), (504, 'disconnecting'))
        self.assertEqual(self.run.call_count, 1)
        self.assertEqual(self.run.call_args.args[0][-1], 'rpt fun 23456 *111111')

    def test_pending_target_is_not_reissued_after_disconnect(self):
        self.probe.side_effect = [evidence(), evidence('C'), evidence('T'), evidence('T')]
        self.assertEqual(self.request()[0], 200)
        self.run.assert_not_called()

    def test_connect_failure_has_phase_and_no_rollback(self):
        self.probe.return_value = evidence()
        with patch.object(controls, 'VERIFY_SECONDS', 0):
            code, result = self.request()
        self.assertEqual((code, result['phase']), (504, 'connecting'))
        self.run.assert_called_once()

    def test_final_state_requires_fresh_source_absence_and_target_presence(self):
        for final in (self.samples(('11111', 'T'), ('50241', 'T')), evidence(),
                      dict(evidence('T'), observed_at=0), {'status': 'unavailable'}):
            self.probe.side_effect = [evidence(), evidence('T'), final]
            code, result = self.request()
            self.assertEqual((code, result['phase']), (504, 'verifying'))
            self.assertEqual(self.record.call_args.args[0]['action'], 'node-switch')
        self.run.assert_not_called()

    def test_bad_switch_targets_never_observe_or_execute(self):
        for payload in ({}, {'node': '50241'}, {'node': '50241', 'from_node': '50241'},
                        {'node': '50241', 'from_node': '23456'},
                        {'node': '50241', 'from_node': '1;id'},
                        {'node': 50241, 'from_node': '11111'}):
            self.assertEqual(controls.perform('node-switch', payload, CONFIG)[0], 400)
        self.probe.assert_not_called()
        self.run.assert_not_called()


class AutomaticSwitchTests(unittest.TestCase):
    setUp = NodeControlTests.setUp
    samples = SwitchTests.samples

    def automatic(self, **extra):
        return controls.perform('node-connect', dict(node='50241', replace_current=True, **extra), CONFIG)

    def test_automatic_switch_uses_fresh_peer_and_verified_order(self):
        self.probe.side_effect = [self.samples(('11111', 'T')), self.samples(('11111', 'T')),
                                 evidence(), evidence(), evidence('T'), evidence('T')]
        code, result = self.automatic()
        self.assertEqual((code, result['phase']), (200, 'complete'))
        self.assertEqual([call.args[0][-1] for call in self.run.call_args_list],
                         ['rpt fun 23456 *111111', 'rpt fun 23456 *350241'])

    def test_no_peer_connects_normally(self):
        self.probe.side_effect = [evidence(), evidence(), evidence('T')]
        self.assertEqual(self.automatic()[0], 200)
        self.assertEqual([call.args[0][-1] for call in self.run.call_args_list], ['rpt fun 23456 *350241'])

    def test_same_target_never_disconnects_even_with_other_links(self):
        self.probe.return_value = self.samples(('50241', 'T'), ('33333', 'T'))
        self.assertEqual(self.automatic()[1]['outcome'], 'already_satisfied')
        self.run.assert_not_called()

    def test_several_peers_require_explicit_selection(self):
        self.probe.return_value = self.samples(('11111', 'T'), ('33333', 'C'))
        code, result = self.automatic()
        self.assertEqual((code, result['reason']), (409, 'choose_current_node'))
        self.assertEqual(result['connected_nodes'], ['11111', '33333'])
        self.run.assert_not_called()

    def test_stale_missing_or_malformed_evidence_never_disconnects(self):
        for sample in ({'status':'unavailable'}, dict(evidence(), observed_at=0),
                       dict(evidence(), links=[{}]), dict(evidence(), links=None)):
            self.probe.return_value = sample
            self.assertEqual(self.automatic()[0], 503)
        self.run.assert_not_called()

    def test_invalid_auto_payload_never_observes(self):
        for payload in ({'node':'50241','replace_current':False}, {'node':'23456','replace_current':True},
                        {'node':'bad','replace_current':True}, {'node':'50241','replace_current':'true'},
                        {'node':'50241','replace_current':True,'extra':1}):
            self.assertEqual(controls.perform('node-connect', payload, CONFIG)[0], 400)
        self.probe.assert_not_called()
        self.run.assert_not_called()


class DiagnosticStorageTests(unittest.TestCase):
    def test_writes_structured_record_and_handles_unwritable_storage(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / 'failures.jsonl'
            with patch.object(controls, 'FAILURE_LOG', str(path)):
                self.assertTrue(controls.record_failure({'reason': 'command_timeout'}))
                self.assertEqual(json.loads(path.read_text()), {'reason': 'command_timeout'})
            with patch.object(controls, 'append_bounded', side_effect=OSError):
                self.assertFalse(controls.record_failure({}))

    def test_snapshot_does_not_copy_raw_output_or_credentials(self):
        result = controls.snapshot(dict(evidence(), stdout='private output', password='secret'))
        self.assertNotIn('stdout', result)
        self.assertNotIn('password', result)


if __name__ == '__main__':
    unittest.main()
