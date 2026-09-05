# Authenticated control UX validation

Validated on September 5, 2026. Application implementation is ready for review;
production deployment is held by operator instruction.

- Linux: 135 Python tests passed, zero skips, inside the existing isolated
  mount/network/PID clean-install fixture. Its two lifecycle tests passed:
  clean installation/repetition/first monitoring cycle and dashboard-only
  deployment/rollback. The fixture checks systemd, sudoers, permissions,
  compilation, shell syntax, missing state and installation safety.
- Windows: 135 Python tests ran successfully with two platform skips
  (POSIX pseudo-terminal and bash-dependent transaction coverage).
- All six JavaScript/browser suites passed. Browser control requests were
  intercepted; no production operational action was invoked. Coverage includes
  nine representative controls, exactly-once resumption, cancellation, login
  failure, expiration, logout, reload, actual persistent HttpOnly browser cookies,
  CSRF rejection, malformed actions and unavailable session verification.
- HTTP security tests verify all ten ordinary action routes reject missing
  authentication and missing CSRF, protected admin routes reject unauthenticated
  requests, cookie lifetime/attributes, rotation and expired-session rejection.
- Session tests cover the 30-day limit, logout, server restart, and invalidation
  after credential, permission, secret and duration changes.

Existing explicit session durations are preserved. New configurations default to
30 days with Secure cookies. Server authorization remains in memory and does not
survive a web-service restart; browser persistence does not override expiration
or revocation. See `REMOTE_ADMIN.md` for configuration and operator behavior.

## Deployment hold

Production remains on backend `bf91361` with the previously deployed dashboard
overlay. Main also contains the undeployed fresh-install changes: the constrained
`bluenode-asterisk` command broker, changed command invocations and sudoers rules,
helper updates, configuration validation, ownership/directory modes, and service
unit changes. The production broker was absent at the read-only compatibility
check. The normal deployment refuses to proceed without the broker and matching
sudoers; dashboard-only deployment cannot install this session backend.

No production migration or partial backport is authorized in this validation.
The next safe step is operator review of a coordinated installer/privilege and
application migration. The established application deployment restarts
`nodesmart.service` and `nodesmart-web.service`; it must not restart Asterisk.
Review helper/configuration compatibility and capture backups of application
code, operator configuration, affected helpers, sudoers and service units before
any migration. Application-only rollback is insufficient for privilege changes:
the rollback plan must restore the matching helper/sudoers/unit set, preserve
runtime data, and validate BlueNode health with Asterisk identity unchanged.

Risks to review are mismatched helper privileges, service account permissions,
brief BlueNode monitoring/dashboard interruption, and invalidation of all web
sessions. No App_Rpt/radio or network/firewall changes are part of this proposal.
