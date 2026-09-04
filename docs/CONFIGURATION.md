# Configuration

The live configuration is `/opt/nodesmart/config/nodesmart.json`. A Git-safe example is provided as `config/nodesmart.example.json`.

- `node`: local AllStar node number
- `callsign`: station callsign
- `friendly_nodes`: node-number to friendly-name mappings
- `web.host` / `web.port`: dashboard listener
- `health`: CPU, memory, and disk warning/critical thresholds
- `recovery.asterisk_enabled`: enables automatic Asterisk recovery
- `recovery.asterisk_cooldown_seconds`: minimum cooldown between recovery attempts
- `recovery.display_reset_hours`: hours successful or cancelled recovery results remain prominently displayed before returning to READY. Failed results clear from the current display when Asterisk is observed online; recovery records and restart limits remain preserved

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

The shipped systemd service runs monitor.py, which owns health collection,
AllStar monitoring, Intelligence updates, and automatic recovery. Do not schedule
health.py or recovery.py separately when this service is active.
