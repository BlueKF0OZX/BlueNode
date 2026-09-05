# Installation

BlueNode targets an existing, working AllStarLink 3 node on Debian 12 with
Python 3.11 or newer, Asterisk/App_Rpt, and systemd. It does not install or
configure AllStarLink. Python uses only the standard library; the dashboard's
JavaScript and CSS are shipped in Git, with no npm, pip, CDN, or build step.
SkywarnPlus, Apache, Tailscale, and Remote Admin are optional.

## Get the public repository

Run these commands in your regular operator account, outside `/opt/nodesmart`:

```bash
sudo apt-get update
sudo apt-get install git python3 sudo iproute2 iputils-ping
git clone https://github.com/BlueKF0OZX/BlueNode.git
cd BlueNode
```

Debian supplies the remaining shell/core utilities and `getent` through its
base installation. Asterisk must be available at `/usr/sbin/asterisk` and
`systemctl` at `/usr/bin/systemctl`. The installer checks dependencies before
creating files; it does not run package upgrades itself.

Use a dedicated, unprivileged service account, with no login shell and no
membership in `sudo`, `audio`, or radio-device groups:

```bash
sudo useradd --system --user-group --home-dir /opt/nodesmart --no-create-home --shell /usr/sbin/nologin bluenode
sudo NODESMART_USER=bluenode bash ./install/install.sh
```

Create the account only once. `NODESMART_USER` must name an existing non-root
account. For an existing installation, retain the user shown by
`systemctl show nodesmart.service -p User --value`; do not silently switch users.
Without `NODESMART_USER`, the installer uses the account invoking sudo.

## Configure before starting

The first invocation creates only `/opt/nodesmart/config/nodesmart.json` and
stops successfully. It does not install sudo rules or units, or start services.

```bash
sudo nano /opt/nodesmart/config/nodesmart.json
```

Set `node` to your own AllStar node number and `callsign` to your station
callsign. The placeholder identity is rejected on the next run. Leave
`friendly_nodes` as `{}` unless you want optional labels. See
[Configuration](CONFIGURATION.md) for the remaining settings.

New installations default to `web.host: "127.0.0.1"`, port `8080`, and
`recovery.asterisk_enabled: false`. Automatic Asterisk restart is opt-in;
keep it disabled while validating your installation. Remote Admin and Soft
Radio are disabled without their separate configuration.

For access from another computer on your **trusted LAN**, deliberately set
`web.host` to the node's LAN IPv4 address. The dashboard includes radio control
actions and has no authentication by default. Do not bind it to an untrusted
interface or forward its port to the Internet. `0.0.0.0` listens on every IPv4
interface. This server uses IPv4; use an IPv4 address in `web.host`.

Finish installation from the same checkout:

```bash
sudo NODESMART_USER=bluenode bash ./install/install.sh
systemctl is-enabled nodesmart nodesmart-web
systemctl is-active nodesmart nodesmart-web
curl -f http://127.0.0.1:8080/web/
```

Use the configured listener address instead of `127.0.0.1` in that last command
if you selected a LAN address. Open `http://NODE_IP:8080/web/` from your trusted
LAN, replacing `NODE_IP` with that address. For a loopback-only installation,
you can use an SSH local forward from your computer:

```bash
ssh -N -L 8080:127.0.0.1:8080 youruser@NODE_IP
```

Then open `http://127.0.0.1:8080/web/` on that computer. BlueNode does not change
host firewall rules, router settings, or public exposure. Any LAN firewall
policy is an operator decision, outside the installer.

## What installation changes

After configuration validation, installation copies application files into
`/opt/nodesmart`, creates `state`, `events`, `history`, and `logs`, installs the
two units in `/etc/systemd/system`, reloads systemd, and enables/restarts only
`nodesmart` and `nodesmart-web`. These services run as the specified account.
Code and installer helpers are root-owned; runtime directories belong to the
service account with mode `0750`. Live config is root-owned, service-group
readable, mode `0640`; units use umask `0027`.

The installer installs `/etc/sudoers.d/nodesmart` with mode `0440` after
`visudo` validation. `/usr/local/sbin/bluenode-asterisk` allows only the status
queries and numeric connect/disconnect commands BlueNode uses. The rule also
allows the exact Asterisk restart command for opt-in recovery and deliberate
Remote Admin actions. It grants no arbitrary Asterisk CLI or shell access.
Four root-owned optional helpers are installed in `/usr/local/bin`:
`dodropin`, `dodropoff`, `skywarnon`, and `skywarnoff`.

