# Changelog

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
