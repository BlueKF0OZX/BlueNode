# Radio activity observation limits

The backend observes local receiver COR, local transmitter key state, and the keyed state of directly adjacent App_Rpt peers. It does not identify the ultimate transmitting operator or a remote node behind a hub.

- Local RF means this node's receiver is keyed. It does not identify the person transmitting.
- Remote-link activity identifies an immediate peer only. Registered callsign/location metadata describes that peer, not the current speaker or their location.
- Simultaneous local and linked audio, or multiple keyed links, remains ambiguous.
- Missing or stale telemetry produces an unavailable result, not a claim of silence.

No audio is recorded for identification and no corrective radio commands are issued by this observer. Radio Activity presentation remains removed from the dashboard. Node Behavior uses passive observations only. Any future origin display requires authoritative evidence beyond adjacent-peer telemetry.
