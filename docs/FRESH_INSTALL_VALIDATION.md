# Fresh install / new user validation

Validation date: 2026-09-05. Revalidated after weather wording commit `7088c39`.
Result: **PASS WITH LIMITATIONS**. Public-tree installation is a **SIMULATED
PASS**; physical ASL3 integration limits are stated below.

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

## Foundation defects corrected in earlier validation

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

## Current new-user audit

No new installer or backend defect was found. This pass corrects a misleading
README statement about authentication, adds local-node identification and
read-only Asterisk integrity guidance, and documents optional weather onboarding.
The normal installer does not patch SkywarnPlus. New users without SkywarnPlus,
the observer, Tailscale or Remote Admin can bootstrap the core dashboard.

The installed-adapter fixture now explicitly checks absent/current/stale/partial
and disabled weather telemetry, using the producer's atomic replacement contract.
Neither upstream SkywarnPlus nor an external weather service is run by this test.

## Regression coverage

- Python: **145 tests**, all passing on Debian ARM64, **zero skips**.
- Windows Python: **145 tests**, passing with **two POSIX pseudo-terminal
  skips**; those terminal tests passed inside the Debian fixture.
- Two isolated fixture tests: clean-install lifecycle and dashboard-only
  deployment/repeat/rollback. System services and sudo execution are substituted.
- Six JavaScript/browser suites, including five responsive viewport sizes,
  authentication/session/CSRF and control routing, empty first load, dashboard
  polling/rendering, and Remote Access framework checks.
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

Before broad recommendation to unrelated operators, repeat the documented
installation on a genuinely disposable ASL3 host. Package installation,
systemd boot/restart persistence, real sudo/PAM and Asterisk socket permissions,
App_Rpt compatibility, and optional upstream/proxy integration are **NOT TESTABLE
WITHOUT A DISPOSABLE ASL3 HOST** in this fixture. Sudoers parsing and unit syntax
are real checks; authorization execution and service lifecycle are simulated.
No production deployment is required for this documentation/test-only pass.
Soft Radio stays parked; Net Mode/NetMap remain deferred.
