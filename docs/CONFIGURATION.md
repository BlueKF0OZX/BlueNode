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
- `node_behavior.evaluation_interval_seconds`: cached passive analysis interval (default `10`)
- `node_behavior.event_window_seconds`: rolling window for link/control activity (default `300`)
- `node_behavior.link_settle_seconds`: time allowed for an accepted connect command to produce a matching connection (default `20`)
- `node_behavior.reconnect_notice_count` / `reconnect_warning_count`: same-node attempt thresholds (default `5` / `8`)
- `node_behavior.churn_notice_count` / `churn_warning_count`: connection-transition thresholds (default `6` / `10`)
- `node_behavior.failed_link_notice_count` / `failed_link_warning_count`: unconfirmed establishment thresholds (default `4` / `6`)
- `node_behavior.local_key_notice_seconds` / `local_key_warning_seconds`: continuous authoritative local-COR thresholds (default `90` / `180`)
- `node_behavior.rapid_key_notice_transitions` / `rapid_key_warning_transitions`: local key/unkey thresholds in the configured rapid-key window (default `10` / `16`)
- `node_behavior.control_notice_count` / `control_warning_count`: BlueNode control activity thresholds (default `12` / `20`)
- `node_behavior.automation_notice_count` / `automation_warning_count`: recovery-attempt thresholds in the automation window (default `2` / `3`)
- `node_metadata.source_url`: structured AllStarLink public Node Directory source
- `node_metadata.success_ttl_seconds`: successful directory cache lifetime (default `86400`)
- `node_metadata.negative_ttl_seconds`: shorter cache lifetime for missing nodes (default `3600`)
- `node_metadata.refresh_retry_seconds`: minimum retry delay after a directory refresh attempt (default `300`)
- `node_metadata.timeout_seconds`: HTTPS directory request timeout (default `5`)
- `node_metadata.maximum_download_bytes`: defensive response-size limit (default `8000000`)
- `connectivity.interval_seconds`: layered diagnostic interval (default `30`, minimum `10`)
- `connectivity.timeout_seconds`: timeout for each lightweight probe (default `1.5`)
- `connectivity.failure_threshold` / `recovery_threshold`: consecutive observations required to confirm failure or recovery (default `2`)
- `connectivity.stale_seconds`: maximum cached diagnostic age (default `120`)
- `connectivity.allstar_service_host` / `allstar_service_port`: official AllStar endpoint used for the service-layer TCP probe (default `register.allstarlink.org:443`)

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

The published `tx_origin` object distinguishes verified local RF, a verified
immediate linked-node ingress, ambiguous simultaneous sources, and unknown
internal transmitter activity. For linked audio, App_Rpt identifies the keyed
connection that delivered audio to this node; it does not identify whether that
peer originated or relayed the transmission. BlueNode therefore reports
`confidence: verified_ingress`, `path_scope: immediate_peer`, and
`ultimate_source_known: false` instead of claiming an unsupported distant RF
station or individual operator identity.

Current activity is written atomically to `state/radio_activity.json`. Start/end
events are emitted only for local receiver and remote linked-audio transitions,
not for every poll. Stale, missing, or malformed telemetry fails safely as
unavailable.

Remote activity metadata comes from AllStarLink's official structured Node
Directory at `https://allmondb.allstarlink.org/allmondb.php`. BlueNode chose it
over the live statistics API because it is the directory source intended for
node number, callsign, description, and registered location data, and avoids
scraping the searchable HTML node list. The complete directory is refreshed in
one background request, normally once per day; missing nodes are cached for one
hour and failed refresh attempts are bounded to at most once every five minutes.
The two-second App_Rpt telemetry path never waits for this request.

The displayed location is the node owner's public registered directory text,
not a speaker or handheld position. The source currently provides no structured
coordinates or reliably separable city/region/country fields, so BlueNode does
not infer them. `callsign`, `display_location`, `latitude`, and `longitude` are
optional activity-state fields, allowing a future NetMap consumer without
assigning fabricated map coordinates.

## Smart connectivity diagnostics

A separate cached monitor checks the active IPv4 default-route interface, its
gateway, DNS resolution, a direct-IP external TCP endpoint, the official
AllStar registration service endpoint, App_Rpt registration, Asterisk, the IAX
module, and App_Rpt's explicit link connection states. These checks default to
every 30 seconds and never run in the two-second health or browser polling
paths. Two consecutive failures are required before escalation, and two
successful observations verify recovery.

Each layer is `ok`, `fail`, `unknown`, or `blocked_by_upstream`. A downstream
layer is never called failed merely because an earlier dependency prevented a
meaningful probe. Remote-link diagnosis is limited to App_Rpt explicitly
reporting a requested link as non-established; BlueNode does not invent the
remote cause and does not treat an ordinary disconnected node as a failure.

The resulting `state/connectivity.json` is published atomically. BlueNode keeps
the established `internet` field for compatibility while exposing the diagnosed
failure domain in `connectivity`. DNS and AllStar-only failures leave general
Internet status online but create a sustained warning; interface, gateway, and
external-path failures become offline after confirmation. Asterisk recovery is
never requested for a connectivity-only failure.

The shipped systemd service runs monitor.py, which owns health collection,
AllStar monitoring, Intelligence updates, and automatic recovery. Do not schedule
health.py or recovery.py separately when this service is active.
