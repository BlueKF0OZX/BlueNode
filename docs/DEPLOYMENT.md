# Deployment

After an approved change has been tested, committed, and pushed to `main`, run
the deployment from a Windows PowerShell prompt at the repository root:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\deploy\Deploy-BlueNode.ps1
```

The command refuses to deploy a dirty tree, a branch other than `main`, a local
`main` that differs from `origin/main`, or any configured/commit author identity
other than `BlueKF0OZX <bluedrummer1985@outlook.com>`. It deploys the recorded
commit through the existing SSH alias `nodesmart60873`.

Before changing `/opt/nodesmart`, the remote process creates and verifies a
timestamped archive under `/opt/nodesmart-backups`. Git updates only tracked
application files; machine-specific `config/nodesmart.json`, `events`, `history`,
`logs`, and `state` data are preserved and their service ownership is repaired.

The deployed commit, service, live state files, Asterisk CLI, dashboard HTTP
endpoint, and new journal messages are validated. If any post-change validation
fails, the failed tree is retained under `/opt/nodesmart-backups`, the verified
backup is restored, and the BlueNode services are restarted and checked. The command
returns a nonzero exit code and prints `FAIL` even when rollback succeeds.

This workflow does not change Asterisk configuration, networking, firewall,
sudoers, systemd unit definitions, releases, tags, or Git history.
