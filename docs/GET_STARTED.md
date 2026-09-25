# Get BlueNode running

BlueNode adds a browser dashboard to an **existing working AllStarLink 3 node**.
The guided installer supports **Debian 12 ASL3**. It is an early-testing alpha.
You do not need to edit a configuration file or create a service account.

**Using Windows? [Download the setup app and follow these steps](WINDOWS_SETUP.md).**
It handles the node connection, installation, and private dashboard access for
you. The terminal instructions below are an alternative for Linux/Mac users or
operators who already use SSH.

## 1. Connect to your node

Use the same SSH terminal and login you use to manage ASL3. Run the command on
the node itself, not in Windows PowerShell or your Mac's local terminal.
If you have a blank Raspberry Pi, install ASL3 and get your radio working first:
[AllStarLink installation guide](https://allstarlink.github.io/install/).

## 2. Start guided setup

Copy this entire line into the node's terminal:

```bash
curl -fsSL https://raw.githubusercontent.com/BlueKF0OZX/BlueNode/v0.1.4-alpha.1/install/bootstrap.sh | sudo bash
```

This downloads and runs the installer from the named alpha release. You can
[read it first](../install/bootstrap.sh). If curl is missing, run
`sudo apt-get update && sudo apt-get install curl ca-certificates` first.

Confirm the download, then answer the questions:

1. **Node number:** confirm the detected local node. With multiple local nodes,
   choose the one to monitor.
2. **Callsign:** confirm or enter your callsign.
3. **Dashboard address:** choose a listed home-network address to open BlueNode
   from a phone/computer on that trusted network. Type `YES` to confirm that
   access. Keep `127.0.0.1` for SSH-tunnel access only.
4. **Port:** press Enter for `8080`, unless it is already in use.
5. Review the summary and type `YES` to install.

Home-network access is not password protected by default. Devices on that
network can control your node. Do not use this option on guest/public Wi-Fi or
forward its port to the Internet. [Authenticated HTTPS access](REMOTE_ACCESS.md)
is a separate optional setup; it is not needed to try BlueNode through SSH.

The installer checks the dashboard and station identity and prints the exact
link to open. Bookmark that link. BlueNode starts after reboot.
For SSH-only access it prints a tunnel command; replace the login and node-IP
placeholders with the same values used for SSH.

## 3. Use the dashboard

**[Meet your dashboard: every section explained](DASHBOARD_GUIDE.md)**

After installation, the welcome page links to the same guide. You can also use
**Dashboard guide** at the top of the dashboard whenever you need a reminder.

Confirm your callsign/node at the top. Give the first observations time to arrive.
Use Connect to add a node and Disconnect to leave it. Favorites and Recent Nodes
save typing. Connection history starts when BlueNode starts observing your node.

Weather and Internet remote access are optional. Automatic recovery stays off.
Your radio settings are preserved, and setup does not restart Asterisk.

## Already installed?

Running setup again checks the existing dashboard and prints its link. It does
not overwrite your settings. A partial/manual installation or conflicting helper
is left alone, with directions to the manual guide.

For an update to this release, use:

```bash
curl -fsSL https://raw.githubusercontent.com/BlueKF0OZX/BlueNode/v0.1.4-alpha.1/install/bootstrap.sh | sudo bash -s -- --update
```

Read the confirmation: an update replaces BlueNode code, including custom edits.
Both BlueNode services must be enabled and healthy, and automatic recovery must
be off. Settings/history are backed up privately under `/var/backups/bluenode/`.
The dashboard pauses while updating; Asterisk continues running. Failed
installation/startup checks restore the previous BlueNode installation.
Unsupported legacy/custom layouts use the [full upgrade guide](UPGRADE.md).
Backups remain on disk; review them before deleting any. Package dependencies
installed by the downloader are not removed by rollback.

To restore a completed update's backup, run the following on the node, replacing
the last argument with the exact backup path printed during that update:

```bash
sudo python3 /opt/nodesmart/install/quickstart.py --restore /var/backups/bluenode/before-update-YOUR_BACKUP
```

Restoration asks for confirmation and restores settings/history as of that backup.
It also saves the current files privately before restoring, so later history is
not silently lost. If BlueNode files are missing, download the matching release
and run its `install/quickstart.py --restore ...` from that checkout instead.

## If something goes wrong

| Message | What to do |
| --- | --- |
| ASL3/App_Rpt is not running | Finish or repair ASL3 setup first. |
| No running local nodes | Check your local node in ASL3; do not enter a remote node. |
| Address/port unavailable | Confirm the address or rerun using another port, such as 8082. |
| Existing installation/helper | Your files were preserved. Use the manual install/upgrade guide. |
| Startup check failed | Read the printed log path. Fresh failed installs are removed; failed updates restore the backup. |
| Link works on the node but not on your phone | Check that both are on the trusted LAN and you chose that LAN address, not 127.0.0.1. Check the node firewall; setup does not change it. |

If the dashboard opens, use **Troubleshooting Report** to preview and download
a privacy-filtered report. Review it before sharing it in a
[GitHub issue](https://github.com/BlueKF0OZX/BlueNode/issues/new).
Never post passwords, private backup directories, or unreviewed setup logs.

Advanced configuration: [Installation](INSTALL.md), [Configuration](CONFIGURATION.md),
[Upgrade and recovery](UPGRADE.md).
