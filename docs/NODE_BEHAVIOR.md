# Node Behavior and Network Courtesy

BlueNode passively evaluates existing local telemetry. Version 1 never
disconnects a link, inhibits RF, restarts a service, blocks a control, or
changes automatic recovery policy.

The persisted runtime state is `/opt/nodesmart/state/node_behavior.json` and is
published in `system.json` as `node_behavior`. Writes are atomic. Evaluation is
cached (10 seconds by default), reads only a bounded tail of the event log, and
does not add network or Asterisk probes.

## Assessments

- `NORMAL`: no unusual supported pattern is present.
- `NOTICE`: a conservative lower threshold was crossed; operator attention is
  not automatically required.
- `WARNING`: repeated or sustained evidence crossed the warning threshold and
  operator review is recommended.

Stale or unavailable local-RF telemetry is marked explicitly. BlueNode does
not make a confident RF-behavior finding from stale data.

## Evidence and limitations

Local RF uses App_Rpt's authoritative `RPT_RXKEYED` state and only
`RADIO.LOCAL_RX.START/END` transitions. Linked audio is not counted as local
RF. Connection churn uses observed connection transitions. A failed
establishment means BlueNode accepted a connect control request but did not
observe the matching node connect within the configured settle time. It does
not identify or speculate about the remote cause.

Repeated control and recovery observations contain action types, timestamps,
node numbers where already present in operational history, and counts. They do
not contain credentials, session tokens, CSRF values, client addresses, or
request bodies.

Only assessment/finding transitions emit `BEHAVIOR.NORMAL`,
`BEHAVIOR.NOTICE`, or `BEHAVIOR.WARNING`; every monitoring cycle does not add
an event. Warning findings inform Intelligence without becoming recovery
actions or automatically creating incidents. Active notices and warnings are
visually promoted by the existing Emergency Mode layout.
