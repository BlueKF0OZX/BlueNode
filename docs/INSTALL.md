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



## Dashboard Network Access



NodeSmart listens on the TCP port configured by `web.port` in `config/nodesmart.json` (default: `8080`).



During installation, if an active `firewalld` installation is detected, the installer automatically allows the configured NodeSmart dashboard port through the firewall zone associated with the system's default network interface.



After installation, the dashboard can normally be reached from another device on the same local network at:



    http://NODE_IP:8080/web/



Replace `NODE_IP` with the IP address of the AllStarLink node and `8080` if a different `web.port` has been configured.



If `firewalld` is not available or active, the installer will display a warning and the firewall may need to be configured manually.



### Security



NodeSmart does not configure router port forwarding and does not intentionally expose the dashboard to the public Internet.



Because the NodeSmart dashboard includes node control functions, directly forwarding the dashboard port from the Internet is not recommended. Remote access should be provided through a secure method such as a VPN or authenticated reverse proxy.
