# Installation

NodeSmart v0.1.0-alpha targets AllStarLink v3 systems using Python 3 and systemd.

## Install

Clone the repository, enter it, and run:

```bash
sudo ./install/install.sh
```

Run the installer with `sudo` from the Linux account that should run NodeSmart. If needed:

```bash
sudo NODESMART_USER=youruser ./install/install.sh
```

On a first run, the installer creates `/opt/nodesmart/config/nodesmart.json` and stops so you can edit it. Set your node number, callsign, friendly nodes, and thresholds, then rerun the installer.

## Verify

```bash
systemctl is-enabled nodesmart
systemctl is-active nodesmart
systemctl status nodesmart --no-pager
```

Then open:

```text
http://NODE_IP:8080/web/
```

## Installer actions

The installer installs NodeSmart under `/opt/nodesmart`, preserves an existing live config, creates runtime directories, installs helper commands, validates and installs `/etc/sudoers.d/nodesmart`, installs the systemd unit, enables the service, and starts NodeSmart after configuration exists.

SkywarnPlus is optional. If `/usr/local/bin/SkywarnPlus/SkyControl.py` is missing, installation continues with a warning.

For troubleshooting:

```bash
journalctl -u nodesmart -n 100 --no-pager
```
