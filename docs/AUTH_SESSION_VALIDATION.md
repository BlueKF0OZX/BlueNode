# Authenticated control validation

Remote Admin has DISABLED, ENABLED, and CONFIG_ERROR policy states. DISABLED is trusted-local mode for ordinary node/dashboard controls; administrative APIs still require an enabled, authenticated session. CONFIG_ERROR locks controls rather than falling back to local mode. The configured-intent marker prevents missing credentials from silently selecting DISABLED.

Python tests cover secure/HttpOnly/SameSite cookies, CSRF, rate limits including simultaneous attempts, expiration, logout, browser-session rotation, permission changes, credential changes, restart revocation, strict action allowlists, request-log privacy, and policy errors. See [Remote Admin](REMOTE_ADMIN.md) and [Testing](TESTING.md).

Browser tests cover Enter-to-login, one-time pending-action resumption, target labels, duplicate-submit prevention, cancellation, failed login, expiry, reload, and unavailable session verification. Browser requests are intercepted; the separate HTTP tests exercise backend enforcement. SkywarnPlus controls are read-only and unavailable for execution.

POSIX security-file ownership/mode enforcement and pseudo-terminal credential entry require Linux validation. Browser persistence never overrides server-side expiration or revocation.
