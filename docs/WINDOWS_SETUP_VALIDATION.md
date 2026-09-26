# Windows setup validation

Release candidate: **0.1.3-alpha.1**, checked 2026-09-25. This is an early-testing
alpha, not a claim of universal hardware compatibility.

## 0.1.6-alpha.1 release validation (September 26, 2026)

- Rebuilt the self-contained Windows x64 executable and passed its embedded
  package/runtime check. Every payload file matches release source, including
  shared favorites and the authentication-required gateway fix.
- Repeated actual Windows session tests against an isolated Debian 12 ASL3 VM:
  key login, password login with password-required sudo, rejected password and
  untrusted host, opening an existing installation, and fresh installation with
  a deliberately disconnected/reconnected client. The private tunnel and station
  identity passed. Asterisk process/configuration stayed unchanged.
- Repeated actual guided update, injected installer failure with healthy rollback,
  occupied-port refusal, failed fresh-install cleanup, successful fresh install,
  and refusal to overwrite an existing installation. Radio identity/configuration
  stayed unchanged through every phase.
- All 268 Python tests passed in the isolated Linux fixture; the workstation run
  passed with six platform skips. All three namespace-isolated deployment
  scenarios, all 14 JavaScript suites, Windows deployment checks, and the
  tracked-source privacy check passed.
- Shared-favorites checks include two independent browser contexts and an
  operator-confirmed phone/PC check on a reviewed customized installation. See
  [the favorites validation record](SHARED_FAVORITES_VALIDATION.md).

These checks support publishing an alpha for external testing. They do not
establish universal compatibility or replace wider hardware/endurance testing.

## 0.1.5-alpha.1 package refresh

The 0.1.5-alpha.1 Windows executable passed a new self-contained build and
runtime/embedded-package check. Every bundled file was compared byte-for-byte
with the release source, including the new Favorites controls, Auto-switch,
and dashboard guide. The tracked-source privacy check passed. The installer now also displays a feedback note and GitHub issue link. The installation
engine and Windows connection/install logic are unchanged from the integration validation below;
the full VM installation exercise was not repeated for this dashboard refresh.
The same hardware and external-testing limits still apply.

## Completed

- Built the self-contained Windows x64 executable with .NET SDK 8.0.425,
  runtime 8.0.31, and locked SSH.NET 2026.0.0 dependencies. The packaged executable
  passed its runtime/embedded-release check. No separate end-user SDK is needed.
- Rendered and inspected the Windows form; the app provides address/login,
  detected station, confirmation, progress, and dashboard access.
- Tested the actual Windows SSH/session code against a checkpointed, isolated
  Debian 12 ASL3 VM with no radio hardware. Both SSH-key login/passwordless sudo
  and password login/password-required sudo passed.
- Rejected an untrusted host identity and an incorrect login password.
- Detected and opened an older existing installation through an automatic
  loopback tunnel without replacing its files/settings. Older versions without
  the welcome page open the dashboard directly.
- Installed a fresh node, deliberately disconnected the Windows client after
  starting setup, then reconnected and verified completion, the welcome page,
  live dashboard, and the expected node identity through the tunnel.
- Injected a failing installer into a disposable lab source copy. The detached
  worker reported failure, removed its partial installation/service account,
  and preserved Asterisk. A subsequent fresh install succeeded.
- Compared Asterisk PID/start identity and hashes of all `/etc/asterisk` files
  across the install/failure cases: unchanged. Checked all three services were
  healthy after successful installation and automatic recovery remained off.
- Backend regression: 253 tests passed as the installed service user. With an
  additional low-disk-space guard test, all 254 passed inside the isolated
  installer fixture. All 12 JavaScript/dashboard suites passed on Windows/Edge.
- All three namespace-isolated installer/deployment scenarios, Windows deployment
  tooling tests, and the tracked-source privacy check passed.
- The isolated Linux installer fixture needed a larger temporary filesystem
  (256 MiB) so its copied OS tools leave the updater's required 64 MiB reserve.
  The production reserve was not reduced; its refusal is tested separately.

## Limits

The Windows app supports fresh installation and opening existing installations.
Updates/restoration use the existing explicit guided CLI flow. It requires an
already working Debian 12 ASL3 node, SSH, Python, sudo access, and the standard
installer prerequisites; it does not image a Pi, recover passwords, configure
ASL3, discover routers, modify firewalls, or expose a dashboard to the Internet.
Passwords are held only in process memory; connection metadata/fingerprints
are saved locally. SSH first-use trust still requires operator verification.

The Windows binary is **unsigned** and may trigger Windows reputation warnings.
Testing used Windows x64 and an amd64 VM. Raspberry Pi hardware, Windows ARM,
unusual authentication methods, and broad external beta/endurance testing are
not covered. Loss of the Windows connection was tested; loss of power to the
node can interrupt installation and requires log review. No production radio
was modified during these checks.

The regular GitHub checks cover Python, dashboard, and repository/deployment
regressions. The Windows executable build/integration checks were run locally;
they are not yet a separate GitHub Actions job. See [build and test commands](../desktop/README.md).
