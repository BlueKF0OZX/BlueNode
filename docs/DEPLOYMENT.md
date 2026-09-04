# Deployment

After an approved change has been tested, committed, and pushed to `main`, run
the deployment from a Windows PowerShell prompt at the repository root:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\deploy\Deploy-BlueNode.ps1
```

The command refuses to deploy a dirty tree, a branch other than `main`, a local
`main` that differs from `origin/main`, or any configured/commit author identity
other than `BlueKF0OZX <bluedrummer1985@outlook.com>`. It deploys the recorded
commit through an explicitly configured operator SSH target.

Configure the target outside tracked files using one of these methods:

```powershell
git config --local bluenode.sshTarget example-node
$env:BLUENODE_SSH_TARGET = "example-node"
powershell -NoProfile -ExecutionPolicy Bypass -File .\deploy\Deploy-BlueNode.ps1 -SshTarget example-node
```

The local Git setting is recommended for the canonical no-argument deployment
command. It remains in `.git/config` and is never committed.

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

## Canonical autonomous workflow

Use these stable commands for routine work so execution approvals remain narrow
and reusable:

```powershell
# Before committing: verify branch, official origin, and exact Git identity.
powershell -NoProfile -ExecutionPolicy Bypass -File .\deploy\Verify-BlueNodeGit.ps1 -IdentityOnly

# Push only main to its named origin.
git push origin main

# When no deployment is required, verify the clean tree, remote main, and attribution.
powershell -NoProfile -ExecutionPolicy Bypass -File .\deploy\Verify-BlueNodeGit.ps1

# Normal deployment, including local Git gates and live verification.
powershell -NoProfile -ExecutionPolicy Bypass -File .\deploy\Deploy-BlueNode.ps1
```

For an application deployment, the final Git verification is already part of
`Deploy-BlueNode.ps1`; routine ad-hoc SSH checks afterward are unnecessary. Its
single remote session verifies the backup, exact live commit, compilation,
services, state freshness, Asterisk, dashboard HTTP response, and journal. Use
separate read-only SSH diagnostics only when the guarded report fails or a
request specifically requires additional live evidence.

The intended sequence is: inspect, edit, test, review, identity verification,
commit, `git push origin main`, guarded deployment, built-in live verification,
report.

The canonical Git verifier also runs `deploy/Test-PublicTree.ps1`. This rejects
tracked runtime/state directories, live configuration, private-key file types,
and common private-key, Tailscale, GitHub, cloud-key, password, and token
signatures. It scans tracked and staged text content, while ignored local
runtime data remains outside the public repository. It also rejects known
operator-specific fixture identifiers while preserving the intentional
`BlueKF0OZX <bluedrummer1985@outlook.com>` project identity.
