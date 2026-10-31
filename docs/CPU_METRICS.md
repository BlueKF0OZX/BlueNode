# CPU utilization

The temperature card also displays whole-system CPU utilization as a percentage
of aggregate CPU capacity, rounded to one decimal place. It is independent of
the existing temperature health thresholds.

The health worker reads the aggregate `/proc/stat` counters once per observation.
The percentage is busy counter change divided by total counter change; idle and
iowait are excluded from busy time. Guest counters are not counted twice.
There is no sampling sleep, subprocess, or added dependency.

The existing health loop and dashboard poll every two seconds. The percentage
covers the actual time between health observations, which may exceed two seconds
when other work is slow. It is not an instantaneous or per-process measurement.
The first observation, invalid reads, unchanged counters, and counter resets
produce `null` (`N/A` in the dashboard). Stale or unavailable snapshots clear the
display through the existing freshness checks. Troubleshooting reports include
the cached CPU percentage.
