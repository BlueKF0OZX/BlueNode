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

The monitor samples connections and rebuilds Intelligence every 2 seconds plus
processing time. The dashboard polls status every 2 seconds, with overlapping
status requests suppressed; events and recovery display refresh every 5 seconds.
Skywarn and system health still depend on the health collector's cadence.

The shipped systemd service runs monitor.py only. It does not schedule health.py
or recovery.py. Existing installations may schedule these externally; inspect
that scheduling before enabling additional collectors or automatic recovery.
