# BlueNode improvement queue validation

Validated on Windows on 2026-09-11 using Python 3.12, Node, Chrome/Playwright, PowerShell, and Git Bash. This records workstation validation, not certification of an installed AllStar node. All changes are local; no remote deployment, production installation, SSH, tag, or release was performed.

## Completed phases

| Phase | Result |
| --- | --- |
| Initial batch | Centered status-card information while retaining hierarchy and status colors. |
| 1 Dashboard | Improved touch targets, emergency guidance, missing-mapping help, responsive rendering, and wrapping. Exercised 320, 390, 768, 1024, and 1440px, login/Enter, duplicate submits, pending actions, cancellation, navigation, sessions, and events. |
| 2 Remote Admin | Reserved rate-limit attempts before password verification; rejected malformed credentials/CSRF safely; escaped dashboard text; suppressed raw HTTP request logging; tested session, cookie, permission, audit, and configuration states. |
| 3 Asterisk safety | Added conflicting-evidence regression; verified failed CLI does not authorize recovery. Stabilized a simulated recovery timing fixture on Windows without changing production recovery policy. |
| 4 Connectivity | Propagated effective upstream IAX failures to remote links; corrected DNS/Internet explanations and dependency presentation; tested independent failure boundaries. |
| 5 Weather | Enforced read-only integration in UI, routes, helpers, and sudoers template. Preserved bounded observer validation and isolated absent, stale, malformed, and zero-alert states. Final review also bounded YAML status reads and handled invalid UTF-8. |
| 6 Emergency Mode | Clarified monitoring and automatic-recovery boundaries; rejected invalid activation timestamps; audited maintenance actions; tested cancellation and disabled recovery policy. |
| 7 Node controls | Verified outcomes from fresh App_Rpt observations, serialized actions, handled already-satisfied and uncertain states, and retained manual controls without directory data. Example mapping includes 50241 to DODROPIN. |
| 8 TX origin | Labeled adjacent-peer/local-receiver scope and explicitly denied authoritative ultimate-transmitter identification. Radio Activity UI remains absent. |
| 9 Soft Radio | Hardened config reads, WebSocket validation, ticket bounds/expiration/revocation, and teardown. Tested rejection of transmit input. Documented future stuck-PTT/max-duration acceptance criteria; no TX functionality enabled. |
| 10 Installation | Improved dependency/version/configuration errors and optional-component guidance. Preserved explicit node/callsign selection, operator configuration, and disabled-by-default Remote Admin. No real installation performed. |
| 11 Upgrade/rollback | Documented complete configuration-preserving backup, migration review, and rollback. Passed local deployment transaction regression; no automatic general installer migration or rollback invented. |
| 12 Public readiness | Updated install, authentication, weather, testing, and related documentation; replaced stale dashboard screenshot with synthetic observations; checked documentation links and public tree. |
| 13 Release readiness | Added public version endpoint/footer and unreleased changelog structure for 0.1.2-alpha.0. No tag or release; Linux gates remain outstanding. |
| 14 Reliability | Bounded event/history/audit retention and authentication/ticket collections; made connection-state writes atomic; isolated corrupt history, rejected future-dated radio state, bounded/redacted log responses, and prevented overlapping event polls. |
| 15 Final validation | Added event response bounds, quoted-key redaction and weather decoding regressions; aligned documented Python minimum with ASL3 requirements; ran complete supported checks and reviewed the change set. |

## Final test results

Commands run from the repository root using public example configuration and temporary fixtures. See [Testing](TESTING.md) for environment setup and repeatable commands.

| Check | Result |
| --- | --- |
| python -m unittest discover -s core -v | 196 tests in 12.381 seconds: 193 passed, 3 skipped, 0 failures/errors. Includes mocked recovery, connectivity, authentication, weather, node-control, RX, retention, and install validation. |
| node core/test_dashboard.js | PASS: presentation and polling guard. |
| node core/test_fresh_dashboard.js | PASS: first load without state/logs/history/optional integrations. |
| node core/test_remote_access.js | PASS: remote access framework. |
| node core/test_dashboard_render.js | PASS: all five widths, diagnostics, keyboard, emergency mode, missing state, status alignment, touch targets and overflow. |
| node core/test_control_auth.js | PASS: seven controls, resume once, expiry, reload, logout, failure, cancellation, CSRF and injection. |
| node core/test_control_routing.js | PASS: trusted-local, signed-out and authenticated routing. |
| powershell -NoProfile -ExecutionPolicy Bypass -File deploy/Test-DeployBlueNode.ps1 | PASS: temporary local repositories and local bare remote only. |
| Python AST parsing | PASS: 53 Python source files. |
| Bash syntax checks | PASS: 12 shell/helper files. |
| PowerShell parser checks | PASS: 4 scripts. |
| Documentation relative links | PASS. |
| powershell -NoProfile -ExecutionPolicy Bypass -File deploy/Test-PublicTree.ps1 | PASS. |
| git diff --check | PASS. |

