# Fresh install / new user validation

Validation date: 2026-09-05. Result: **PASS for public-tree clean-install
simulation**, with physical-machine limits stated below.

## Architecture and evidence

The installer was exercised from public source in a newly created Debian 12
ARM64 chroot with Python 3.11, inside private mount, network, and PID namespaces.
The fixture began without `/opt/nodesmart`, BlueNode units, sudoers fragments,
runtime state, logs, credentials, or optional integrations. It copied OS
binaries/standard libraries, not live BlueNode files, into its temporary root.
Asterisk, sudo execution, and systemctl were substituted; the real Asterisk
socket, radio devices, and network were inaccessible inside the fixture.

The actual installer created configuration, stopped before service changes,
rejected unchanged example identity values, then installed after generic
operator configuration. The actual installed monitor completed its first
health/Intelligence cycle as an unprivileged account. The installed HTTP handler
served dashboard assets, state, and disabled/unconfigured API states as that
account. Separate HTTP and whole-script JavaScript tests exercised the period
before any monitoring data exists.

Repeated installation preserved config/history and ownership. Missing required
source and malformed sudoers content failed before changing code or service
state. Simulated startup failure returned nonzero and retained config/history.
Real `visudo -c` and `systemd-analyze verify` accepted generated files; service
operations were checked through a constrained fake systemctl, not a live PID 1.
Generic Asterisk/App_Rpt/radio configuration sentinels remained byte-identical.
No firewall command or Asterisk restart was issued by the installer.

## Defects corrected

- Automatic firewall opening removed; new listener defaults to loopback.
- Automatic Asterisk recovery made explicit opt-in, including runtime fallback
  and accurate disabled reporting in Automated Operations.
- Unrestricted Asterisk CLI sudo access replaced with a root-owned validating
  broker. Numeric connection controls remain supported; arbitrary CLI, module
  loading, channel origination, and shell commands are rejected.
- Code and root-invoked helpers made root-owned. Runtime and config permissions
  explicitly set; application readability no longer depends on checkout umask.
- First installation now stops before adding privileges/units; configuration
  and public-source preflight catch invalid inputs before deployment.
- Missing core telemetry now clears confidence to unavailable; missing event
  history is explicit, and absent SkywarnPlus disables its controls.
- Clone/prerequisite/account/configuration/access/update instructions supplied;
  code-only developer deployment rejects an unmigrated broker installation.
- Linux scripts/helpers/units/Python files have explicit LF checkout rules.

## Regression coverage

- Python: **132 tests**, all passing on Debian ARM64, **zero skips**.
- Windows Python: **132 tests**, passing with **two POSIX pseudo-terminal
  skips**; those terminal tests passed inside the Debian fixture.
- One clean-install integration lifecycle covering the stages above.
- Three JavaScript suites: dashboard rendering/polling, whole-script empty
  first load, and Remote Access/Remote Admin/Soft Radio framework checks.
- Python compilation, shell syntax (including extensionless helpers), generated
  systemd/sudoers validation, deployment preflight fixtures, privacy guard,
  whitespace validation, and tracked-public-tree integrity checks.

The Python suite includes Remote Admin/security, Recovery, Intelligence,
Connectivity, Emergency Mode, Radio Activity/TX-origin, Node Behavior, and
parked Soft Radio safety/transaction regressions. Five new Python tests live
in `core/test_fresh_install.py`; the repeatable Debian fixture is
`deploy/test_clean_install.py`, and the full first-load JavaScript test is
`core/test_fresh_dashboard.js`.

## Production read-only check and limits

The existing production installation remained active and healthy. Asterisk's
PID/start timestamp remained unchanged. Both BlueNode services were active;
the dashboard and read-only APIs returned HTTP 200. Node Behavior was NORMAL
with current evidence, Connectivity was healthy/current, Emergency Mode was
normal, and Remote Admin was enabled while the unauthenticated session remained
unauthenticated. This run did not deploy the changed installer or application
to production.

This validates public-repository bootstrap and first-run behavior, not a
physical clean-ASL3 certification. A separate clean ASL3 machine should still
confirm actual systemd enable/boot/restart behavior, distribution package
installation, real sudo/PAM enforcement, Asterisk/App_Rpt version compatibility,
and optional integrations. The isolated fixture intentionally cannot validate
real RF/audio behavior or live Internet reachability. No Asterisk restart,
App_Rpt/radio change, intentional PTT/RF transmission, host firewall change,
or public exposure was performed.

Before UI/UX polish, repeat the documented install on that separate ASL3 machine
and schedule any production installer migration deliberately. Soft Radio stays
parked; Net Mode/NetMap remain deferred.
