# NodeSmart

NodeSmart is an open-source monitoring, control, intelligence, and automatic-recovery dashboard for AllStarLink v3 nodes.

**Status:** v0.1.0-alpha — early public testing release.
## Dashboard

![NodeSmart Dashboard](nodesmart-dashboard.png)
## Features

- Live AllStar, Asterisk, Internet, CPU, memory, disk, and uptime monitoring
- HEALTHY / DEGRADED / FAULT health states
- Connection/session tracking with friendly node names
- Manual connect/disconnect controls
- Optional DODROPIN and SkywarnPlus controls
- Event logging and incident correlation
- NodeSmart Intelligence summaries and recommendations
- Automatic Asterisk recovery with verification, cooldown, and lockout protection
- Desktop/mobile web dashboard
- systemd startup and installer support
- Python standard library only

## Requirements

AllStarLink v3, Python 3, Asterisk with `rpt`, systemd, sudo, and a Linux service user. SkywarnPlus is optional.

## Install

```bash
sudo ./install/install.sh
```

On a first install, edit:

```text
/opt/nodesmart/config/nodesmart.json
```

Then rerun the installer.

The dashboard defaults to:

```text
http://NODE_IP:8080/web/
```

See `docs/INSTALL.md` and `docs/CONFIGURATION.md`.

## Security

NodeSmart installs a project-specific sudoers file rather than requiring blanket passwordless root access. The alpha privilege model may be tightened further in future releases.

The dashboard does not provide Internet-facing authentication. Keep it on a trusted network unless you place it behind appropriate authentication and network security.

## Optional integrations

Skywarn controls require an existing SkywarnPlus installation at `/usr/local/bin/SkywarnPlus/`.

The DODROPIN helper searches `friendly_nodes` for an entry named `DODROPIN`.

## Project layout

```text
config/   Example configuration
core/     Monitoring, health, intelligence, recovery, web backend
docs/     Installation and configuration documentation
install/  Installer, helpers, sudoers template
systemd/  Service template
web/      Dashboard
```

Runtime directories (`events/`, `history/`, `logs/`, `state/`) and the live `config/nodesmart.json` are ignored by Git.

## Alpha notice

This is an alpha release. Test it on a node you can access directly before relying on automatic recovery or remote controls.

## License

MIT. See `LICENSE`.
