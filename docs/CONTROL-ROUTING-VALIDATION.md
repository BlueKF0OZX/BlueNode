# Dashboard control routing validation

Run node core/test_control_routing.js and node core/test_control_auth.js with Playwright available. Optional BLUENODE_BROWSER_PATH selects an installed Chromium-compatible browser.

The suites use local intercepted requests in trusted-local, signed-out, and authenticated scenarios. They check DODROPIN, manual nodes, Emergency Mode, maintenance, administrative routes, CSRF headers, and pending target/action text. Confirm cancellation sends no action. Sign-in resumes a pending action once; failed login, cancellation, reload, or unavailable session verification discards it. Disabled Skywarn controls remain read-only.

These browser fixtures prove routing and presentation, not actual radio outcomes. core/test_node_controls.py separately tests fresh App_Rpt observation, already-satisfied requests, invalid targets, missing mappings, command failure, timeouts, and post-command verification. Actual ASL3 compatibility belongs in a separate authorized test environment. See [Testing](TESTING.md).

## Pending links and failure evidence

A connect request for a target already reported in pending mode (`C`) waits for
fresh confirmation within the normal verification window. It does not issue a
second connect command. Disconnecting a pending link still issues the requested
disconnect. Concurrent controls remain rejected with HTTP 409; this is not yet
a node-switch queue or an automatic retry mechanism.

Failed controls save structured evidence in
`/opt/nodesmart/logs/control-failures.jsonl`: action, target node, reason,
timestamps, elapsed time, command-attempt status/return code, observation count,
and the initial/latest parsed App_Rpt link observations. Retention is one MiB
per file with two rotated backups. Raw command output, credentials, and the
configuration are not copied. These are operator diagnostics containing node
identifiers; review them before sharing. The file is not a public dashboard
endpoint. An initial-only snapshot after command failure does not establish
the resulting link state.

Failure responses include `reason`, `diagnostic_saved`, and `diagnostic_id`
(null when storage failed). A diagnostic write failure never changes the
control outcome or holds the control lock. The dashboard already displays the
plain-language error. No restart, stale-link cleanup, or automatic reconnect
is triggered by these failures.

Regression coverage includes pending-to-connected, pending timeout, observation
loss, missing confirmation, disconnect while pending, concurrent rejection,
and unavailable diagnostic storage. Actual pending-link behavior still needs
verification against an isolated ASL3 peer before production deployment.
