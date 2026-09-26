# Shared favorites validation

Starting with 0.1.6-alpha.1, the dashboard saves up to 20 favorites in the node's
`state/favorites.json`. Names and numbers are shared between devices connected to
that node. Recent Nodes and Auto-switch remain browser preferences. This change
requires the matching backend and dashboard. Installers from 0.1.5-alpha.1 and
earlier do not contain it.

## Verified on September 26, 2026

- Backend tests cover save, rename, remove, fresh reads after persistence,
  competing revisions, import without overwriting shared names, invalid input,
  capacity, corrupt/wrong-node/oversized files, and failed writes.
- HTTP tests exercise disabled/enabled Remote Admin, sign-in, CSRF rejection,
  foreign-origin rejection, and malformed authentication configuration. Favorite
  changes do not invoke node controls.
- Two independent Chromium browser contexts, at 1440px desktop and 390px mobile
  widths, use the real Python HTTP/favorites service and temporary storage. PC
  import, phone rename, PC save, phone removal, automatic refresh, reload,
  touch targets, and persisted content passed. All other requests use synthetic
  fixtures. No operating node is contacted.
- Frontend checks cover conflicting edits, unavailable service, blocked browser
  storage, escaping, canceled rename, recent-node rules, and delayed responses
  for a different node identity. Protected gateways that return HTTP 403 with
  `auth_required` also display the sign-in action.
- The complete workstation run passed 268 Python tests with six platform skips,
  and all 14 JavaScript suites, including five-width dashboard rendering.
- A reviewed four-file overlay was deployed to an existing customized node,
  with a backup and a tested rollback path. Served file hashes and sign-in
  enforcement passed; configuration hashes and the Asterisk process were
  unchanged. The operator confirmed favorites matched on their actual phone
  and PC after refreshing. This is one installation's acceptance, not coverage
  of every gateway or hardware combination.

## Deployment and operator acceptance

Deploy the matching backend and dashboard together. Copying only the HTML onto
an older backend leaves shared favorites unavailable. The state directory must
be writable by the web service account; include its favorites file in backups.
Do not replace a customized operating installation with the public tree without
reviewing and preserving its changes.

After a reviewed deployment, sign in from the actual PC and phone, import any
old browser favorites, and verify one save, rename, and removal on both devices.
Different node installations have separate lists. Do not claim actual phone,
remote gateway, or production deployment acceptance from the fixture tests above.
