# Dashboard control routing investigation

Historical findings below describe the investigation at `6aaf643`. The subsequent
authenticated-control UX retains the same security boundary and now offers login
and one-time action resumption after HTTP 401; see `REMOTE_ADMIN.md`.

The reported post-polish login regression was investigated against the pre-polish
`bf91361` dashboard and the published `2e84860` dashboard. Browser clicks in both
versions use the same `/api/control/*` endpoints for ordinary controls, without
invoking `adminLogin` or posting to `/api/admin/login`.

The `bf91361` backend explicitly calls `require_admin(csrf=True)` for all
`/api/control/*` requests when Remote Admin is enabled. Consequently an
unauthenticated request receives `401 Remote Admin authentication required` even
with the old dashboard. This is an existing backend policy, not evidence of a
new frontend endpoint redirect. The production session endpoint reported Remote
Admin enabled during this investigation. An unauthenticated read-only probe does
not establish whether the operator's browser has a valid session.

No application or security change was made. A frontend-only bypass would not
preserve the existing backend security contract. The operator's exact browser
symptom (inline error, dashboard sign-in panel, browser authentication prompt, or
navigation to a login page) and session state remain necessary to diagnose a
different failure that was not reproduced in these isolated tests.

## Repeatable browser coverage

With Playwright available through `NODE_PATH`, run:

```sh
node core/test_control_routing.js
```

Set `BLUENODE_BROWSER_PATH` to an installed Chromium-compatible browser when
needed. Historical HTML comparison was supported by the test at `6aaf643`;
the current suite tests the new pending-control flow. All requests are intercepted and
fulfilled by synthetic fixtures; no control request reaches an actual node.

The tests click DODROPIN, Skywarn, manual node, Emergency Mode, and maintenance
controls in local, signed-out Remote Admin, and authenticated scenarios. They
verify endpoints, node payloads, CSRF headers, and absence of login invocation.
Protected admin requests and helpers remain subject to authentication in the
fixture. Existing Python HTTP security tests separately exercise actual backend
authentication and CSRF rejection; browser fixtures alone do not prove server
security enforcement.