Relevant targeted suites were also run after each behavioral phase before committing. An early recovery test exposed timestamp granularity in its simulated restart fixture; the fixture was corrected and the final full suite passes. test_intelligence.py prints scenarios during discovery and is not counted as an independent assertion suite.

The three skips are PolicyTests.test_unsafe_file_directory_ownership_and_symlink and both RemoteAdminPtyTests terminal-input cases. They require POSIX ownership/permissions or terminal behavior unavailable on Windows.

## Deliberate boundaries and remaining validation

- Remote Admin administrative APIs remain deny-by-default. DISABLED retains the existing trusted-local ordinary-control model; it is not a remote-access security boundary. ENABLED requires configured authentication; CONFIG_ERROR locks controls. Validate the real HTTPS/proxy/cookie boundary separately.
- Recovery policy was preserved. Uncertain Asterisk observations do not authorize recovery. Tests mock CLI, service, permission, timeout and active-link observations; they do not establish real system behavior.
- Run the Debian namespace/chroot clean-install fixture, POSIX tests, unit startup/boot checks, ownership/sudoers verification, rerun/customization checks and full restore rehearsal on a disposable ASL3 system before release.
- Run the source-specific SkywarnPlus upstream fixture against the selected upstream source, which was not available locally. Validate optional observer freshness with synthetic or isolated data. BlueNode must never execute SkywarnPlus.
- Verify actual App_Rpt command/result formats and active-link non-interruption on an isolated test node. Validate network/registration failure boundaries there without disrupting an operating node.
- RX transport tests do not establish actual audio quality. No browser TX/PTT was implemented or enabled. Future stuck-PTT/max-duration implementation needs independent safety design and hardware testing.
- No Net Map/Net Mode, Radio Activity frontend, credential changes, production configuration changes, or guessed operator values were added.
- Upgrade/rollback is documented with complete backups. Installer-wide automatic rollback and unspecified schema migrations remain deliberately unimplemented.
- Copied installations without Git show the semantic snapshot version and an unavailable commit, rather than an invented revision. Retention limits mean older history can age out, as documented.
- Recommend completing the isolated Linux gates, then reviewing the alpha change set before deciding whether to push, tag, or publish a release.

## Local commits before final validation commit

The commit containing this report is the final validation commit; its hash is available in Git history. Earlier commits, in order:

```text
67ca90b Center dashboard status cards
791943e Polish dashboard touch targets and emergency guidance
76e0175 Harden dashboard text rendering and remote authentication
6d6e048 Verify conflicting Asterisk evidence and stabilize recovery fixture
6a03e7b Propagate connectivity dependencies and clarify failure boundaries
14acf8b Enforce read-only SkywarnPlus integration
b554a44 Clarify emergency recovery boundaries and audit maintenance actions
2ed370b Verify node control outcomes from fresh App_Rpt state
6f381d3 Document radio origin limits and label adjacent-peer telemetry
6fd0853 Harden RX tickets and reject malformed or transmit WebSocket input
4b440fb Improve clean-install prerequisites and configuration errors
7168e31 Document configuration-preserving upgrade and complete rollback
cc26356 Refresh public setup documentation and dashboard screenshot
6d7281b Expose alpha snapshot version and organize unreleased changes
dc2fde7 Bound runtime retention and harden state and log handling
```

## Complete changed-file manifest

Relative to e2529f3, including this final validation batch (56 files):

```text
CHANGELOG.md
README.md
bluenode-dashboard.jpeg
config/nodesmart.example.json
core/allstar_status.py
core/asterisk_observation.py
core/automation.py
core/connection_stats.py
core/connectivity.py
core/emergency_mode.py
core/event_logger.py
core/health.py
core/intelligence.py
core/node_controls.py
core/radio_activity.py
core/remote_admin.py
core/runtime_io.py
core/soft_radio.py
core/test_admin_policy.py
core/test_asterisk_observation.py
core/test_automation.py
core/test_connectivity.py
core/test_control_auth.js
core/test_control_routing.js
core/test_dashboard.js
core/test_dashboard_render.js
core/test_emergency_mode.py
core/test_fresh_install.py
core/test_node_controls.py
core/test_radio_activity.py
core/test_remote_admin.py
core/test_runtime_io.py
core/test_soft_radio.py
core/test_weather_alerts.py
core/test_web_admin.py
core/version.py
core/web_server.py
docs/AUTH_SESSION_VALIDATION.md
docs/CONFIGURATION.md
docs/CONTROL-ROUTING-VALIDATION.md
docs/DEPLOYMENT.md
docs/FRESH_INSTALL_VALIDATION.md
docs/INSTALL.md
docs/REMOTE_ADMIN.md
docs/SOFT_RADIO_RX.md
docs/TESTING.md
docs/TX_ORIGIN.md
docs/UPGRADE.md
docs/WEATHER_ALERTS.md
docs/WORK_QUEUE_VALIDATION.md
install/helpers/skywarnoff
install/helpers/skywarnon
install/install.sh
install/nodesmart.sudoers.example
install/validate-config.py
web/index.html
```
