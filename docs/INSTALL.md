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
sudo apt-get install git python3 sudo iproute2 iputils-ping curl nano
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

BlueNode does not discover or configure your local node automatically. Use the
node number from your existing ASL3 setup. If unsure, inspect the node stanza
headers in `/etc/asterisk/rpt.conf` read-only and confirm the intended local
node in your ASL3 administration interface; do not use a linked remote node's
number. On systems hosting multiple nodes, select the one BlueNode will monitor.
Do not edit Asterisk configuration to match a BlueNode example.

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

## After installation

1. Check `systemctl is-active nodesmart nodesmart-web`. Both should be active.
2. Confirm `systemctl is-active asterisk` and compare its PID/start time with
   your pre-install baseline. The read-only broker check in Troubleshooting
   verifies BlueNode can query Asterisk; do not use radio/control actions as a test.
3. Confirm the dashboard's node number and callsign match the local node you
   configured. BlueNode does not automatically select among multiple local nodes.
4. Allow the first observations to arrive. Monitoring normally repeats every
   two seconds after startup checks; Connectivity normally refreshes every
   30 seconds. These are polling intervals, not guaranteed readiness deadlines.
   Waiting/unavailable values are not zero activity. Connection statistics
   describe activity recorded by BlueNode, not events before installation.
5. Overall Status summarizes current observations. Read its explanation and
   Intelligence's recommendation when attention is indicated. Smart Connectivity
   identifies the affected network layer; Node Behavior describes findings in
   available evidence, not a certification of long-term node behavior.
6. Monitoring is active independently of automatic recovery. Automatic Asterisk
   recovery is disabled by default; leave it disabled during initial validation.
7. SkywarnPlus is optional. If wanted, follow [Weather Alerts](WEATHER_ALERTS.md)
   after installing/configuring SkywarnPlus separately. No weather update is not
   an all-clear; wait for its normal collection schedule without forcing a run.
8. Remote Admin and HTTPS are optional, separate setup steps. Follow
   [Remote access](REMOTE_ACCESS.md) and [Remote Admin](REMOTE_ADMIN.md); use
   trusted HTTPS, initialize your own credentials, and verify unauthenticated
   protected requests are rejected. Do not publicly expose the default listener.
9. Soft Radio is parked. Net Mode/NetMap are deferred; neither is an incomplete
   setup step you need to perform.

If observations remain unavailable, use Troubleshooting below rather than
restarting Asterisk or changing radio settings.

### After reboot

Enabled BlueNode services should start automatically. Configuration and recorded
history persist; cached telemetry needs fresh observations. Remote Admin's
in-memory sessions are cleared by a web-service restart, so sign in again through
the configured HTTPS path. Optional weather may be unavailable until the next
normal collection, especially when its temporary output was cleared at boot.
Verify both BlueNode services, Asterisk, the configured node and observation
freshness. These are code-derived expectations: real reboot behavior still
requires validation on a disposable ASL3 host. Do not reboot an operating radio
node solely to test onboarding.

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
  Weather awareness additionally requires the optional guarded
  [snapshot observer](WEATHER_ALERTS.md), installed from the public checkout.
  Missing, failed or partial snapshots show unavailable; old successful data
  shows stale. Only a successful current empty snapshot means no active alerts.
  Normal BlueNode installation neither installs nor updates this observer.
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
Before and after installation, compare `systemctl show asterisk -p MainPID
-p ExecMainStartTimestamp` and confirm `systemctl is-active asterisk`; neither
check changes node operation. Enabled BlueNode units start on subsequent boots,
but real boot behavior must be checked on a disposable host, not by rebooting
an operating radio node for validation.
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

## Asterisk observations and safe automatic recovery

BlueNode separates three observations: the systemd Asterisk service/process,
CLI query access through the restricted broker, and configured App_Rpt node
telemetry. A running service with failed CLI access appears as **RUNNING / LIMITED**,
with an explanation that BlueNode cannot query it. This needs investigation,
but is not proof that Asterisk stopped. Missing or ambiguous systemd evidence
appears as **UNKNOWN** and prohibits automatic restart. Invalid App_Rpt telemetry
is reported separately; command exit success alone is insufficient.

Automatic recovery remains disabled by default. When explicitly enabled, it
requires fresh evidence (at most 30 seconds old) that the loaded Asterisk unit
is inactive/dead or failed/failed with MainPID zero. BlueNode checks independently
at worker entry, after the confirmation delay, and immediately before acting.
A running PID, transitional state, failed probe or restored CLI response cancels
recovery. Existing maintenance, cooldown, attempt limits and backoff still apply.
After a restart, success requires independently running service evidence, valid
CLI and App_Rpt telemetry, and fresh health/Intelligence observations.

For query-access problems, verify the BlueNode service account's broker/sudo
permissions and access to the Asterisk control socket. These read-only checks
help separate process health from access problems (replace the example account):

```sh
systemctl show asterisk -p ActiveState -p SubState -p MainPID -p LoadState
sudo -u bluenode sudo -n /usr/local/sbin/bluenode-asterisk -rx 'core show version'
```

Do not broaden sudo permissions or restart a working Asterisk service to work
around query-access failures. Query access and configured-node observation have
separate warning/resolution events; restoring access is not described as a
process restart. Historical outage records from older versions are retained.
A syntactically valid configuration pointing to another real local node cannot
reveal the operator's intent: verify the configured node after installation.
The final probe and systemctl action are separate OS operations; they are not
an atomic service-manager transaction. Automatic recovery assumes the supported
systemd-managed ASL3 service, rather than independently launched Asterisk processes.

App_Rpt validation accepts the explicitly empty zero-link `RPT_ALINKS` emitted
by upstream [rpt_update_links](https://github.com/AllStarLink/app_rpt/blob/master/apps/app_rpt/rpt_link.c).
It still requires valid RX/TX fields and a present, structurally valid link field;
an absent field or a successful command containing an error is not valid telemetry.
