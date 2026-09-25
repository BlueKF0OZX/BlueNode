# Meet your BlueNode dashboard

Start here after installation, or return whenever a label is unfamiliar. Some optional sections depend on your configuration. A customized dashboard may have extra controls.

## Your first visit

1. Check the callsign and local node number at the top. This is the station you control.
2. Look at Overall Status and Last Health Check. Give a new installation a few seconds to collect its first readings.
3. To connect somewhere, enter the remote node number in the main box beside Connect and Disconnect, then click Connect.
4. To save that number, enter an optional Favorite name and click Save node as favorite. You do not need to connect first.
5. Read the result message after using a control. A request being sent does not necessarily mean the connection succeeded.

## Saved nodes, Favorites, and Recent Nodes

**These are different lists. Saving a favorite does not add it to a preset dropdown.**

- **Saved nodes dropdown:** preset shortcuts, if your dashboard has them. Selecting one fills the main node-number box; it does not connect automatically. Presets are supplied by that dashboard's configuration/customization.
- **Favorites:** numbers you save yourself using Save node as favorite. Find them in the Favorites section above Manual Node Connection. Use their Connect button next time; Remove removes the shortcut, not the radio connection.
- **Recent Nodes:** shortcuts from verified connections and observed connection history. They are not a list of nodes currently connected. Connect adds a link; Disconnect leaves that particular link.
- **Favorite name:** an optional label to help you recognize a saved number. Saving the same number again updates its label.

Favorites are stored in this browser, separately for each local node. Another browser, device, or dashboard address can have a different list. Clearing browser data can remove them. If storage is blocked, the dashboard explains that changes last only for that page.

**Which number gets saved?** The main number beside Connect and Disconnect. The number beside Switch nodes is the node you want to leave; it is not the number saved as a favorite.

## Station and health cards

- **Callsign / local node:** identifies the station being monitored, not a remote station you want to contact.
- **Overall Status:** the combined health assessment. Healthy means checks are passing; Degraded means something needs attention; Fault means a detected problem. Read the explanation below it for the reason.
- **Asterisk:** the radio/link software running on your node. Its detail text explains what BlueNode could verify.
- **Internet:** the connectivity assessment. Open the diagnostic link for more detail; one failing Internet check does not prove every network service is down.
- **SkywarnPlus:** the optional weather-alert integration. Not configured or not detected does not mean your radio is broken.
- **Connected Nodes:** links currently observed by BlueNode. A connected node can be quiet. Receiving/idle and activity timing describe recent observations; an incoming peer is not necessarily the original person transmitting.
- **Last Health Check:** when BlueNode last checked the station. Old or unavailable readings should not be treated as a current all-clear.
- **CPU Temperature:** the computer's temperature, when supported by its hardware.
- **System Uptime:** how long the node computer has been running since boot.
- **Memory Usage / Disk Usage:** how much RAM and storage the computer is using. These describe the node, not the computer displaying your browser.

## Connection controls

- **Connect:** adds a link to the number in the main node box. Other links stay connected.
- **Disconnect:** leaves the number in the main node box. It does not mean disconnect everything.
- **Switch nodes:** leaves the number in the Node to leave box, then connects to the number in the main box above. Other links stay connected. Read the result if either step fails.
- **DODROPIN controls:** shortcuts for that configured destination, where available.
- **Search AllStar Nodes:** looks up a node, callsign, or location in the directory. A listing does not guarantee the node is online or accepting connections.
- **Close Results:** hides the directory results; it does not disconnect a node.

When Remote Admin is required, a control may ask you to sign in first. Review the pending action before continuing. Saving a favorite is a browser preference, not a radio command.

## Connection statistics and history

- **Connections Today / Connected Time Today:** today's connection activity recorded by BlueNode, not a count of spoken contacts or your personal transmitting time.
- **Active Connections:** the current observed link count.
- **Current Session:** information about ongoing observed connection activity.
- **Last Session:** the most recent recorded session information.
- **Recent Sessions:** previously observed links, with timing and duration. Longest Session Today, Completed Today, and Completed Time Today summarize retained completed sessions.
- **Recent Events:** recorded changes and actions. Filters help separate radio, connection, and system events.
- **Observed activity history:** past received/transmitted activity observations. These are sampled intervals, not recordings or exact audio durations. Expand raw records when investigating an event.
- **Activity notifications:** optional browser notifications for prolonged activity. They depend on browser permission and the page remaining open.

History starts when BlueNode observes your node. A new installation can have an empty history, and missing observations limit what the statistics can show.

## Weather and connection diagnostics

- **Current Weather Alerts / View alerts:** expands available alert details and their freshness. Weather setup is optional.
- **Smart Connectivity:** expands checks for the local network, gateway, DNS, Internet, and AllStar connectivity to help identify where a problem is occurring.
- **Troubleshooting report:** previews and downloads a privacy-filtered support report. Review it before sharing it on GitHub. It does not repair or restart the radio.

## Monitoring, recovery, and emergency mode

- **Monitoring / Automation:** explains whether automatic recovery is enabled, blocked, or waiting. Monitoring can continue while recovery is off.
- **Automatic recovery:** if configured and allowed, BlueNode can attempt recovery after qualifying failures. Fresh guided installations leave it off.
- **Maintenance Mode:** suppresses automatic recovery while you work on the station. It does not stop monitoring or disconnect your links.
- **Repeated-failure protection / Cooldown:** limits repeated recovery attempts. Check the explanation rather than assuming a delayed attempt is a malfunction.
- **Recovery attempts today / Last automation check:** show recent recovery activity and when the automation policy was evaluated.
- **Emergency Mode:** makes important operational information more prominent. It does not call emergency services, transmit an emergency message, or change recovery/radio operation by itself.
- **Node Behavior / Network Courtesy:** observations that may deserve an operator's attention. They do not identify an unknown speaker or automatically prove misuse.

## Remote Admin and browser audio

- **Remote Admin sign-in:** unlocks the actions allowed for that account when this optional feature is configured. Use the dashboard administrator's credentials, not your AllStar website login.
- **Refresh status / Refresh diagnostics:** requests updated information.
- **Restart monitor service:** restarts BlueNode's monitoring service.
- **BlueNode logs / Asterisk logs:** displays diagnostic messages for the selected service.
- **Restart Asterisk:** restarts the radio/link software and can interrupt active links. This is different from restarting the monitor.
- **Log out:** ends the browser's administrative session; it does not disconnect radio links.
- **Soft Radio Listen / Stop / Volume:** optional receive audio in your browser. Stop stops that browser audio, not the AllStar connection. The standard public panel is receive-only; customized dashboards may provide other radio controls.

## BlueNode Intelligence

**BlueNode Intelligence** summarizes detected conditions and suggests what to investigate. **Recent Incidents** shows recent recorded problems. Read the observations behind a recommendation; the text is not a guarantee that every part of the radio system has been checked.

## Coming back later

Open your usual dashboard address. With Windows Setup's private connection, reopen the app, sign in, click Open dashboard, and keep the app open. That temporary address can change between visits, which can also affect browser-stored favorites.

Use **Dashboard guide** at the top of the dashboard to return here. Optional features can wait until the basic station and connection controls make sense.
