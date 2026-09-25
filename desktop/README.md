# Building BlueNode Setup

Windows x64, .NET 8 SDK, PowerShell, Git. The published executable bundles the
runtime, so end users do not install .NET. SSH.NET 2026.0.0 and its transitive
dependencies are pinned by `packages.lock.json`; restore uses nuget.org only.

From a clean checkout of the release (with all changes staged if developing):

```powershell
./desktop/build.ps1
```

The build embeds tracked files from `core`, `web`, `install`, `config`, and
`systemd`, checks the packaged executable/runtime, and prints its SHA-256.
It excludes local settings, `.git`, backups, and credentials. The output is
`desktop/dist/BlueNode-Setup.exe`. Publish the executable and a checksum as release
assets, not in the source tree. An unsigned alpha may trigger Windows warnings.
Third-party licenses are embedded and available from the app's license link.
Keep licenses current when changing dependencies or the bundled runtime.

## Tests

Backend protocol tests run with the regular Python suite (`test_desktop_bridge.py`).
The Windows integration harness uses exactly the app's SSH/session implementation:

```powershell
dotnet restore desktop/tests/SetupChecks.csproj --configfile desktop/NuGet.Config
dotnet build desktop/tests/SetupChecks.csproj --no-restore -c Release
dotnet desktop/tests/bin/Release/net8.0-windows/SetupChecks.dll --render setup.png
```

For a **disposable, checkpointed ASL3 lab only**, set `BLUENODE_TEST_HOST`,
`BLUENODE_TEST_PORT`, `BLUENODE_TEST_USER`, `BLUENODE_TEST_FINGERPRINT`, and either
`BLUENODE_TEST_KEY` or `BLUENODE_TEST_SECRET` in the process environment. Running
the harness without arguments checks rejection of an untrusted identity and
opens an existing dashboard through SSH. With `--install` and
`BLUENODE_TEST_NODE`, it performs a confirmed fresh installation, disconnects
deliberately, reconnects, and checks the dashboard/node identity. It changes
the disposable node. Do not use that mode against an operator's live node.
Never save passwords in commands, source, reports, or CI configuration files.

The app remembers only connection details and approved host fingerprints under
LocalAppData. Sudo input goes through the SSH command's input stream, never
command arguments. No remote shell is constructed from operator input. The
root bridge has a small JSON protocol and exposes no HTTP endpoint. A detached
root worker inherits the guided installer's exclusive lock and runs the same
fresh-install transaction. The desktop release intentionally does not add a
second updater or a new dashboard administration API.
