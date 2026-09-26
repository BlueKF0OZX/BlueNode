# Shared favorites validation

The development dashboard saves up to 20 favorites in the node's
`state/favorites.json`. Names and numbers are shared between devices connected to
that node. Recent Nodes and Auto-switch remain browser preferences. This change
is after the published 0.1.5-alpha.1 release; existing release installers do not
contain it.

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
  for a different node identity.
- The complete workstation run passed 268 Python tests with six platform skips,
  and all 14 JavaScript suites, including five-width dashboard rendering.

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
