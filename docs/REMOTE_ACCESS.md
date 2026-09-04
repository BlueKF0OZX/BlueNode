# Optional BlueNode Remote Access

BlueNode remains local-only by default. Nothing in the normal installer enables
remote access. Remote access requires an operator to choose a hostname,
authentication credentials, TLS method, and network mode explicitly.

## Security model

- Remote traffic terminates as HTTPS at an authenticated reverse proxy or an
  identity-aware tunnel. Authentication covers `/` and every API/control path.
- The upstream is always loopback HTTP. Never publish or forward TCP 8080.
- Local dashboard access continues unchanged. The framework does not modify
  BlueNode, Asterisk, its ports, firewalld, router settings, or DNS.
- Password files, private keys, tunnel tokens, and the live configuration stay
  outside Git. Use root ownership and mode `0600`.
- Direct mode refuses activation without `mod_evasive`, providing baseline
  request-abuse protection in addition to Apache request timeouts and limits.
  Monitor logs and add host-level banning appropriate to the installation.

## Direct HTTPS mode (public IPv4 or global IPv6)

Prerequisites are Apache 2.4, the SSL/proxy/headers/basic-auth/request-timeout
modules, `mod_evasive`, a trusted certificate, and a bcrypt Apache password file.
Acquire the certificate before activation, using an ACME client or another
trusted certificate-management method suitable for the operator's DNS setup.

1. Create a dedicated DNS hostname. Use an A record for public IPv4, an AAAA
   record for stable global IPv6, or both.
2. Reserve the node's LAN address. For IPv4, forward TCP 443 only to the node.
   For IPv6, permit inbound TCP 443 only in the router's IPv6 firewall. Do not
   forward or permit 8080, Asterisk, Allmon, Cockpit, or SSH for this feature.
3. Install/enable the required Apache modules and obtain the TLS certificate.
4. Create credentials outside the repository, for example with Apache's
   `htpasswd -B` option. Use a unique password.
5. Copy `install/remote-access.conf.example` to
   `/etc/bluenode/remote-access.conf`, replace every placeholder, then set
   ownership `root:root` and mode `0600`.
6. Validate without changing Apache:

   ```bash
   sudo bash /opt/nodesmart/install/remote-access.sh validate
   sudo bash /opt/nodesmart/install/remote-access.sh render
   ```

7. After reviewing the rendered hostname, paths, authentication block, and
   loopback upstream, explicitly activate it:

   ```bash
   sudo bash /opt/nodesmart/install/remote-access.sh enable
   ```

The enable operation backs up any same-named site, installs a hostname-specific
HTTPS vhost, runs `apache2ctl configtest`, reloads Apache, and verifies Apache is
active. A failure restores the previous site and reloads the previous validated
configuration. Existing default sites and aliases are not disabled or replaced.
Common globally configured Apache application paths such as `/allmon3` and
`/server-status` are explicitly denied on the BlueNode hostname so another
local application is not accidentally published through this vhost.

Disable remote access while preserving the local dashboard:

```bash
sudo bash /opt/nodesmart/install/remote-access.sh disable
```

Disable also validates Apache before accepting the change and restores the
enabled state if validation or reload fails. Certificate issuance/renewal must
be tested separately; this framework deliberately does not own private keys.

## Tunnel mode (CGNAT or no inbound ports)

Choose an outbound HTTPS tunnel provider that supports identity-aware access.
Configure a dedicated hostname to route to `http://127.0.0.1:8080`, require
authentication (preferably MFA) before every path, and ensure no bypass hostname
or unauthenticated API route exists. Store its token only in the provider's
root-readable service configuration, never in this repository.

Set `BLUENODE_REMOTE_MODE=tunnel`, keep the loopback backend, and set
`BLUENODE_TUNNEL_AUTHENTICATION_ACK=required`. The local validator checks those
provider-neutral invariants. Provider installation, enable, disable, credential
rotation, and rollback remain explicit operator actions because their commands
and trust models differ. Disabling/stopping the provider connector removes the
remote path without changing BlueNode's local service.

## Validation after an authorized activation

From a non-LAN connection, verify HTTPS certificate trust, authentication
failure/success, dashboard loading, and a harmless API read. Confirm unauthenticated
requests to both `/` and `/api/...` receive `401` or the identity provider's login
response. Confirm the router has no 8080 rule, the node still serves the local
dashboard, and Asterisk listeners/firewall rules are unchanged.
