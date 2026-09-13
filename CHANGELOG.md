# Changelog

## [Unreleased] - 0.1.2-alpha.0

### Changed

- Opening the dashboard directly from a local file now explains how to reach the live node, without polling unavailable endpoints or showing misleading emergency status.

- Added a previewable troubleshooting report under Smart Connectivity, with allowlisted health/resource/check data and no logs, identities, addresses, or configuration.
- Improved keyboard focus visibility for dashboard buttons and added a responsive report preview/download area.

- Centered dashboard cards and improved mobile touch targets, diagnostic explanations, and Emergency Mode guidance.
- Node controls verify resulting App_Rpt state, including already-satisfied and unverified outcomes.
- SkywarnPlus is strictly read-only; former On/Off controls no longer execute SkywarnPlus.
- Clarified local-receiver and adjacent-peer limits; Radio Activity stays absent from the dashboard.
- Improved installation prerequisites, configuration errors, and upgrade/rollback guidance.

### Security

- Escaped observation/history text in dashboard HTML.
- Hardened concurrent login throttling, CSRF input handling, and request-log privacy.
- Revoked unused RX tickets on logout/stop and rejected malformed WebSocket and browser TX input.

### Reliability

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
