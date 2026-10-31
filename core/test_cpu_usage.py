import io
import unittest
from unittest.mock import Mock

from cpu_usage import CpuUsage


class CpuUsageTests(unittest.TestCase):
    def sampler(self, *lines):
        path = Mock()
        path.open.side_effect = [io.StringIO(line) if isinstance(line, str) else line for line in lines]
        return CpuUsage(path)

    def test_interval_and_guest_not_double_counted(self):
        cpu = self.sampler('cpu 100 0 0 100 0 0 0 0 90 0',
                           'cpu 150 0 0 150 100 0 0 0 140 0')
        self.assertIsNone(cpu.sample())
        self.assertEqual(cpu.sample(), 25.0)

    def test_idle_busy_and_unchanged(self):
        cpu = self.sampler('cpu 0 0 0 0', 'cpu 0 0 0 100',
                           'cpu 100 0 0 100', 'cpu 100 0 0 100')
        self.assertIsNone(cpu.sample())
        self.assertEqual(cpu.sample(), 0.0)
        self.assertEqual(cpu.sample(), 100.0)
        self.assertIsNone(cpu.sample())

    def test_reset_error_and_recovery(self):
        cpu = self.sampler('cpu 100 0 0 100', 'cpu 1 0 0 1',
                           OSError('unavailable'), 'bad', 'cpu 5 0 0 5', 'cpu 10 0 0 10')
        for _ in range(5):
            self.assertIsNone(cpu.sample())
        self.assertEqual(cpu.sample(), 50.0)

    def test_iowait_decrease_rebaselines(self):
        cpu = self.sampler('cpu 100 0 0 100 10', 'cpu 110 0 0 110 5',
                           'cpu 120 0 0 120 5')
        self.assertIsNone(cpu.sample())
        self.assertIsNone(cpu.sample())
        self.assertEqual(cpu.sample(), 50.0)

    def test_invalid_counters_clear_baseline(self):
        for invalid in ['', 'cpu', 'cpu -1 0 0 100', 'cpu nope 0 0 100']:
            with self.subTest(invalid=invalid):
                cpu = self.sampler('cpu 100 0 0 100', invalid,
                                   'cpu 200 0 0 200', 'cpu 210 0 0 210')
                self.assertIsNone(cpu.sample())
                self.assertIsNone(cpu.sample())
                self.assertIsNone(cpu.sample())
                self.assertEqual(cpu.sample(), 50.0)


if __name__ == '__main__':
    unittest.main()
