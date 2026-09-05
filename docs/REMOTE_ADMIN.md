# BlueNode Remote Admin

Remote Admin is an optional application-level administrative boundary. It is
disabled by default and does not create a listener or public route. Use it only
through an existing trusted HTTPS path; the authenticated Apache/Tailscale
gateway can remain as an independent outer authentication layer.

## Security model

- Credentials and generated secret material live only in
  `/etc/bluenode/remote-admin.json`; the file must not be committed.
- Passwords use PBKDF2-HMAC-SHA256 with a unique salt and 600,000 iterations.
- Random server-side sessions expire after 30 days by default for newly initialized
  configurations. Existing explicit `session_seconds` values are preserved. The browser
  receives an `HttpOnly`, `Secure`, `SameSite=Strict` cookie; its CSRF token
  stays in page memory. Logout invalidates the session, and a web service
  restart invalidates every outstanding session. The cookie's `Max-Age` and
  server expiration use the same configured duration; activity does not extend it.
  A successful login rotates the session and CSRF token and invalidates this
  browser's preceding session. Credential, permission, duration, and cookie-policy
  changes invalidate sessions when checked. Disabling Remote Admin clears sessions
  when observed by the server. Sessions are held in server memory, so browser
  restarts can retain authorization but web-service restarts cannot.
- Failed logins are rate-limited. Existing gateway abuse protection remains an
  independent outer limit for remote traffic.
- The server accepts only fixed action identifiers and fixed service/log
  sources. It never accepts commands, unit names, Asterisk CLI text, or paths.
- Enabling Remote Admin also requires its session and CSRF token for existing
  dashboard control POSTs. Read-only health/state endpoints remain unchanged.
- `/opt/nodesmart/logs/admin-audit.jsonl` records timestamp, action, and outcome
  only—never credentials, tokens, request bodies, or command output.

Implemented actions are status/version inspection, constrained recent logs,
connectivity refresh, restart and verification of `nodesmart.service`, and an
explicitly confirmed Asterisk restart with reachability verification. A
`nodesmart-web.service` self-restart is intentionally not exposed because the
process cannot truthfully verify its own restart. Arbitrary shell, arbitrary
systemd/Asterisk operations, file access, package management, reboot/shutdown,
networking, firewall, and public-access configuration are prohibited.

## Enable safely

First confirm BlueNode is reached over trusted HTTPS and the outer gateway
protects every route. Then substitute the actual service account:

```sh
sudo NODESMART_USER=SERVICE_USER bash /opt/nodesmart/install/remote-admin.sh enable
```

The initializer prompts without echo, requires at least 14 characters, writes
atomically, and grants only root and the service account group read access. It
does not accept a password on the command line. Asterisk restart requires the
displayed confirmation phrase and may interrupt active links.

Check or disable the feature:

```sh
sudo NODESMART_USER=SERVICE_USER bash /opt/nodesmart/install/remote-admin.sh status
sudo NODESMART_USER=SERVICE_USER bash /opt/nodesmart/install/remote-admin.sh disable
```

The lifecycle helper validates and installs one exact monitor-service restart
rule when enabled, and removes that optional rule when disabled. It does not
grant arbitrary `systemctl` access. Disabling changes neither Apache, Tailscale,
firewall, nor LAN access. If HTTPS
is unavailable, leave Remote Admin disabled; do not weaken secure cookies to
administer over plain HTTP.

Soft Radio RX uses a separate permission and remains unavailable to an
ordinary Remote Admin session until explicitly granted. See
`docs/SOFT_RADIO_RX.md`. Permission changes invalidate active sessions.

## Persistent controls and pending actions

For an existing installation, `session_seconds` in the root-managed
`/etc/bluenode/remote-admin.json` can be set to `2592000` after installing the
updated session backend. This is a 30-day absolute maximum, not a sliding expiry.
Keep `secure_cookie: true` and use the existing HTTPS access path. Explicit shorter
lifetimes remain supported (minimum 300 seconds). Legacy configurations with
insecure cookies are capped at 24 hours; the UI does not change this setting.
Changing the lifetime revokes old sessions, so sign in again once. Use Sign out
on shared devices; do not choose a long duration on a browser others can access.
No password, session token, or pending control is stored in localStorage or
sessionStorage. The session cookie is HttpOnly; the CSRF token stays in page memory.

The Controls section displays locked/unlocked status and Sign in / Sign out.
A control rejected with HTTP 401 is retained in memory while the existing sign-in
panel is focused. Successful login must be followed by a verified session and CSRF
token before the original control resumes once. Emergency confirmation still
happens before queuing. Only the enumerated ordinary controls and validated numeric
node parameters can be queued. Administrative service actions are not queued.

Failed login, Cancel pending control, sign-out, leaving the page, or reload
clears the pending action. One ordinary control can be outstanding at a time;
another click cannot replace it. HTTP 403, network errors, and other ambiguous
failures are displayed without automatic replay. If the retry fails, inspect its
result before deliberately trying again. Viewing and monitoring require no login.

Browser coverage: `node core/test_control_auth.js` and
`node core/test_control_routing.js` (Playwright; optional `BLUENODE_BROWSER_PATH`).
All test control requests are intercepted and never reach a production node.
