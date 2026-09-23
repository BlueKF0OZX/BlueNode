# Validation status

Review date: 2026-09-23. Status: unreleased alpha candidate for supervised early
evaluation, not a production-certified release. Record the exact installed
commit when reporting results. No new stable release or tag is implied.

## Completed checks

| Area | Evidence and scope |
| --- | --- |
| Installation and reboot | Earlier Debian 12 / ASL3 lab work verified configuration-only first pass, configured installation, repeat installation, and reboot persistence. The installer corrections were published in commit `5fe8fca`. |
| Upgrade and restoration | That lab verified retirement of the obsolete health timer and exact restoration of inventoried files, permissions, and absent paths. Asterisk was not restarted by the upgrade or restoration. The prior-release lab archive needed shell line-ending normalization; this was not a test of that archive unchanged. |
| Current installer regression | All three isolated Linux installer/rollback scenarios passed with the candidate's link-status observation fixtures. Service and Asterisk operations are substituted in this fixture; it supplements the live evidence above. |
| Core regression | All 214 tests passed on Linux. The Windows run passed with three platform-specific skips. |
| Dashboard | Eight JavaScript/browser suites passed, including five display widths, authentication/control routing, missing and stale state, report preview/download, and direct-file guidance. Browser cases use synthetic observations. |
| Private-peer behavior | Repeated connect/disconnect and idempotent controls passed on two isolated ASL3 peers. During a peer outage, reconnecting transport no longer appears as an established connection. BlueNode-only restarts preserved the observed Asterisk process and channel list. |
| Installed security baseline | All 35 collector checks passed for service accounts, ownership/modes, unit definitions, loopback listeners, command broker, and positive/negative sudo authorization. |
| Application authentication | Lab checks passed for login/logout, cookie flags, CSRF rejection, and locked controls with missing, malformed, or incomplete credentials. The original disabled configuration was restored. These loopback tests do not certify an external HTTPS gateway. |

Lab platform: Debian 12 amd64, ASL3 metapackage `3.18.2-2.deb12`,
Asterisk/App_Rpt package `2:22.9.0+asl3-3.9.3-1.deb12`. The live checks used a
working candidate tree containing the link-status fix; installation/reboot
evidence from the earlier baseline is identified separately above. Results
do not automatically cover another OS, package version, or future commit.

## September 23 connection/activity follow-up

The draft connection/activity branch was tested on two disposable Debian 12 / ASL3
VMs with an internal-only peer network, outbound firewall restrictions, no radio
hardware, and automatic recovery disabled. The initial installed revision was
`c9e7255`; the pending-transport correction and test-fixture changes accompanying
this record were then applied and tested.

- Three real connect/disconnect cycles and repeated already-satisfied requests
  passed through the dashboard control API.
- With the peer stopped, App_Rpt exposed an outbound CONNECTING transport before
  adding it to its link variables. The corrected reconciliation retains that
  transport as pending. Both attempts returned a pending result; the second
  attempt sent **no duplicate command**, as recorded in the failure diagnostics.
- After the peer restarted, a connect/disconnect recovery cycle passed.
- Stopping only the collector for eight seconds left the web service available
  and produced observation age above the six-second activity expiry threshold.
  Collection resumed after restart. This checks the live data path; stale display
  behavior is covered by the dashboard suites using synthetic observations.
- The local Asterisk process identity remained unchanged across installation,
  BlueNode restarts, controls, peer outage, and collector interruption. Operator
  configuration was preserved by installation.
- All **230 Python tests passed on Linux** as the service user. Windows passed
  227 with three platform-specific skips. A media-test fixture now uses the test
  user's ownership and a bounded socket wait; production permission checks are
  unchanged. The preceding dashboard validation passed all 11 suites, including
  five display widths; this follow-up changes no dashboard code.

These are short supervised private-peer checks, not live RF acceptance, external
HTTPS/proxy acceptance, or an endurance run. No production deployment is included.

## Incomplete or outside this evaluation

- The proposed 24-hour stability run was stopped after eight samples. It is
  **incomplete**, not a pass. Sustained resource trends and loaded-dashboard
  endurance remain unverified. Short supervised sessions can provide additional
  evidence, but do not count as an uninterrupted 24-hour run.
- Sampled private-link observations do not prove the absence of every brief
  interruption or establish RF/audio quality.
- Physical radio interfaces, arm64/Pi performance, thermals, SD-card behavior,
  and a constrained-hardware endurance run need separate operator evaluation.
- External HTTPS/proxy boundaries and the optional weather observer need
  validation against the intended installation and upstream version.
- Soft Radio remains parked. Browser TX/PTT, Net Mode, and Net Map are not part
  of the supported first-user path.

For a first evaluation, keep automatic recovery disabled and follow
[Trying BlueNode](EARLY_TESTING.md). Full release acceptance remains open;
this document distinguishes demonstrated behavior from remaining work.
