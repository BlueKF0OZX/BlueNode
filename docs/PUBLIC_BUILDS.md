# Public builds and local customizations

Each installation runs its own copy of BlueNode. Updating GitHub does not update
an operating node automatically. A change made directly on one node does not
appear in the public repository unless it is deliberately contributed.

## Choose the version you will test

`main` contains merged development work and can change. It is currently an early
alpha. A pull-request branch can contain features that have not reached `main`.
Tags identify historical versions; check their validation notes before choosing.

Record `git rev-parse HEAD` in your source checkout before installation. Keep that
checkout at the recorded commit throughout a repeatable evaluation. Record the
installed backend version from Remote Admin when available. If files were copied
or edited outside Git, also record that fact: a commit label alone does not prove
every installed file matches it.

## What a public installation includes

Shared monitoring, diagnostics, verified node controls, activity history, saved
nodes, and responsive controls are included. Replace the example identity with
your own. Favorites are stored in that browser, per monitored node, and do not
automatically follow you to another phone or computer.

Weather observations need their documented optional integration. A customized
station may show regional weather, an operating schedule, additional controls,
or a different sign-in flow absent from the public build. Do not copy another
operator's private configuration to reproduce it.

Remote HTTPS access and application-level Remote Admin are separately configured.
Opening the website can require gateway credentials, while protected controls
can require a second Remote Admin sign-in. Those credentials can differ. See
[Remote access](REMOTE_ACCESS.md) and [Remote Admin](REMOTE_ADMIN.md).

## Keep local work during an upgrade

Inventory local source edits, configuration, integrations, and the installed
service account. Follow [Upgrade and rollback](UPGRADE.md). Preserve a verified
backup and review how each local change will be retained; installing public files
over a customized tree can replace custom code.

Configuration preservation does not imply source-code preservation. The strict
maintainer deployment workflow rejects a modified checkout. Resolve changes
through a reviewed integration rather than bypassing that check.

## What passing checks establish

GitHub checks cover core regression, dashboard fixtures, public-tree hygiene, and
disposable deployment-tool scenarios. They do not connect to operating radios.
A successful private installation is evidence for that installation, not proof
that the unchanged public build works on different hardware or gateways. Use
[Early testing](EARLY_TESTING.md) and [Validation status](VALIDATION_STATUS.md)
to distinguish automated results from radio and endurance checks.
