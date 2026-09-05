# Current SkywarnPlus Weather Alerts

BlueNode consumes the alerts SkywarnPlus already computes. There is no additional
weather API, independent filtering engine, weather command, or browser-triggered
collection. SkywarnPlus enable/disable controls and their authentication remain
unchanged.

## Why an optional observer is necessary

The inspected SkywarnPlus `data.json` contains `last_alerts`, grouped by event
name, with county codes, severity, description and end time. It is saved for
event/county changes, not every successful collection. Description/end-time-only
changes can be missed. Fetch failures reuse cached data without a structured
freshness flag. File mtime, the existing log, Supermon text and an empty cache
cannot establish a successful current all-clear.

The observer wraps the single `get_alerts(COUNTY_CODES)` call in `main`. One
notification is inserted after a county's response has been fully processed,
inside its existing try block. An optional import is inserted before
`get_alerts`. Nothing in alert retrieval, blocking, sorting, limiting, fallback,
announcements or radio operation is replaced. The returned object is unchanged;
upstream exceptions propagate. Export failures cannot change the returned alerts.
No upstream source copy is maintained in this repository.

## Explicit installation and update audit

The ordinary BlueNode installer does **not** patch SkywarnPlus automatically.
From the public BlueNode checkout, first run:

```sh
python3 install/skywarn-snapshot.py --skywarn-root /usr/local/bin/SkywarnPlus
python3 deploy/test_skywarn_upstream.py /usr/local/bin/SkywarnPlus/SkywarnPlus.py
```

The first command checks compatibility without writing anything. The second
executes only the extracted collection function with synthetic responses and a
temporary cache; it never imports/runs the upstream module or its main function.
It verifies unchanged requests/alerts for complete, partial and failed fetches.

After backup and operator approval for production installation:

```sh
sudo python3 install/skywarn-snapshot.py --skywarn-root /usr/local/bin/SkywarnPlus --install
```

This installs `bluenode_skywarn_snapshot.py` beside `SkywarnPlus.py` and applies
the three small source edits atomically per file, installing the module first.
The original script is retained as `SkywarnPlus.py.bluenode-before-<digest>`.
The installer never runs SkywarnPlus, changes its configuration or cron schedule,
restarts a service, or calls Asterisk. The existing next scheduled collection
produces the snapshot. Exporter module absence/import failure leaves upstream
collection available; BlueNode eventually reports stale/unavailable telemetry.

Compatibility is guarded by AST fingerprints of **both** inspected functions
and unique anchors. Repeat application validates the reversible patch. An
unreviewed upstream change or a damaged patch is refused before writing.
After a SkywarnPlus update, rerun the checks. If refused, review the new source,
update the supported fingerprints only after auditing the integration, and run
the isolated comparison again. Do not bypass the fingerprint check. To remove
the integration, restore the matching backed-up source after reviewing any later
upstream changes; do not blindly restore an older version over a newer update.

## Snapshot contract and freshness

The exporter writes `<SkywarnPlus DEV.TmpDir>/bluenode-weather.json` (normally
`/tmp/SkywarnPlus/bluenode-weather.json`). Schema version 1 contains:

- `source: "SkywarnPlus"`, `schema_version: 1`;
- UTC epoch seconds: `last_attempt`, `observed_at`, `last_success` (nullable);
- `collection_status`: `success`, `partial`, or `failure`;
- `in_progress`, `test_mode`, configured/successful county counts;
- `county_names`: the existing county-name mapping already loaded by SkywarnPlus;
- `alerts`: the exact returned event/list-of-county-record pairs, including
  available `county_code`, numeric `severity`, `description`, `end_time_utc`.

An attempt initially publishes `in_progress: true`; it cannot claim a successful
check. Every completed collection publishes even when event/county names remain
unchanged. Failure/partial completion retains the previous complete-success time
and records the actual fallback set returned by SkywarnPlus. Injected development
alerts are explicitly marked and never presented as live weather. An empty
configured county set cannot produce a successful all-clear.

Writes use a temporary file, fsync and atomic replacement, with a nonblocking
producer lock and an attempt-time guard against older overlapping cron runs.
Snapshots are limited to 1 MiB. Lock/output errors are isolated from upstream;
an unrefreshed snapshot ages out. The output is public weather telemetry (0644),
contains no credentials, and must be readable by the BlueNode service account.

BlueNode performs bounded regular-file reads, caches by file metadata, and
publishes sanitized weather state in its existing `system.json`. No browser
request executes collection. A recent complete success (within 180 seconds) is
CURRENT; zero records means **No active weather alerts**. An old successful
snapshot is STALE. Partial, failed, malformed, missing, disabled, in-progress,
or test-injection telemetry is UNAVAILABLE. Expired records are removed from the
active presentation; a successful new empty snapshot clears previous alerts.

For a custom `DEV.TmpDir`, set the optional BlueNode config section explicitly:

```json
"weather_alerts": {
  "snapshot_path": "/custom/local/path/bluenode-weather.json"
}
```

Use a local filesystem and preserve SkywarnPlus producer ownership. County names use the mapping already loaded by SkywarnPlus, with county codes
as the fallback; BlueNode performs no geographic lookup. Numeric severity is
labelled as the SkywarnPlus 0–4 scale, since its API and name-fallback mappings
have different meanings. Issued/effective times and headlines are not invented.

## Dashboard and Emergency Mode

The compact SkywarnPlus card retains enabled/disabled status and emphasizes alert
types. SkywarnPlus groups by event type, so counts are labelled **alert types**,
not distinct warning IDs. The expandable Current Weather Alerts section shows
each supplied area record, severity, end time and escaped description. Existing
On/Off controls remain in BlueNode Controls beneath the awareness sections.

Tornado, Severe Thunderstorm, Flash Flood, Hurricane and Tsunami Warnings receive
a visible warning accent and appear in the existing Emergency Mode banner **only
as information**. Weather never activates Emergency Mode or any control.

The previous SkywarnPlus value waited for Intelligence, Emergency Mode and live
AllStar fetches after `system.json` arrived. Its status/weather now render first;
the browser fixture holds Intelligence pending to verify this. There was no
expensive SkywarnPlus command in the original status read. A local timer expires
weather presentation even if another request stalls, without additional polling.
Unchanged detail markup preserves expanded descriptions across refreshes.

## Validation and future deployment

Run the Python suite, all dashboard/browser suites, public-tree audit and
`deploy/test_clean_install.py`; also run the source-specific isolated check above.
Fixtures cover empty/one/multiple alerts, changes/removal/expiry, malformed and
oversized data, partial/failure/stale/missing state, disabled integration, atomic
failure, overlapping attempts, patch guards, rendering and existing auth/controls.

Production deployment is a separate approved operation. Back up BlueNode plus
the existing SkywarnPlus script/module and validate compatibility first. Deploy
BlueNode through its supported path, keeping BlueNode writers quiescent during
archives. Apply the optional observer only after its check passes; wait for the
existing scheduled collection rather than invoking SkywarnPlus manually. Validate
local APIs on the node and HTTPS from another peer. Confirm snapshot freshness,
browser display and unchanged Asterisk identity. Rollback must restore both the
matching upstream script/module and BlueNode backup; preserve runtime history.
No Asterisk restart, radio test, additional weather dependency or network change
is required.
