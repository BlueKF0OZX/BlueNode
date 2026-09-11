import subprocess
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


if __name__ == '__main__':
    unittest.main()
