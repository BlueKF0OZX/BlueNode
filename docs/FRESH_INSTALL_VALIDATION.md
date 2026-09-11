# Clean-install validation

The repeatable Debian fixture is deploy/test_clean_install.py. Run it with sudo from a separate checkout on a disposable Debian host. It builds a temporary chroot inside private mount, network, and PID namespaces and substitutes service/Asterisk operations. It does not access a real radio device or Asterisk socket.

Coverage includes first-pass configuration creation, rejection of example identity, repeated installation, unchanged operator configuration, service ownership and permissions, sudoers parsing, systemd unit syntax, optional-component absence, initial monitor/web responses, dashboard-only deployment rollback, and full deployment intent rollback. It also runs the Python suite inside the isolated filesystem.

Windows can run configuration-validator, HTTP, backend, browser, and temporary-repository preflight tests. It cannot establish real systemd startup, boot persistence, sudo/PAM enforcement, POSIX file security, or App_Rpt/socket compatibility. Linux fixture success is also not physical-ASL3 certification: package installation, actual service behavior, radio/audio boundaries, and proxy/upstream integration need a disposable ASL3 host.

BlueNode starts without SkywarnPlus. Remote Admin remains disabled until deliberately configured. Recovery is disabled in the example configuration. Soft Radio RX stays parked; browser TX/PTT, Net Mode, and Net Map are unsupported. See [Installation](INSTALL.md), [Upgrade](UPGRADE.md), and [Testing](TESTING.md).
