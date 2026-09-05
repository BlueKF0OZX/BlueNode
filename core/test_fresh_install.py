"""First-run and privileged-boundary regressions using only public fixtures."""
import http.client
import importlib.machinery
import importlib.util
import json
from pathlib import Path
import tempfile
import threading
import unittest
from unittest.mock import patch
from http.server import ThreadingHTTPServer

import automation
import emergency_mode
import node_behavior
import radio_activity
import recovery
import remote_admin
import connectivity
import web_server

ROOT = Path(__file__).resolve().parents[1]
def load_source(name, path):
    loader = importlib.machinery.SourceFileLoader(name, str(path))
    spec = importlib.util.spec_from_loader(name, loader)
    module = importlib.util.module_from_spec(spec)
    loader.exec_module(module)
    return module


broker = load_source("asterisk_broker", ROOT / "install/helpers/bluenode-asterisk")
validator = load_source("install_validator", ROOT / "install/validate-config.py")


class FreshInstallTests(unittest.TestCase):
    def test_broker_only_accepts_complete_fixed_commands(self):
        for command in ("core show version", "core show uptime seconds",
                        "module show like chan_iax2", "rpt show registrations",
                        "rpt show variables 23456", "rpt lstats 23456",
                        "rpt fun 23456 *323457", "rpt fun 23456 *123457"):
            self.assertTrue(broker.allowed(["-rx", command]), command)
        for command in ("!id", "core stop now", "core restart now", "rpt fun 23456 *99",
                        "rpt fun 23456 *323457\ncore stop now", "rpt fun 23456 *323457;!id",
                        "rpt fun 23456 *3", "rpt show variables １２３", "module load evil",
                        "channel originate Local/test application Rpt 23456"):
            self.assertFalse(broker.allowed(["-rx", command]), command)
        self.assertFalse(broker.allowed(["-rx", "core show version", "-C", "/tmp/evil"]))
        self.assertFalse(broker.allowed([]))

    def test_onboarding_rejects_defaults_and_invalid_types(self):
        config = json.loads((ROOT / "config/nodesmart.example.json").read_text())
        with self.assertRaises(ValueError):
            validator.validate(config)
        config.update(node="23456", callsign="W1AW")
        validator.validate(config)
        for section, value in (("node", "23456\n!id"), ("friendly_nodes", []),
                               ("web", {"port": 80}), ("recovery", {"asterisk_enabled": "false"})):
            with self.subTest(section=section), self.assertRaises((ValueError, TypeError)):
                validator.validate(dict(config, **{section: value}))

    def test_disabled_recovery_never_invokes_asterisk(self):
        with patch.object(recovery, "ASTERISK_RECOVERY_ENABLED", False), \
             patch.object(recovery.subprocess, "run") as command:
            recovery.recover_asterisk()
        command.assert_not_called()
        with patch.object(automation, "RECOVERY_ENABLED", False):
            self.assertFalse(automation.public_state({})["automation_armed"])

    def test_empty_telemetry_is_unavailable(self):
        with tempfile.TemporaryDirectory() as directory:
            missing = Path(directory) / "missing.json"
            for module in (connectivity, radio_activity, node_behavior):
                with patch.object(module, "STATE_FILE", missing):
                    state = module.public_state()
                    self.assertTrue(state.get("stale") or state.get("available") is False
                                    or state.get("diagnosis") == "unavailable", state)
            with patch.object(recovery, "RECOVERY_STATE_FILE", missing):
                self.assertEqual(recovery.load_recovery_state(), {})
            with patch.object(emergency_mode, "STATE_FILE", missing):
                self.assertFalse(emergency_mode.public_state()["active"])
            with patch.object(remote_admin, "CONFIG_FILE", missing):
                self.assertFalse(remote_admin._safe_config()["enabled"])

    def test_web_load_without_any_state_or_history(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "web").mkdir()
            (root / "web/index.html").write_bytes((ROOT / "web/index.html").read_bytes())
            with patch.object(web_server, "ROOT", root), \
                 patch.object(remote_admin, "CONFIG_FILE", root / "absent-admin.json"), \
                 patch.object(emergency_mode, "STATE_FILE", root / "absent-emergency.json"):
                server = ThreadingHTTPServer(("127.0.0.1", 0), web_server.NodeSmartHandler)
                thread = threading.Thread(target=server.serve_forever, daemon=True)
                thread.start()
                try:
                    def get(path):
                        connection = http.client.HTTPConnection("127.0.0.1", server.server_port, timeout=3)
                        connection.request("GET", path)
                        response = connection.getresponse()
                        body = response.read()
                        connection.close()
                        return response.status, body
                    self.assertEqual(get("/web/")[0], 200)
                    for path in ("system", "intelligence", "recovery", "connectivity",
                                 "automation", "radio_activity"):
                        self.assertEqual(get("/state/" + path + ".json")[0], 404)
                    self.assertEqual(get("/logs/events.log")[0], 404)
                    self.assertEqual(get("/events/allstar_state.json")[0], 404)
                    self.assertFalse(json.loads(get("/api/admin/session")[1])["enabled"])
                    self.assertFalse(json.loads(get("/api/emergency-mode")[1])["active"])
                    self.assertEqual(get("/config/nodesmart.json")[0], 404)
                finally:
                    server.shutdown()
                    server.server_close()
                    thread.join()


if __name__ == "__main__":
    unittest.main()
