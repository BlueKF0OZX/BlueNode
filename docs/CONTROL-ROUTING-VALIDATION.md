# Dashboard control routing validation

Run node core/test_control_routing.js and node core/test_control_auth.js with Playwright available. Optional BLUENODE_BROWSER_PATH selects an installed Chromium-compatible browser.

The suites use local intercepted requests in trusted-local, signed-out, and authenticated scenarios. They check DODROPIN, manual nodes, Emergency Mode, maintenance, administrative routes, CSRF headers, and pending target/action text. Confirm cancellation sends no action. Sign-in resumes a pending action once; failed login, cancellation, reload, or unavailable session verification discards it. Disabled Skywarn controls remain read-only.

These browser fixtures prove routing and presentation, not actual radio outcomes. core/test_node_controls.py separately tests fresh App_Rpt observation, already-satisfied requests, invalid targets, missing mappings, command failure, timeouts, and post-command verification. Actual ASL3 compatibility belongs in a separate authorized test environment. See [Testing](TESTING.md).
