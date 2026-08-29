# Configuration

The live configuration is `/opt/nodesmart/config/nodesmart.json`. A Git-safe example is provided as `config/nodesmart.example.json`.

- `node`: local AllStar node number
- `callsign`: station callsign
- `friendly_nodes`: node-number to friendly-name mappings
- `web.host` / `web.port`: dashboard listener
- `health`: CPU, memory, and disk warning/critical thresholds
- `recovery.asterisk_enabled`: enables automatic Asterisk recovery
- `recovery.asterisk_cooldown_seconds`: minimum cooldown between recovery attempts

The DODROPIN helper looks for a friendly node whose name is `DODROPIN` (case-insensitive).

The live config is intentionally ignored by Git. Back it up before upgrades or major changes.
