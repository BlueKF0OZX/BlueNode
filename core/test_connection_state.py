import json
import tempfile
import unittest
from datetime import datetime, timezone, timedelta
from pathlib import Path
from unittest.mock import patch

import allstar_status
import connection_state
import connection_stats
import health


class ConnectionStateTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.path = Path(temporary.name) / 'allstar.json'
        self.started = (datetime.now(timezone.utc) - timedelta(minutes=5)).isoformat()
        for module, name in ((allstar_status, 'STATE_FILE'), (connection_stats, 'ALLSTAR_STATE_FILE'),
                             (health, 'ALLSTAR_STATE_FILE')):
            context = patch.object(module, name, self.path)
            context.start(); self.addCleanup(context.stop)
        context = patch.object(connection_stats, 'HISTORY_FILE', self.path.parent / 'history')
        context.start(); self.addCleanup(context.stop)

    def test_nested_corruption_and_truncation_never_create_sessions(self):
        valid = {'links': ['50241'], 'connected_since': {'50241': self.started}}
        cases = ['{', '[]', 'null', '{}', '{"links":["99999"],"links":[],"connected_since":{}}', json.dumps({'connected_since': []})]
        for key, values in {'links': [None, {}, [None], [['50241']], ['50241', '50241']],
                            'connected_since': [None, [], {'50241': []}, {'50241': 'bad'},
                                                {'99999': self.started}, {'50241': '2099-01-01'}]}.items():
            cases.extend(json.dumps(dict(valid, **{key: value})) for value in values)
        for raw in cases:
            with self.subTest(raw=raw):
                self.path.write_text(raw)
                for state in (allstar_status.load_state(), health.get_allstar_state()):
                    self.assertFalse(state['state_available'])
                    self.assertEqual(state['links'], [])
                    self.assertEqual(state['connected_since'], {})
                self.assertEqual(connection_stats.load_active_connections(), {})
                summary = connection_stats.summarize_connections()
                self.assertFalse(summary['state_available'])
                self.assertEqual(summary['active_connections'], 0)
                self.assertEqual(summary['recent_sessions'], [])

    def test_missing_oversized_and_invalid_utf8(self):
        self.assertFalse(connection_state.load(self.path)['state_available'])
        for raw in (b'\xff', b'x' * (connection_state.MAX_BYTES + 1)):
            self.path.write_bytes(raw)
            self.assertFalse(connection_stats.summarize_connections()['state_available'])

    def test_valid_existing_state_and_empty_state(self):
        self.path.write_text(json.dumps({'links': ['50241'], 'connected_since': {'50241': self.started}}))
        summary = connection_stats.summarize_connections()
        self.assertTrue(summary['state_available'])
        self.assertEqual(summary['active_connections'], 1)
        self.path.write_text('{"links":[],"connected_since":{}}')
        self.assertTrue(connection_stats.summarize_connections()['state_available'])
        self.assertEqual(connection_stats.summarize_connections()['active_connections'], 0)

    def test_history_skips_invalid_nested_fields_and_retains_valid_session(self):
        ended = datetime.now(timezone.utc).isoformat()
        valid = {'node': '50241', 'name': 'DODROPIN', 'connected_at': self.started, 'disconnected_at': ended}
        rows = [None, [], {'node': '50241'}, dict(valid, connected_at=[]), dict(valid, name={}), valid]
        connection_stats.HISTORY_FILE.write_text('\n'.join(json.dumps(row) for row in rows) + '\n{')
        self.assertEqual(connection_stats.load_history(), [valid])
        self.assertEqual(connection_stats.summarize_connections()['recent_sessions'], [valid])

    def test_fresh_observation_replaces_invalid_state_without_fake_history(self):
        self.path.write_text('{"links":["99999"],"connected_since":[]}')
        sample = {'local_rx': False, 'local_tx': False, 'links': [{'node': '50241', 'mode': 'T', 'keyed': False}]}
        with patch.object(allstar_status, 'get_telemetry', return_value=sample), \
             patch.object(allstar_status.radio_activity, 'update'), patch.object(allstar_status, 'emit'), \
             patch.object(allstar_status, 'save_connection_history') as history:
            allstar_status.check_changes()
        history.assert_not_called()
        state = connection_state.load(self.path)
        self.assertTrue(state['state_available'])
        self.assertEqual(state['links'], ['50241'])


if __name__ == '__main__': unittest.main()
