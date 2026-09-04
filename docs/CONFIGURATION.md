# Configuration

The live configuration is `/opt/nodesmart/config/nodesmart.json`. A Git-safe example is provided as `config/nodesmart.example.json`.

- `node`: local AllStar node number
- `callsign`: station callsign
- `friendly_nodes`: node-number to friendly-name mappings
- `web.host` / `web.port`: dashboard listener
- `health`: CPU, memory, and disk warning/critical thresholds
- `recovery.asterisk_enabled`: enables automatic Asterisk recovery
- `recovery.display_reset_hours`: hours successful or cancelled recovery results remain prominently displayed before returning to READY. Failed results clear from the current display when Asterisk is observed online; recovery records and restart limits remain preserved
- `recovery.verification_timeout_seconds`: maximum time to wait for fresh post-restart health and Intelligence state
- `recovery.verification_stable_checks`: consecutive healthy checks required before recovery is verified
- `recovery.verification_interval_seconds`: delay between post-recovery stability checks
- `automation.attempt_window_seconds`: rolling window used to detect repeated recovery attempts
- `automation.max_attempts`: attempts permitted within the rolling window before backoff
- `automation.minimum_cooldown_seconds`: minimum delay after an attempt; failed verification progressively increases it
- `automation.maximum_backoff_seconds`: upper bound for escalation backoff
- `automation.healthy_reset_seconds`: sustained healthy period required to clear escalation and attempt history
- `radio_activity.stale_seconds`: maximum telemetry age before live radio activity clears as unavailable (default `6`, minimum `4`)
- `connectivity.interval_seconds`: layered diagnostic interval (default `30`, minimum `10`)
- `connectivity.timeout_seconds`: timeout for each lightweight probe (default `1.5`)
- `connectivity.failure_threshold` / `recovery_threshold`: consecutive observations required to confirm failure or recovery (default `2`)
- `connectivity.stale_seconds`: maximum cached diagnostic age (default `120`)

The DODROPIN helper looks for a friendly node whose name is `DODROPIN` (case-insensitive).

The live config is intentionally ignored by Git. Back it up before upgrades or major changes.

## Lifecycle and refresh

Current Intelligence severity follows health and unresolved incidents. Historical
failure counts remain visible but do not by themselves keep a recovered node in
warning or critical state. Missing closing events can be reconciled from a newer
normal health observation, explicitly marked with an unknown exact recovery time.
Raw event and connection history is preserved.

The monitor runs independent AllStar and system-health loops every 2 seconds.
Each fresh health observation is saved before Intelligence is rebuilt, and
automatic Asterisk recovery runs in a single non-overlapping background worker.
Slow or failed work in one loop does not stop the other loop. The dashboard polls
status every 2 seconds, with overlapping status requests suppressed; events and
recovery display refresh every 5 seconds.

## Automated Operations

BlueNode persists automation state atomically in
`/opt/nodesmart/state/automation.json`. Maintenance Mode suspends automatic
recovery while health monitoring, state publication, Intelligence, and event
history continue. Disabling Maintenance Mode resumes automatic actions.

Recovery completion requires Asterisk CLI reachability, a newer healthy system
observation, a newer Intelligence file, valid AllStar state when available, and
consecutive stable checks. Failed verification is recorded as a recovery failure
and increases bounded cooldown/backoff. Repeated attempts enter an operator-
attention state instead of creating an endless restart loop. A sustained healthy
period resets escalation and backoff without deleting incident or event history.

Maintenance transitions, recovery starts, verification results, escalation,
backoff entry, and reset are logged only on transitions—not every monitoring
cycle.

## Live radio activity

The independent two-second AllStar monitor reads App_Rpt's `RPT_RXKEYED`,
`RPT_TXKEYED`, and keyed-state suffixes in `RPT_ALINKS`. This distinguishes
local receiver/COR activity, physical transmitter/PTT state, and inbound audio
from a directly connected link without treating a connection as a transmission.
Friendly names come only from `friendly_nodes`; otherwise BlueNode displays the
node number. Multiple keyed links are shown as ambiguous rather than assigning
an unsupported speaker identity.

Current activity is written atomically to `state/radio_activity.json`. Start/end
events are emitted only for local receiver and remote linked-audio transitions,
not for every poll. Stale, missing, or malformed telemetry fails safely as
unavailable.

## Smart connectivity diagnostics

A separate cached monitor checks the active IPv4 default-route interface, its
gateway, DNS resolution, a direct-IP external TCP endpoint, and App_Rpt HTTP
registration status. These checks default to every 30 seconds and never run in
the two-second health or browser polling paths. Two consecutive failures are
required before escalation, and two successful observations verify recovery.

The resulting `state/connectivity.json` is published atomically. BlueNode keeps
the established `internet` field for compatibility while exposing the diagnosed
failure domain in `connectivity`. DNS and AllStar-only failures leave general
Internet status online but create a sustained warning; interface, gateway, and
external-path failures become offline after confirmation. Asterisk recovery is
never requested for a connectivity-only failure.

The shipped systemd service runs monitor.py, which owns health collection,
AllStar monitoring, Intelligence updates, and automatic recovery. Do not schedule
health.py or recovery.py separately when this service is active.
