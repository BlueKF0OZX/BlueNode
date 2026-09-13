# Validation status

Review date: 2026-09-13. Status: unreleased alpha candidate for supervised early
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
