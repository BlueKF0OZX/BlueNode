# Upgrade and rollback

Use a separate checkout and a reviewed commit. The installer preserves live nodesmart.json and runtime directories, but replaces application code and the project-owned helpers, service templates, and sudo rules. Review local customizations to those managed files before proceeding. It is not a general configuration migration engine or an automatic rollback tool.

## Before an upgrade

1. Record the existing application commit/version and service account. If the installation is a copied tree without Git metadata, retain its original checkout or package. A dashboard-only overlay can have a different UI commit; record both.
2. Review the target changelog, configuration example, helper, sudoers, and systemd changes. Do not use dashboard-only deployment for a change requiring backend or installer updates.
3. Prepare a private, root-only backup directory outside the installation. Stop only nodesmart and nodesmart-web while making a consistent backup; AllStar/Asterisk remains running.
4. Back up /opt/nodesmart, the two BlueNode units under /etc/systemd/system, /etc/sudoers.d/nodesmart, the installed BlueNode helpers, and /etc/bluenode if present. Preserve ownership and permissions. Include Remote Admin configuration and its .intent marker together. Include separately managed Apache integration files if that integration will be changed. Never publish these backups.
5. Check that the archive can be listed, record its checksum, and test restoration on a disposable Linux host before relying on it. Ensure enough space for the backup, candidate application, and a retained failed installation.

## Apply a reviewed version

In the separate public checkout, select the reviewed commit and validate the operator configuration before invoking the installer. Replace REVIEWED_COMMIT and SERVICE_USER deliberately:

```bash
git fetch origin
git switch --detach REVIEWED_COMMIT
sudo python3 install/validate-config.py /opt/nodesmart/config/nodesmart.json
sudo NODESMART_USER=SERVICE_USER bash install/install.sh
```

The installer restarts only BlueNode services. Check both service statuses, the dashboard, fresh monitoring data, authentication state, and the unchanged Asterisk process/link state. Do not test recovery by stopping Asterisk on an operating radio node.

No nodesmart.json schema migration is introduced by this batch. New optional defaults do not replace operator values. Remote Admin's existing intent migration records prior configuration before the new policy starts; it neither invents credentials nor enables a new installation. Future incompatible configuration changes must have an explicit migration, a pre-migration backup, and refusal of unsupported versions before replacement.

## Roll back

If validation fails, stop only BlueNode services. Retain the failed application for diagnosis. Restore the complete prior BlueNode application and matching managed helpers, units, sudo rules, configuration, and security intent from the verified backup, preserving ownership and modes. Do not combine old code with newly migrated configuration. Validate restored sudoers with visudo and restored units with systemd-analyze verify; reload systemd, restart only BlueNode, and repeat the health/authentication checks. Do not restore or change Asterisk, radio, network, or Tailscale configuration as part of this procedure.

The maintainer Git-checkout deployment script has its own verified backup and automatic rollback path; see [Deployment](DEPLOYMENT.md). The general installer does not provide that guarantee. Linux installation, upgrade failure, and restoration must pass the isolated clean-install fixture before a release is considered ready.

Automatic recovery now requires the exact sudo rule for `/usr/bin/systemctl --job-mode=fail start asterisk`. Install the matching reviewed sudoers template with the application. Without this rule, recovery fails closed; it never falls back to restart. An already active service is left running, and a conflicting queued systemd job is rejected. Explicit Remote Admin restart remains a separate, confirmed disruptive action.
