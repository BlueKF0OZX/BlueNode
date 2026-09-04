# BlueNode Emergency Mode

Emergency Mode is an explicit operator-selected dashboard state for severe
weather, Skywarn, emergency communications, and other high-attention
operations. It does not change Asterisk, AllStar links, automatic recovery,
networking, or radio behavior.

The normal dashboard remains the default. Entering Emergency Mode requires a
deliberate confirmation and persists the state atomically in
`/opt/nodesmart/state/emergency_mode.json`. The file contains only mode,
timestamps, elapsed-time inputs, and the generic activation source; it contains
no credentials or machine identity. A missing, malformed, or unsafe state file
fails closed to Normal Mode.

When active, BlueNode displays a persistent banner and elapsed operation timer.
It moves current health, Asterisk/connectivity status, Connected Nodes,
SkywarnPlus, Intelligence, and prioritized operational events ahead of routine
statistics and controls. Incidents, recovery status, sessions, and all normal
dashboard data remain available. Exiting restores the familiar normal order.

When Remote Admin is enabled, both enter and exit requests require its valid,
unexpired session and CSRF token. When Remote Admin is disabled, the controls
use the same trusted-local-dashboard boundary as existing BlueNode controls.
The authenticated HTTPS remote-access gateway continues to protect the whole
application externally.

Activation and deactivation create one transition event and one concise admin
audit record. Refresh polling does not create events. Emergency Mode is never
entered automatically because of an alert or health failure.
