"""Nonblocking, whole-system Linux CPU utilization between observations."""

from pathlib import Path


class CpuUsage:
    def __init__(self, path=Path('/proc/stat')):
        self.path = path
        self.previous = None

    def sample(self):
        try:
            with self.path.open() as source:
                fields = source.readline().split()
            if fields[0] != 'cpu' or len(fields) < 5:
                raise ValueError('Missing aggregate CPU counters')
            # guest and guest_nice are already counted in user and nice.
            counters = tuple(int(value) for value in fields[1:9])
            if any(value < 0 for value in counters):
                raise ValueError('Negative CPU counter')
        except (OSError, ValueError, IndexError):
            self.previous = None
            return None
        previous, self.previous = self.previous, counters
        if previous is None or len(previous) != len(counters):
            return None
        deltas = [current - old for current, old in zip(counters, previous)]
        # Rebaseline after counter resets, including decreasing iowait.
        if any(delta < 0 for delta in deltas):
            return None
        total = sum(deltas)
        if total <= 0:
            return None
        idle = deltas[3] + (deltas[4] if len(deltas) > 4 else 0)
        return round(100 * (total - idle) / total, 1)


get_cpu_usage = CpuUsage().sample
