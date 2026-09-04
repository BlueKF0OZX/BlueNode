import json
import subprocess
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import Mock, patch

import recovery


class RecoveryTests(unittest.TestCase):
    def test_post_recovery_requires_fresh_stable_state(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            system = root / "system.json"
            intelligence = root / "intelligence.json"
            allstar = root / "allstar.json"
            system.write_text(json.dumps({
                "asterisk": "online",
                "health": {"asterisk": "normal"},
                "last_health_check": datetime.now(timezone.utc).isoformat(),
            }))
            intelligence.write_text("{}")
            allstar.write_text("{}")
            with patch.object(recovery, "STATE_FILE", system), \
                 patch.object(recovery, "INTELLIGENCE_FILE", intelligence), \
                 patch.object(recovery, "ALLSTAR_STATE_FILE", allstar), \
                 patch.object(recovery, "VERIFY_STABLE_CHECKS", 1), \
                 patch.object(recovery, "asterisk_online", return_value=True), \
                 patch.object(recovery, "allstar_reachable", return_value=True):
                passed, _ = recovery.verify_recovery(0, timeout=1)
        self.assertTrue(passed)

    def test_failed_verification_records_failure(self):
        state = {"asterisk": "offline"}
        completed = subprocess.CompletedProcess([], 0, "", "")
        with patch.object(recovery, "load_system_state", return_value=state), \
             patch.object(recovery.time, "sleep"), \
             patch.object(recovery, "asterisk_online", return_value=False), \
             patch.object(recovery.automation, "recovery_allowed", return_value=True), \
             patch.object(recovery.automation, "begin_recovery", return_value=1), \
             patch.object(recovery.automation, "finish_recovery") as finish, \
             patch.object(recovery.subprocess, "run", return_value=completed), \
             patch.object(recovery, "verify_recovery", return_value=(False, "not healthy")), \
             patch.object(recovery, "record_recovery_result") as record, \
             patch.object(recovery, "emit"):
            recovery.recover_asterisk()
        finish.assert_called_once()
        self.assertFalse(finish.call_args.args[0])
        self.assertEqual(record.call_args.args[0], "failed")

    def test_verified_success_is_not_restart_only(self):
        state = {"asterisk": "offline"}
        completed = subprocess.CompletedProcess([], 0, "", "")
        with patch.object(recovery, "load_system_state", return_value=state), \
             patch.object(recovery.time, "sleep"), \
             patch.object(recovery, "asterisk_online", return_value=False), \
             patch.object(recovery.automation, "recovery_allowed", return_value=True), \
             patch.object(recovery.automation, "begin_recovery", return_value=1), \
             patch.object(recovery.automation, "finish_recovery") as finish, \
             patch.object(recovery.subprocess, "run", return_value=completed), \
             patch.object(recovery, "verify_recovery", return_value=(True, "verified")), \
             patch.object(recovery, "record_recovery_result") as record, \
             patch.object(recovery, "emit"):
            recovery.recover_asterisk()
        finish.assert_called_once_with(True, "verified")
        record.assert_called_once_with("success", "verified")


if __name__ == "__main__":
    unittest.main()
