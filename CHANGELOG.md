# Changelog

## [0.1.6-alpha.1] - 2026-09-26

- Store favorites and their names on the node so phone and PC dashboards share the same list.
- Import existing browser favorites explicitly, preserving names already saved on the node.
- Reject conflicting edits from stale browsers, preserve data on storage errors, and protect shared favorites with the existing Remote Admin sign-in policy.
- Show the favorites sign-in action for protected gateways that return an authentication-required HTTP 403 response.
- Add contributor/security guidance, private vulnerability reporting, and a pull-request checklist.

## [0.1.5-alpha.1] - 2026-09-25

- Bundle the latest dashboard in Windows and terminal installations.
- Invite installation and dashboard issue reports from the installer and welcome page.
- Add Edit name and Disconnect to personal favorites; disconnecting keeps the favorite saved.
- Add a remembered Auto-switch toggle to manual Connect, with clear ON/OFF feedback and a choice of peer when several are linked.
- Replace the separate Switch nodes form and update the dashboard guide.
- Open the dashboard guide in a separate tab.

## [0.1.4-alpha.1] - 2026-09-25

- Added a plain-language guide explaining dashboard cards, controls, statistics, optional features, and the separate preset/Favorites/Recent Nodes lists.
- Linked the guide from the dashboard, first-visit welcome page, and GitHub getting-started instructions.
- Bundled the local guide in the Windows installer. The page is read-only and needs no external scripts or network access to read.

## [0.1.3-alpha.1] - 2026-09-25

- Added a portable Windows x64 setup assistant for existing Debian 12 ASL3 nodes.
- Detects the local station, confirms installation, and opens a private dashboard connection automatically.
- Installs from a bundled release; passwords stay in memory and SSH identities are pinned.
- Setup jobs continue on the node if the computer disconnects; reconnect to check the result.
- Existing installations are verified/opened without replacing settings or code.
- Added Windows setup instructions, integration checks, and a downloadable self-contained app.

## [0.1.2-alpha.1] - 2026-09-25

- Added a release-pinned download command and guided setup for existing Debian 12 ASL3 nodes.
- Detects running local nodes, confirms station identity/network access, creates the service account, checks startup, and prints the dashboard link.
- Leaves existing installations untouched by default; explicit guided updates back up settings/history and restore the prior installation on failure.
- Added a beginner getting-started guide and troubleshooting steps.
- Recent nodes now include Disconnect beside Connect, with inline results.

## [Unreleased] - 0.1.2-alpha.0

### Changed

- Added verified switching between explicit source/destination nodes, preserving unrelated links and reporting the failed phase when verification stops.
- Added compact mobile controls, retained activity summaries, optional prolonged-activity browser notifications, and measured dashboard request timing.
- Added browser-local favorites and recent nodes, scoped per local node, with quick-connect through the existing authenticated control flow. Recent nodes come from verified controls and recorded sessions, not activity estimates.
- Added connection/radio/system event filters, paired radio records with recorded intervals, and expandable original records that remain open across refreshes.
- Added receiving/idle status, an observed activity timer, last activity, and a five-minute activity warning inside the Connected Nodes card. Activity expires independently when telemetry becomes stale.
- Opening the dashboard directly from a local file now explains how to reach the live node, without polling unavailable endpoints or showing misleading emergency status.

- Added a previewable troubleshooting report under Smart Connectivity, with allowlisted health/resource/check data and no logs, identities, addresses, or configuration.
- Improved keyboard focus visibility for dashboard buttons and added a responsive report preview/download area.

- Centered dashboard cards and improved mobile touch targets, diagnostic explanations, and Emergency Mode guidance.
- Node controls verify resulting App_Rpt state, including already-satisfied and unverified outcomes.
- SkywarnPlus is strictly read-only; former On/Off controls no longer execute SkywarnPlus.
- Clarified local-receiver and adjacent-peer limits; activity is integrated into Connected Nodes rather than a separate dashboard panel.
- Improved installation prerequisites, configuration errors, and upgrade/rollback guidance.

### Security

- Escaped observation/history text in dashboard HTML.
- Hardened concurrent login throttling, CSRF input handling, and request-log privacy.
- Revoked unused RX tickets on logout/stop and rejected malformed WebSocket and browser TX input.

### Reliability

- Recognize outbound CONNECTING transports before App_Rpt adds them to link variables; preserve pending status and suppress duplicate connect commands during peer outages.

- Mark lost radio observations and collector gaps as interruptions, rather than ordinary transmission ends; do not pair event records across interruptions or restart markers.
- Reset observed transmission timers after collector gaps or clock reversals, and preserve the last observed activity across idle samples.
- Wait for an existing pending connection instead of sending a duplicate connect command.
- Preserve bounded, structured link-control failure snapshots and distinguish pending links, lost observation, command rejection, and verification deadlines.
- Reconcile App_Rpt link variables with transport status so reconnecting peers are not reported as established connections.
- Reject stale or invalid health timestamps in the dashboard instead of retaining a reassuring old snapshot.
- Extend observation and installer fixtures for transport status; make session-expiration tests wait for actual admission before revocation.

- Bounded event/audit/session-history retention and dashboard event responses.
- Atomic connection-state publication and safe handling of corrupt history and future-dated radio observations.
- Bounded authentication/ticket memory and redacted authorized journal output.

### Validation required before release

- See [validation status](docs/VALIDATION_STATUS.md) for completed Debian/ASL3 installation, reboot, rollback, private-peer, security, and regression checks and their exact scope.
- Sustained resource/endurance testing is incomplete; the short collection is not a 24-hour pass.
- Hardware-specific behavior, optional weather source compatibility, and external HTTPS/proxy behavior remain to be verified.
- Soft Radio remains parked; no browser TX/PTT functionality is included.


## [0.1.1-alpha] - 2026-08-29

Alpha maintenance and security update.

### Changed

- Improved live AllStar connection-status responsiveness

- Reduced AllStar monitor polling interval from five seconds to two seconds

- Dashboard now reads live AllStar connection state directly instead of waiting for the health cycle

- Added no-cache headers for dashboard pages to prevent stale browser code

### Security

- Hardened dashboard static-file access

- Blocked URL-encoded path traversal attempts

## [0.1.0-alpha] - 2026-08-29

Initial public alpha.

### Added

- Live AllStar and system-health monitoring
- Connection/session tracking and friendly node names
- Manual node connect/disconnect controls
- Optional DODROPIN and SkywarnPlus controls
- Event logging and incident correlation
- NodeSmart Intelligence summaries and recommendations
- Automatic Asterisk recovery with verification, cooldown, and lockout protection
- Recovery status UI
- Desktop/mobile dashboard
- systemd startup support
- Git-safe example configuration
- Installer with NodeSmart-specific sudo permissions
- Five-second health and recovery-dashboard refresh
