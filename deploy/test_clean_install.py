#!/usr/bin/env python3
"""Debian-only installer integration fixture. Run with sudo, outside /opt/nodesmart.

Re-executes in private mount/network/PID namespaces, copies OS tools into a
temporary chroot, and substitutes Asterisk, sudo and systemctl. No host service,
radio socket, configuration, credentials, or network is reachable inside it.
"""
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import tempfile
import unittest

SOURCE = Path(__file__).resolve().parents[1]


def run(*args, **kwargs):
    return subprocess.run(args, check=True, text=True, **kwargs)


class CleanInstall(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp = tempfile.TemporaryDirectory(prefix="bluenode-clean-")
        cls.root = Path(cls.temp.name)
        cls.addClassCleanup(cls.cleanup)
        # The host may mount /tmp noexec/nodev. This mount exists only in our
        # private namespace and does not change the host's /tmp options.
        run("mount", "-t", "tmpfs", "-o", "size=128m,mode=0755", "tmpfs", str(cls.root))
        for name in ("tmp", "etc/systemd/system", "etc/sudoers.d", "etc/asterisk",
                     "usr/local/bin", "usr/local/sbin", "run", "dev", "proc", "sys"):
            (cls.root / name).mkdir(parents=True, exist_ok=True)
        (cls.root / "tmp").chmod(0o1777)
        for name in ("bin", "sbin", "lib"):
            (cls.root / "usr" / name).mkdir(exist_ok=True)
            (cls.root / name).symlink_to("usr/" + name)
        (cls.root / "etc/passwd").write_text(
            "root:x:0:0:root:/root:/bin/bash\noperator:x:1234:1234:Fixture:/tmp:/bin/bash\n")
        (cls.root / "etc/group").write_text("root:x:0:\noperator:x:1234:\n")
        (cls.root / "etc/nsswitch.conf").write_text("""passwd: files
group: files
hosts: files
""")
        (cls.root / "etc/sudoers").write_text("root ALL=(ALL:ALL) ALL\n@includedir /etc/sudoers.d\n")
        (cls.root / "etc/sudoers").chmod(0o440)
        for name in ("sysinit", "basic", "shutdown", "network", "network-online", "multi-user"):
            (cls.root / "etc/systemd/system" / (name + ".target")).write_text(
                "[Unit]\nDescription=Isolated fixture target\nDefaultDependencies=no\n")
        cls.sentinels = {}
        for name in ("rpt.conf", "extensions.conf", "iax.conf", "simpleusb.conf", "usbradio.conf"):
            path = cls.root / "etc/asterisk" / name
            cls.sentinels[path] = b"untouched generic operator configuration\n"
            path.write_bytes(cls.sentinels[path])
        binaries = ("bash", "python3", "install", "id", "mkdir", "cp", "rm", "mv", "rmdir",
                    "mktemp", "sed", "chown", "chmod", "find", "dirname", "visudo",
                    "systemd-analyze", "git", "ip", "ping", "free", "df", "getent", "sleep", "ln", "tee", "basename", "cmp",
                    "head", "cat", "stat", "tar", "gzip", "date", "grep", "awk", "tr", "cut", "wc", "flock", "sync", "xargs", "sha256sum", "readlink", "realpath", "sort")
        for name in binaries:
            binary = shutil.which(name)
            if not binary:
                raise RuntimeError("Required fixture tool missing: " + name)
            cls.copy_binary(Path(binary))
        cls.copy_binary(Path("/bin/sh"))
        (cls.root / "usr/lib/git-core").mkdir(parents=True, exist_ok=True)
        for name in ("git-upload-pack", "git-receive-pack"):
            (cls.root / "usr/lib/git-core" / name).symlink_to("/usr/bin/git")
        stdlib = Path(subprocess.check_output(
            ["python3", "-c", "import sysconfig; print(sysconfig.get_path('stdlib'))"], text=True).strip())
        shutil.copytree(stdlib, cls.root / str(stdlib).lstrip("/"), dirs_exist_ok=True,
                        ignore=shutil.ignore_patterns("__pycache__", "site-packages", "dist-packages"))
        for library in stdlib.glob("lib-dynload/*.so"):
            cls.copy_binary(library)
        # Only kernel devices, never a host radio/TTY or Asterisk socket.
        for name, minor in (("null", 3), ("zero", 5), ("random", 8), ("urandom", 9)):
            import stat
            os.mknod(cls.root / "dev" / name, stat.S_IFCHR | 0o666, os.makedev(1, minor))
        run("mount", "-t", "proc", "proc", str(cls.root / "proc"))
        (cls.root / "dev/pts").mkdir()
        run("mount", "-t", "devpts", "devpts", str(cls.root / "dev/pts"),
            "-o", "newinstance,ptmxmode=0666")
        (cls.root / "dev/ptmx").symlink_to("pts/ptmx")
        run("ip", "link", "set", "lo", "up")
        for name in ("core", "web", "install", "systemd", "config", "deploy"):
            shutil.copytree(SOURCE / name, cls.root / "src" / name,
                            ignore=shutil.ignore_patterns("__pycache__"))
        cls.script("usr/bin/systemctl", '''#!/bin/bash
echo "$*" >> /systemctl.calls
case "$*" in
  'daemon-reload'|'enable nodesmart nodesmart-web'|'restart nodesmart nodesmart-web') exit 0;;
  'show asterisk -p MainPID -p ActiveEnterTimestampMonotonic') printf 'MainPID=42\\nActiveEnterTimestampMonotonic=1000\\n'; exit 0;;
  'is-active --quiet asterisk') exit 0;;
  'is-active --quiet nodesmart'|'is-active --quiet nodesmart-web') [[ ! -f /fail-start ]]; exit $?;;
  'status nodesmart --no-pager'|'stop nodesmart.service nodesmart-web.service'|'restart nodesmart.service nodesmart-web.service') exit 0;;
  'show nodesmart.service -p User --value') echo operator;;
  'show asterisk -p ActiveState -p SubState -p MainPID -p LoadState') printf 'ActiveState=active\\nSubState=running\\nMainPID=42\\nLoadState=loaded\\n';;
  'is-active --quiet nodesmart.service'|'is-active --quiet nodesmart-web.service') exit 0;;
  *) echo "Forbidden fixture service operation: $*" >&2; exit 99;;
esac
''')
        cls.script("usr/bin/sudo", '''#!/bin/bash
[[ "${1:-}" == -n ]] && shift
echo "$*" >> /tmp/sudo.calls
exec "$@"
''')
        cls.script("usr/sbin/asterisk", '''#!/bin/bash
echo "$*" >> /tmp/asterisk.calls
case "$*" in
  '-rx core show version') echo 'Asterisk 22.0 fixture';;
  '-rx rpt show variables '*) printf 'RPT_RXKEYED=0\\nRPT_TXKEYED=0\\nRPT_ALINKS=0\\n';;
  '-rx rpt lstats '*) echo 'No links';;
  *) exit 90;;
esac
''')
        cls.script("usr/bin/firewall-cmd", "#!/bin/bash\necho forbidden >> /firewall.calls\nexit 99\n")

    @classmethod
    def copy_binary(cls, source):
        target = cls.root / str(source).lstrip("/")
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, target)
        result = subprocess.run(["ldd", str(source)], capture_output=True, text=True)
        for name in re.findall(r"(?:=>\s+)?(/[^\s()]+)", result.stdout):
            library = Path(name)
            dest = cls.root / name.lstrip("/")
            dest.parent.mkdir(parents=True, exist_ok=True)
            if not dest.exists():
                shutil.copy2(library, dest)

    @classmethod
    def script(cls, name, content):
        path = cls.root / name
        path.write_text(content)
        path.chmod(0o755)

    @classmethod
    def cleanup(cls):
        for path in (cls.root / "dev/pts", cls.root / "proc", cls.root):
            if os.path.ismount(path):
                run("umount", str(path))
        cls.temp.cleanup()

    def inside(self, *args, user=None, check=True):
        command = ["chroot"]
        if user:
            command.append("--userspec=" + user)
        command += [str(self.root), *args]
        result = subprocess.run(command, env={"PATH": "/usr/sbin:/usr/bin:/sbin:/bin",
            "NODESMART_USER": "operator"}, capture_output=True, text=True)
        if check:
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        return result

    def test_clean_lifecycle(self):
        """First pass, invalid config, configured install, repeat, and failure."""
        app = self.root / "opt/nodesmart"
        self.assertFalse(app.exists())
        self.assertFalse((self.root / 'usr/local/bin/SkywarnPlus').exists())
        self.assertFalse((self.root / 'usr/bin/tailscale').exists())
        self.assertFalse((self.root / 'etc/bluenode').exists())
        first = self.inside("bash", "/src/install/install.sh")
        self.assertIn("NOT been started", first.stdout)
        self.assertFalse((self.root / "systemctl.calls").exists())
        self.assertFalse((self.root / "etc/sudoers.d/nodesmart").exists())
        config = app / "config/nodesmart.json"
        settings = json.loads(config.read_text())
        self.assertFalse(settings["recovery"]["asterisk_enabled"])
        self.assertEqual(settings["web"]["host"], "127.0.0.1")
        self.assertNotEqual(self.inside("bash", "/src/install/install.sh", check=False).returncode, 0)
        self.assertFalse((self.root / "systemctl.calls").exists())
        settings.update(node="23456", callsign="W1AW")
        config.write_text(json.dumps(settings))
        before = config.read_bytes()
        self.inside("bash", "/src/install/install.sh")
        for directory in ("state", "logs", "events", "history"):
            path = app / directory
            self.assertTrue(path.is_dir())
            self.assertEqual(path.stat().st_uid, 1234)
            self.assertEqual(path.stat().st_mode & 0o777, 0o750)
            self.assertEqual(list(path.iterdir()), [])
        self.assertEqual((app / "core/monitor.py").stat().st_uid, 0)
        self.assertEqual(config.stat().st_mode & 0o777, 0o640)
        self.assertEqual((self.root / "etc/sudoers.d/nodesmart").stat().st_mode & 0o777, 0o440)
        self.inside("visudo", "-c")
        # Start the actual installed first health cycle as the service account.
        # No historical files exist; network is isolated and Asterisk is fake.
        smoke = """import sys
sys.path.insert(0, '/opt/nodesmart/core')
from unittest.mock import Mock
import monitor, allstar_status, remote_admin, emergency_mode, recovery
allstar_status.check_changes()
state = monitor.run_health_cycle(Mock())
assert state['asterisk'] == 'online', state
assert state['asterisk_evidence']['query']['status'] == 'available'
assert state['asterisk_evidence']['node']['status'] == 'available'
assert state['connectivity']['diagnosis'] == 'unavailable', state['connectivity']
assert state['skywarn'] == 'unknown'
assert state['weather_alerts']['status'] == 'unavailable'
assert state['weather_alerts']['alerts'] == []
assert state['automation']['automation_armed'] is False
assert not remote_admin._safe_config()['enabled']
assert not emergency_mode.public_state()['active']
assert recovery.load_recovery_state() == {}
assert not recovery.ASTERISK_RECOVERY_ENABLED
import http.client, threading, web_server
from http.server import ThreadingHTTPServer
server = ThreadingHTTPServer(('127.0.0.1', 0), web_server.NodeSmartHandler)
thread = threading.Thread(target=server.serve_forever, daemon=True)
thread.start()
try:
    for path in ('/web/', '/web/soft-radio-worklet.js', '/state/system.json', '/state/intelligence.json', '/api/admin/session', '/api/emergency-mode'):
        connection = http.client.HTTPConnection('127.0.0.1', server.server_port, timeout=3)
        connection.request('GET', path)
        response = connection.getresponse()
        assert response.status == 200, (path, response.status)
        response.read()
        connection.close()
finally:
    server.shutdown()
    server.server_close()
    thread.join()
print('Unprivileged first monitor cycle and installed dashboard PASS')
"""
        self.inside("python3", "-c", smoke, user="1234:1234")
        # Exercise the installed adapter with generic local optional telemetry.
        # No upstream program, API, host state, or radio command is invoked.
        weather_smoke = """import sys,json,time,tempfile
from pathlib import Path
sys.path.insert(0, '/opt/nodesmart/core')
import weather_alerts
with tempfile.TemporaryDirectory() as folder:
    weather_alerts.SNAPSHOT_FILE = Path(folder) / 'weather.json'
    assert weather_alerts.public_state('enabled')['status'] == 'unavailable'
    now = time.time()
    snapshot = dict(schema_version=1, source='SkywarnPlus', last_attempt=now,
        observed_at=now, last_success=now, collection_status='success',
        in_progress=False, test_mode=False, configured_counties=1,
        successful_counties=1, alerts=[])
    weather_alerts.SNAPSHOT_FILE.write_text(json.dumps(snapshot))
    assert weather_alerts.public_state('enabled', now)['status'] == 'current'
    assert weather_alerts.public_state('enabled', now+181)['status'] == 'stale'
    assert weather_alerts.public_state('disabled', now)['status'] == 'unavailable'
    snapshot['collection_status'] = 'partial'
    replacement = Path(folder) / 'replacement.json'
    replacement.write_text(json.dumps(snapshot))
    replacement.replace(weather_alerts.SNAPSHOT_FILE)  # Match the atomic producer contract.
    assert weather_alerts.public_state('enabled', now)['status'] == 'unavailable'
print('SIMULATED PASS installed optional weather: absent/current/stale/partial/disabled')
"""
        self.inside("python3", "-c", weather_smoke, user="1234:1234")
        # Legacy credential migration preserves bytes and creates durable intent.
        self.assertFalse((self.root / "etc/bluenode/remote-admin.intent").exists())
        security = self.root / "etc/bluenode"
        security.mkdir(mode=0o750, exist_ok=True)
        os.chown(security, 0, 1234)
        remote_config = security / "remote-admin.json"
        credentials = json.dumps(dict(enabled=True, username="operator", password_salt="ab" * 24,
                                      password_hash="cd" * 32, session_secret="ef" * 32))
        remote_config.write_text(credentials); remote_config.chmod(0o640)
        os.chown(remote_config, 0, 1234)
        initializer = "/opt/nodesmart/install/remote-admin-init.py"
        for _ in range(2):
            self.inside("python3", initializer, "migrate-intent", "--service-user", "operator")
            self.assertEqual(remote_config.read_text(), credentials)
        policy = "import sys; sys.path.insert(0,'/opt/nodesmart/core'); import remote_admin; print(remote_admin._safe_config()['state'])"
        self.assertEqual(self.inside("python3", "-c", policy, user="1234:1234").stdout.strip(), "ENABLED")
        remote_config.unlink()
        self.assertEqual(self.inside("python3", "-c", policy, user="1234:1234").stdout.strip(), "CONFIG_ERROR")
        self.inside("python3", initializer, "disable", "--service-user", "operator")
        self.assertEqual(self.inside("python3", "-c", policy, user="1234:1234").stdout.strip(), "DISABLED")
        marker = security / "remote-admin.intent"
        self.assertEqual(marker.stat().st_uid, 0)
        self.assertEqual(marker.stat().st_mode & 0o777, 0o640)
        print("SIMULATED PASS Remote Admin legacy migration, repeat, lost config across processes, explicit disable")
        self.inside("systemd-analyze", "verify", "/etc/systemd/system/nodesmart.service",
                    "/etc/systemd/system/nodesmart-web.service")
        for name in ("nodesmart", "nodesmart-web"):
            unit = (self.root / "etc/systemd/system" / (name + ".service")).read_text()
            self.assertIn("User=operator", unit)
            self.assertIn("Group=operator", unit)
            self.assertNotIn("NODESMART_", unit)
        self.inside("bash", "/src/install/install.sh")
        self.assertEqual(config.read_bytes(), before)
        # Missing public source and malformed sudo policy must fail before mutation.
        prior_calls = (self.root / "systemctl.calls").read_bytes()
        prior_code = (app / "core/monitor.py").read_bytes()
        optional_template = self.root / "src/install/remote-access.conf.example"
        saved_template = optional_template.read_bytes()
        optional_template.unlink()
        try:
            self.assertNotEqual(self.inside("bash", "/src/install/install.sh", check=False).returncode, 0)
        finally:
            optional_template.write_bytes(saved_template)
        policy = self.root / "src/install/nodesmart.sudoers.example"
        saved_policy = policy.read_bytes()
        policy.write_text("invalid sudo policy @@@\n")
        try:
            self.assertNotEqual(self.inside("bash", "/src/install/install.sh", check=False).returncode, 0)
        finally:
            policy.write_bytes(saved_policy)
        self.assertEqual((self.root / "systemctl.calls").read_bytes(), prior_calls)
        self.assertEqual((app / "core/monitor.py").read_bytes(), prior_code)
        # Run tests only inside the jail: even unpatched absolute runtime paths
        # cannot read or write the host's /opt/nodesmart.
        result = self.inside("bash", "-c", "cd /src/core && python3 -m unittest discover -v")
        print(result.stdout + result.stderr, flush=True)
        self.inside("python3", "-m", "compileall", "-q", "/opt/nodesmart/core")
        shell_scripts = list((self.root / "src/install").rglob("*.sh"))
        shell_scripts += [p for p in (self.root / "src/install/helpers").iterdir()
                          if p.is_file() and p.read_text().startswith("#!/bin/bash")]
        for script in shell_scripts:
            self.inside("bash", "-n", "/" + str(script.relative_to(self.root)))
        # Existing state and auth permissions survive subsequent installation.
        marker = app / "state/fixture.json"
        marker.write_text('{"preserved": true}')
        self.inside("bash", "/src/install/install.sh")
        self.assertEqual(json.loads(marker.read_text()), {"preserved": True})
        (self.root / "fail-start").touch()
        failed = self.inside("bash", "/src/install/install.sh", check=False)
        self.assertNotEqual(failed.returncode, 0)
        self.assertEqual(config.read_bytes(), before)
        self.assertFalse((self.root / "firewall.calls").exists())
        for path, content in self.sentinels.items():
            self.assertEqual(path.read_bytes(), content)
        calls = (self.root / "systemctl.calls").read_text()
        for operation in ("restart", "stop", "reload", "start"):
            self.assertNotIn(operation + " asterisk", calls)
        print("SIMULATED PASS clean install: config, repeat, missing state, optional weather, units, sudoers, permissions, safety; Asterisk/sudo/systemctl substituted")

    def test_dashboard_deployment_preserves_backend_and_rolls_back(self):
        import time
        import urllib.request
        app = self.root / "opt/nodesmart"
        (self.root / "fail-start").unlink(missing_ok=True)
        (app / ".gitignore").write_text("__pycache__/\n*.pyc\nconfig/nodesmart.json\nstate/\nevents/\nhistory/\nlogs/\n")
        self.inside("git", "-C", "/opt/nodesmart", "init", "-b", "main")
        self.inside("git", "-C", "/opt/nodesmart", "add", ".gitignore", "core", "web", "install", "systemd", "config/nodesmart.example.json")
        def commit(where):
            self.inside("git", "-C", where, "-c", "user.name=Fixture",
                        "-c", "user.email=fixture@example.invalid", "commit", "-m", "Fixture")
        commit("/opt/nodesmart")
        baseline = self.inside("git", "-C", "/opt/nodesmart", "rev-parse", "HEAD").stdout.strip()
        self.inside("git", "clone", "--bare", "/opt/nodesmart", "/remote.git")
        self.inside("git", "-C", "/opt/nodesmart", "remote", "add", "origin", "/remote.git")
        self.inside("git", "clone", "/remote.git", "/candidate")
        candidate = self.root / "candidate"
        original_core = (app / "core/config.py").read_bytes()
        with (candidate / "web/index.html").open("a") as handle:
            handle.write("<!-- synthetic dashboard deployment fixture -->")
        with (candidate / "core/config.py").open("a") as handle:
            handle.write("\n# This backend change must not be deployed by dashboard-only mode.\n")
        self.inside("git", "-C", "/candidate", "add", "core/config.py", "web/index.html")
        commit("/candidate")
        target = self.inside("git", "-C", "/candidate", "rev-parse", "HEAD").stdout.strip()
        self.inside("git", "-C", "/candidate", "push", "origin", "main")
        calls_before = (self.root / "systemctl.calls").read_text()
        server = subprocess.Popen(["chroot", str(self.root), "python3", "/opt/nodesmart/core/web_server.py"],
                                  stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        try:
            for attempt in range(50):
                try:
                    with urllib.request.urlopen("http://127.0.0.1:8080/web/", timeout=1):
                        break
                except OSError:
                    time.sleep(0.1)
            else:
                self.fail("Isolated dashboard server did not start")
            command = ("bash", "/src/deploy/dashboard-only.sh", target, "/remote.git")
            self.inside(*command)
            self.inside(*command)  # A recorded overlay is safe to apply again.
            self.assertEqual((app / "web/index.html").read_bytes(), (candidate / "web/index.html").read_bytes())
            self.assertEqual((app / "core/config.py").read_bytes(), original_core)
            self.assertEqual(self.inside("git", "-C", "/opt/nodesmart", "rev-parse", "HEAD").stdout.strip(), baseline)
            config = app / "config/nodesmart.json"
            original_config = config.read_bytes()
            bad_config = json.loads(original_config)
            bad_config["web"]["port"] = 65534
            config.write_text(json.dumps(bad_config))
            failed = self.inside(*command, check=False)
            config.write_bytes(original_config)
            self.assertNotEqual(failed.returncode, 0)
            self.assertIn("ROLLBACK PASS", failed.stdout)
            self.assertEqual((app / "web/index.html").read_bytes(), (candidate / "web/index.html").read_bytes())
            self.assertNotIn("restart", (self.root / "systemctl.calls").read_text()[len(calls_before):])
        finally:
            server.terminate()
            server.wait(timeout=5)

    def test_full_deployment_intent_rollback(self):
        """Execute the supported deployment's rollback in the isolated chroot."""
        app = self.root / "opt/nodesmart"
        candidate = self.root / "candidate"
        source = (SOURCE / "deploy/Deploy-BlueNode.ps1").read_text()
        script = source.split("    $remoteScript = @'\n", 1)[1].split("\n'@", 1)[0]
        (self.root / "full-deploy.sh").write_text(script)
        (candidate / "core/deliberately_invalid_fixture.py").write_text("invalid fixture syntax !\n")
        self.inside("git", "-C", "/candidate", "add", "core/deliberately_invalid_fixture.py")
        self.inside("git", "-C", "/candidate", "-c", "user.name=Fixture",
                    "-c", "user.email=fixture@example.invalid", "commit", "-m", "Fixture failure")
        self.inside("git", "-C", "/candidate", "push", "origin", "main")
        target = self.inside("git", "-C", "/candidate", "rev-parse", "HEAD").stdout.strip()
        baseline = self.inside("git", "-C", "/opt/nodesmart", "rev-parse", "HEAD").stdout.strip()
        marker = self.root / "etc/bluenode/remote-admin.intent"
        credentials = self.root / "etc/bluenode/remote-admin.json"
        original_credentials = credentials.read_bytes()
        original_marker = marker.read_bytes()
        radio_calls = (self.root / "tmp/asterisk.calls").read_bytes()
        for present in (False, True):
            with self.subTest(previous_intent=present):
                if present:
                    marker.write_bytes(original_marker); marker.chmod(0o640)
                else:
                    marker.unlink(missing_ok=True)
                result = self.inside("bash", "/full-deploy.sh", target, "/remote.git", check=False)
                self.assertNotEqual(result.returncode, 0)
                self.assertIn("ROLLBACK PASS", result.stdout, result.stdout + result.stderr)
                self.assertEqual(marker.exists(), present)
                if present: self.assertEqual(marker.read_bytes(), original_marker)
                self.assertEqual(credentials.read_bytes(), original_credentials)
                self.assertEqual(self.inside("git", "-C", "/opt/nodesmart", "rev-parse", "HEAD").stdout.strip(), baseline)
                self.assertEqual((self.root / "tmp/asterisk.calls").read_bytes(), radio_calls)
        print("SIMULATED PASS supported full-deployment rollback: application, absent/existing intent, credentials, Asterisk untouched")



if __name__ == "__main__":
    if sys.platform != "linux" or os.geteuid() != 0:
        sys.exit("Run with sudo on Debian Linux; never run the installer directly as a fixture")
    if "--isolated" not in sys.argv:
        os.execvp("unshare", ["unshare", "--mount", "--net", "--pid", "--fork",
                             sys.executable, str(Path(__file__).resolve()), "--isolated"])
    os.umask(0o022)
    run("mount", "--make-rprivate", "/")
    sys.argv.remove("--isolated")
    unittest.main(verbosity=2)
