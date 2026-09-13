# Trying BlueNode

BlueNode is an early alpha for AllStarLink 3. Start with a node you can access
directly and keep automatic recovery disabled during your first evaluation.
The current development snapshot is still undergoing release validation. Read
[validation status](VALIDATION_STATUS.md) for what has and has not been checked.

## Before installation

- Record your Debian version, hardware model, ASL3 version, and Asterisk version.
- Keep a backup of your existing node configuration and a way to sign in locally.
- Follow [Installation](INSTALL.md), including the first configuration-only run.
- Record the exact checkout with `git rev-parse HEAD` before installation. The
  development branch can change between tests; include that commit in feedback.
- For an existing BlueNode installation, read [Upgrade and rollback](UPGRADE.md)
  before changing it.

## First session

1. Open the dashboard through the running BlueNode service, following the access
   instructions in the installation guide. Opening the HTML file directly on
   your computer will show guidance instead of live readings.
2. Confirm the last health check keeps advancing and that Asterisk, Internet,
   memory, disk, and connection observations match what you can independently
   verify. Missing optional weather data is expected without its integration.
3. Open Smart Connectivity and inspect its checks. Preview and download a
   troubleshooting report; confirm the saved file opens and contains no private
   information you do not want to share.
4. If you have a consenting test peer, connect and disconnect once. Compare
   BlueNode's result with the actual link state. Do not use an unrelated public
   node for repeated tests.
5. Try your normal desktop and phone browsers. Note clipped text, controls that
   are hard to use, and any values that stop updating.
6. Leave ordinary monitoring running and note unexpected restarts, connection
   changes, errors, or steadily increasing resource use. There is no need to
   deliberately stop Asterisk or interrupt your network for a first-user test.

## Reporting a problem

Use the project's [bug report template](https://github.com/BlueKF0OZX/BlueNode/issues/new?template=bug_report.md).
Include the steps, what you expected,
what happened, the BlueNode version or commit you installed, OS/hardware,
and whether optional integrations are configured. Attach the troubleshooting
report after reviewing it.

Do not post passwords, tokens, SSH keys, full configuration files, private
addresses, or unreviewed logs. Dashboard screenshots may show your callsign,
node number, connected peers, and browser details; crop or redact as needed.

## Scope of early feedback

The first-user path covers installation, ordinary monitoring, diagnostics,
manual peer controls, and the dashboard. Remote HTTPS access needs its separate
setup and validation. Soft Radio is parked, and browser transmit/PTT, Net Mode,
and Net Map are outside this alpha's supported testing path. Hardware-specific
behavior still needs operator feedback; virtual-machine results do not prove
radio, thermal, or SD-card performance.
