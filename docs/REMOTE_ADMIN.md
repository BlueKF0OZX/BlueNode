# BlueNode Remote Admin

Remote Admin is an optional application-level administrative boundary. It is
disabled by default and does not create a listener or public route. Use it only
through an existing trusted HTTPS path; the authenticated Apache/Tailscale
gateway can remain as an independent outer authentication layer.

## Security model

- Credentials and generated secret material live only in
  `/etc/bluenode/remote-admin.json`; the file must not be committed.
- Passwords use PBKDF2-HMAC-SHA256 with a unique salt and 600,000 iterations.
- Random server-side sessions expire after 30 minutes by default. The browser
  receives an `HttpOnly`, `Secure`, `SameSite=Strict` cookie; its CSRF token
  stays in page memory. Logout invalidates the session, and a web service
  restart invalidates every outstanding session.
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
