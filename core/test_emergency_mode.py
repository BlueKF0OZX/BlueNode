import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import emergency_mode


class EmergencyModeTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.state_file = Path(self.temp.name) / "emergency_mode.json"
        self.file_patch = patch.object(emergency_mode, "STATE_FILE", self.state_file)
        self.emit_patch = patch.object(emergency_mode, "emit")
        self.emit = self.emit_patch.start()
        self.file_patch.start()

    def tearDown(self):
        self.file_patch.stop()
        self.emit_patch.stop()
        self.temp.cleanup()

    def test_defaults_to_normal(self):
        self.assertEqual(emergency_mode.public_state(now=100), {
            "version": 1, "active": False, "mode": "normal",
            "activated_at": None, "activated_epoch": None,
            "activation_source": None, "last_transition_at": None,
            "elapsed_seconds": 0,
        })

    def test_enter_persist_restart_and_exit(self):
        active = emergency_mode.set_emergency(True, "remote_admin", now=1000)
        self.assertTrue(active["active"])
        self.assertEqual(active["activation_source"], "remote_admin")
        self.assertEqual(emergency_mode.public_state(now=1061)["elapsed_seconds"], 61)
        persisted = json.loads(self.state_file.read_text(encoding="utf-8"))
        self.assertEqual(persisted["mode"], "emergency")
        cleared = emergency_mode.set_emergency(False, "remote_admin", now=1100)
        self.assertEqual(cleared["mode"], "normal")
        self.assertEqual(cleared["elapsed_seconds"], 0)
        self.assertEqual(self.emit.call_count, 2)

    def test_duplicate_transition_does_not_spam_events(self):
        emergency_mode.set_emergency(True, now=1000)
        emergency_mode.set_emergency(True, now=1002)
        self.assertEqual(self.emit.call_count, 1)

    def test_malformed_state_fails_safe_to_normal(self):
        self.state_file.write_text('{"active":true,"mode":"emergency","activated_epoch":"bad"}')
        self.assertEqual(emergency_mode.public_state(now=100)["mode"], "normal")

    def test_atomic_state_has_no_temporary_residue(self):
        emergency_mode.set_emergency(True, now=1000)
        self.assertEqual(list(self.state_file.parent.glob("*.tmp")), [])


if __name__ == "__main__":
    unittest.main()