Installation never writes Asterisk/App_Rpt or radio configuration, restarts
Asterisk, originates channels, sends DTMF, or keys PTT. Clicking connection or
Skywarn controls later is a deliberate operational action and can affect radio
operation. Monitoring alone does not invoke those controls.

## First startup and optional integrations

Historical state and logs need not exist. The dashboard shows unavailable
monitoring/Intelligence and no event history until the monitor publishes data.
Connectivity needs several observations; Node Behavior may report LIMITED or
UNAVAILABLE while evidence is incomplete. Emergency Mode defaults to normal.
Missing optional data does not prevent service startup.

- SkywarnPlus is detected at `/usr/local/bin/SkywarnPlus/config.yaml`, with
  controls through `SkyControl.py` in that directory. Install and configure it
  separately; otherwise Skywarn is unknown and its dashboard buttons disabled.
- DODROPIN is optional: add your chosen node number with the label `DODROPIN`
  in `friendly_nodes`. No destination is shipped or inferred.
- [Remote Admin](REMOTE_ADMIN.md) requires separate credential initialization
  and trusted HTTPS. Use the same `NODESMART_USER=bluenode` when invoking its
  lifecycle helper. There are no default credentials. Journal access may need
  membership in `systemd-journal` if you deliberately enable log viewing.
- [Remote access](REMOTE_ACCESS.md) is a separate opt-in authenticated HTTPS
  setup. Apache and Tailscale are not core installation requirements.
- Soft Radio is parked/disabled pending a verified read-only audio tap. Do
  not activate it as part of installation validation. Net Mode/NetMap are deferred.

## Updating and recovering

Keep the public checkout separate from `/opt/nodesmart`. Back up the live
configuration and runtime data to a private location, then from that checkout:

```bash
git pull --ff-only origin main
sudo NODESMART_USER=bluenode bash ./install/install.sh
```

Existing config and runtime history are preserved. Repeated installation is
supported; it refreshes code, privileges, units, and BlueNode services. It does
not reset your listener address or recovery choice. Invalid configuration or
missing required source files fail before deployment. A service-start failure
returns nonzero and preserves config/history; there is no automatic installer
rollback. Diagnose the journal, fix the cause, and rerun, or reinstall a known
good checkout with your backed-up config. Do not reset or delete radio settings.

For older Git-in-`/opt/nodesmart` developer deployments, see
[Deployment](DEPLOYMENT.md). A code-only update is insufficient when installer
helpers or system rules change.

## Troubleshooting and stopping

```bash
systemctl status nodesmart nodesmart-web --no-pager
sudo journalctl -u nodesmart -u nodesmart-web -n 100 --no-pager
sudo /usr/sbin/visudo -c
sudo -u bluenode sudo -n /usr/local/sbin/bluenode-asterisk -rx 'core show version'
```

The last command is a read-only CLI check. Permission failures usually mean
the installer was not rerun with the intended service account. A blank/failed
dashboard should be checked at its configured address, followed by both unit
journals. Do not create dummy healthy state files to hide startup errors.
After config changes, restart only BlueNode:

```bash
sudo systemctl restart nodesmart nodesmart-web
```

There is no automated uninstaller. To stop BlueNode without affecting Asterisk
or deleting history:

```bash
sudo systemctl disable --now nodesmart nodesmart-web
```

Disable any separately enabled remote-access integration before manual removal.
Retain your private backup; review the installed paths above before removing
units, sudo rules, helpers, or application data. Never remove AllStar files.

## Repeatable validation

On Debian, the public fixture can be run from the checkout with:

```bash
sudo python3 deploy/test_clean_install.py
```

It needs util-linux namespace/mount/chroot tools, the packages above, and
`systemd-analyze`/`visudo`. It copies OS tools into a temporary filesystem,
creates private mount/network/PID namespaces, and substitutes Asterisk and
systemctl. It cannot access the real Asterisk socket or radio devices. It
validates an absent `/opt/nodesmart`, onboarding, permissions, repeat execution,
first monitor cycle, unit and sudoers syntax, failure reporting, and the full
Python suite. This is an isolated integration fixture, not physical ASL3 or
systemd PID 1 boot certification. See [validation evidence](FRESH_INSTALL_VALIDATION.md).
