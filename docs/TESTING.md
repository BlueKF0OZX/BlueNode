# Testing BlueNode

Run from the repository root. Tests use public example configuration and temporary fixtures; never point the test suite at an operator's live configuration.

## Python on Windows

```powershell
$env:NODESMART_CONFIG = Join-Path (Get-Location) 'config/nodesmart.example.json'
python -m unittest discover -s core -v
```

Use an installed Python 3.9+ interpreter. POSIX file-security and terminal tests skip on Windows. The Soft Radio transaction tests use Bash (Git for Windows is supported). test_intelligence.py is a scenario-printing script imported during discovery, not an assertion suite.

## Dashboard

```sh
node core/test_dashboard.js
node core/test_fresh_dashboard.js
node core/test_remote_access.js
node core/test_dashboard_render.js
node core/test_control_auth.js
node core/test_control_routing.js
```

The last three need Playwright resolvable by Node and Chromium. BLUENODE_BROWSER_PATH can select an installed compatible browser. Rendering checks use 320, 390, 768, 1024, and 1440px and write screenshots to a temporary directory (or BLUENODE_RENDER_OUTPUT). No request reaches an actual node.

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
