import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import runtime_io
import event_logger
import allstar_status
import connection_stats
import radio_activity


class RuntimeIOTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.path = Path(temporary.name) / 'data'

    def test_rotation_retains_bounded_complete_records(self):
        for i in range(30):
            runtime_io.append_bounded(self.path, json.dumps({'i': i}), maximum=64)
        files = list(self.path.parent.glob('data*'))
        self.assertLessEqual(len(files), 4)  # current, two archives, lock
        self.assertTrue(all(p.stat().st_size <= 64 for p in files))
        records = [json.loads(line) for line in runtime_io.tail_lines(self.path, 64, backups=2)]
        self.assertEqual(records[-1], {'i': 29})
        self.assertEqual([r['i'] for r in records], sorted(r['i'] for r in records))

    def test_legacy_oversized_log_is_bounded_on_next_append(self):
        self.path.write_text('old record\n' * 100)
        runtime_io.append_bounded(self.path, 'new record', maximum=64)
        self.assertTrue(all(p.stat().st_size <= 64 for p in self.path.parent.glob('data*')))

    def test_future_radio_state_is_unavailable(self):
        self.path.write_text(json.dumps({'last_update': '2099-01-01T00:00:00+00:00'}))
        with patch.object(radio_activity, 'STATE_FILE', self.path):
            self.assertTrue(radio_activity.public_state()['stale'])

    def test_atomic_failure_preserves_previous_state(self):
        runtime_io.atomic_json(self.path, {'old': True})
        with patch.object(runtime_io.os, 'replace', side_effect=OSError('fixture')):
            with self.assertRaises(OSError):
                runtime_io.atomic_json(self.path, {'new': True})
        self.assertEqual(json.loads(self.path.read_text()), {'old': True})
        self.assertEqual(list(self.path.parent.glob('*.tmp')), [])

    def test_history_skips_corrupt_and_non_object_records(self):
        self.path.write_text('null\n[]\n{\n{"node":"50241"}\n')
        with patch.object(connection_stats, 'HISTORY_FILE', self.path):
            self.assertEqual(connection_stats.load_history(), [{'node': '50241'}])

    def test_logging_failure_does_not_interrupt_monitoring(self):
        with patch.object(event_logger, 'append_bounded', side_effect=OSError('fixture')):
            event_logger.emit('FIXTURE.EVENT', 'safe message')

    def test_allstar_state_is_atomic_and_corrupt_data_is_ignored(self):
        with patch.object(allstar_status, 'STATE_FILE', str(self.path)):
            allstar_status.save_state({'50241'}, {'50241': '2026-01-01T00:00:00+00:00'})
            self.assertEqual(allstar_status.load_state()['links'], ['50241'])
            self.path.write_text('[]')
            self.assertEqual(allstar_status.load_state()['links'], [])


if __name__ == '__main__':
    unittest.main()
