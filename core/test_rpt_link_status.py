"""Synthetic transport observations; these do not certify live App_Rpt formats."""
import copy
import unittest

from rpt_link_status import reconcile
from radio_activity import classify

HEADER = 'NODE PEER RECONNECTS DIRECTION CONNECT TIME CONNECT STATE\n--------------------\n'


class LinkStatusTests(unittest.TestCase):
    def setUp(self):
        self.sample = dict(local_rx=False, local_tx=False,
                           links=[dict(node='23456', mode='T', keyed=True)])

    def test_established_and_pending_links(self):
        original = copy.deepcopy(self.sample)
        for state in ['ESTABLISHED', 'CONNECTING']:
            with self.subTest(state=state):
                result = reconcile(self.sample, HEADER + f'23456 192.0.2.1 0 OUT 00:01:00 {state}\n')
                activity = classify(result)
                self.assertEqual(activity['connected_nodes'], ['23456'] if state == 'ESTABLISHED' else [])
                self.assertEqual(result['links'][0]['keyed'], state == 'ESTABLISHED')
        self.assertEqual(self.sample, original)

    def test_empty_matching_observations(self):
        sample = dict(self.sample, links=[])
        self.assertEqual(reconcile(sample, HEADER), sample)

    def test_racing_and_invalid_observations_are_unavailable(self):
        valid = '23456 192.0.2.1 0 OUT 00:01:00 ESTABLISHED\n'
        for output in ['', 'Command not found', HEADER, HEADER + valid + valid,
                       HEADER + valid.replace('23456', '34567'),
                       HEADER + valid.replace('ESTABLISHED', 'UNKNOWN'),
                       HEADER + valid.replace(' OUT ', ' SIDEWAYS '),
                       HEADER + valid.replace(' 0 ', ' invalid ')]:
            with self.subTest(output=output):
                self.assertIsNone(reconcile(self.sample, output))


if __name__ == '__main__':
    unittest.main()
