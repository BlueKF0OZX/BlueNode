# Guided setup validation — September 25, 2026

Scope: 0.1.2-alpha.1 guided installation on an existing Debian 12 ASL3 node.
This does not certify blank-Pi provisioning, other distributions, live RF,
Internet HTTPS gateways, or long-term unattended operation.

## Checks completed

- Nine focused setup tests cover local include discovery, template exclusion,
  call identity, traversal refusal, trusted-network confirmation, allowed listener
  selection, occupied ports, existing-file protection, incomplete backup refusal,
  and failed-update restoration of code/settings/history. The transaction case
  runs on Linux; it is skipped on Windows.
- Full Python suite: 245 tests passed on Debian 12 as the service user with the
  public example configuration.
- All 12 dashboard suites passed using synthetic observations. The welcome page
  was checked at phone and desktop widths, including unavailable station data,
  escaped text, and absence of mutation requests. Mobile layout was visually inspected.
- Existing namespace-isolated installer/deployment suite passed all three
  lifecycle and rollback cases; Asterisk/systemd are substituted in those cases.

## Real ASL3 disposable lab

The existing lab was checkpointed before testing. It has no attached radio
hardware and an isolated private-peer configuration. Production was not changed.

The following checks ran against the lab's real systemd and Asterisk/App_Rpt:

1. Existing installation check returned its dashboard URL without reconfiguration.
2. Update backed up the previous installation and preserved settings.
3. An intentionally failing installer restored the preceding working dashboard.
4. An occupied web port was refused before installation mutation.
5. A deliberately failed fresh install removed its incomplete files/account.
6. Fresh installation created the dedicated service account, enabled both BlueNode
   services, served the dashboard, and obtained a successful local App_Rpt observation.
7. A second installation attempt refused to overwrite the working installation.
8. Explicit restoration recovered the saved settings and a healthy dashboard,
   preserved the pre-restore files in a separate backup, and left Asterisk unchanged.

Asterisk process identity and `/etc/asterisk` file hashes remained unchanged through
these cases. Retired legacy health units were detected and refused by guided updates;
the lab fixture then removed its inactive legacy units to test the supported layout.

## Boundaries

- The downloader installs missing packages; those package changes are not rolled
  back with BlueNode. It never runs a distribution upgrade.
- Setup defaults to loopback. Trusted-LAN access is an explicit choice and has no
  default password. Authenticated HTTPS remains a separate optional setup.
- Guided updates require healthy/enabled BlueNode services, matching service users,
  recovery disabled, and no legacy health units. Custom deployments keep the manual path.
- Backups contain private configuration/history and remain root-only. Rollback
  cannot reverse unrelated concurrent edits or external outages.
- Hardware-specific endurance testing and feedback from independent operators
  remain outstanding. The release stays alpha.
