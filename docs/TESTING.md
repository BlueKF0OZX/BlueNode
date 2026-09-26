# Testing BlueNode

Run from the repository root. Tests use public example configuration and temporary fixtures; never point the test suite at an operator's live configuration.

## Python on Windows

```powershell
$env:NODESMART_CONFIG = Join-Path (Get-Location) 'config/nodesmart.example.json'
python -m unittest discover -s core -v
```

Use an installed Python 3.11+ interpreter. POSIX file-security and terminal tests skip on Windows. The Soft Radio transaction tests use Bash (Git for Windows is supported). test_intelligence.py is a scenario-printing script imported during discovery, not an assertion suite.

## Dashboard

```sh
node core/test_dashboard.js
node core/test_live_activity.js
node core/test_event_history.js
node core/test_saved_nodes.js
node core/test_shared_favorites_browser.js
node core/test_fresh_dashboard.js
node core/test_remote_access.js
node core/test_dashboard_render.js
node core/test_control_auth.js
node core/test_control_routing.js
```

The browser suites, including shared favorites and the last three listed above,
need Playwright resolvable by Node and Chromium. BLUENODE_BROWSER_PATH can select
an installed compatible browser. Rendering checks use 320, 390, 768, 1024, and
1440px and write screenshots to a temporary directory (or BLUENODE_RENDER_OUTPUT).
No request reaches an actual node.

The shared-favorites browser suite starts the real Python HTTP/favorites service
on loopback with temporary storage and uses separate phone/PC browser contexts.
It verifies migration, save/rename/remove synchronization, automatic refresh,
reload persistence, and touch targets. Set `BLUENODE_TEST_PYTHON` if Python is not
on PATH (`python` on Windows, `python3` elsewhere). Other requests are fixtures;
the suite never reaches an operating node. Backend tests cover concurrent edits,
corrupt state, capacity, storage failure, authentication, CSRF, and origins.

## Repository and deployment fixtures

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\deploy\Test-DeployBlueNode.ps1
powershell -NoProfile -ExecutionPolicy Bypass -File .\deploy\Test-PublicTree.ps1
git diff --check
```

The deployment regression creates temporary local Git repositories and a local bare remote. It does not deploy or push to GitHub. The public-tree check scans tracked/staged paths and text; it does not replace review of ignored files or external credentials.

## Linux-only integration

```bash
sudo python3 deploy/test_clean_install.py
python3 deploy/test_skywarn_upstream.py /path/to/SkywarnPlus.py
```

The clean-install fixture requires Debian namespace/chroot tools and the dependencies in [Installation](INSTALL.md). The source-specific weather check requires the operator-selected upstream source; it isolates its collection function with synthetic requests. Neither check establishes live RF/audio correctness. Do not perform disruptive validation on an operating AllStar node.

## Automated pull request checks

The BlueNode checks workflow runs on pull requests and pushes to main or configured feature
branches. Core regression runs Python 3.11 on Linux using only the public example
configuration. Dashboard regression runs every core/test_*.js suite with pinned
Playwright and Chromium; node observations and controls are synthetic. Repository
checks run the public-tree scan and disposable deployment-tool fixtures on Windows.
The workflow has read-only repository permission and no deployment credentials.
It does not install BlueNode on an operating node or certify live radio behavior.

The branch-protection check names are Core regression, Dashboard regression,
and Repository checks. Require them only after their first successful GitHub run.
