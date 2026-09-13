# Troubleshooting report

Open **Smart Connectivity** on the dashboard and select **Preview report**.
Review the snapshot, then select **Download report** to save a plain-text file
for a support request. Nothing is sent to a support service automatically.

The report contains overall health, Asterisk and Internet status, CPU
temperature, memory and disk usage, uptime, and connectivity check results.
Its observation timestamp and age help distinguish old monitoring data from
current observations. Preparing a report reads cached monitoring data; it
does not run diagnostics or change the node.

Only predefined fields, status values, booleans, and numeric measurements
are exported. Logs, callsigns, node numbers, addresses, configuration, and
free-text observations are excluded. Missing or unrecognized values appear
as unavailable. If monitoring data cannot be read, any previous preview is
cleared and download stays disabled until a new report succeeds.

Validation: `node core/test_support_report.js` checks the export privacy
boundary and missing/invalid observations. `node core/test_dashboard_render.js`
checks preview, download contents, failed refresh, and mobile layout using
synthetic observations.
