import json
import subprocess
import tempfile
import time
import unittest
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import Mock, patch

import recovery


class RecoveryTests(unittest.TestCase):
    def setUp(self):
        enabled = patch.object(recovery, "ASTERISK_RECOVERY_ENABLED", True)
        enabled.start()
        self.addCleanup(enabled.stop)
        service = patch.object(recovery.asterisk_observation, "service_evidence", side_effect=lambda: {
            "status": "offline", "observed_at": time.time(), "main_pid": 0,
            "active_state": "inactive", "sub_state": "dead", "load_state": "loaded"})
        service.start(); self.addCleanup(service.stop)

    def test_concurrent_start_is_not_restarted_or_disconnected(self):
        # Model systemd's start-vs-restart semantics at the execution boundary,
        # after every BlueNode probe has reported a stopped service.
        instance = {'pid': 0, 'links': []}
        def execute(command, **kwargs):
            instance.update(pid=321, links=['50241'])  # Independent concurrent start.
            if 'restart' in command:
                instance.update(pid=999, links=[])
            self.assertEqual(command, ['sudo', '-n', '/usr/bin/systemctl',
                                       '--job-mode=fail', 'start', 'asterisk'])
            return subprocess.CompletedProcess(command, 0, '', '')
        with patch.object(recovery, 'load_system_state', return_value={'asterisk': 'offline'}), \
             patch.object(recovery.time, 'sleep'), \
             patch.object(recovery, 'asterisk_online', return_value=False), \
             patch.object(recovery.automation, 'recovery_allowed', return_value=True), \
             patch.object(recovery.automation, 'begin_recovery', return_value=1), \
             patch.object(recovery.automation, 'finish_recovery'), \
             patch.object(recovery.subprocess, 'run', side_effect=execute) as command, \
             patch.object(recovery, 'verify_recovery', return_value=(True, 'verified')), \
             patch.object(recovery, 'record_recovery_result'), patch.object(recovery, 'emit'):
            recovery.recover_asterisk()
        command.assert_called_once()
        self.assertEqual(instance, {'pid': 321, 'links': ['50241']})

    def test_start_rejection_never_falls_back_to_restart(self):
        for failure in (subprocess.CompletedProcess([], 1, '', 'conflicting job or sudo denial'),
                        subprocess.TimeoutExpired('fixture', 20)):
            with self.subTest(failure=type(failure).__name__), \
                 patch.object(recovery, 'load_system_state', return_value={'asterisk': 'offline'}), \
                 patch.object(recovery.time, 'sleep'), \
                 patch.object(recovery, 'asterisk_online', return_value=False), \
                 patch.object(recovery.automation, 'recovery_allowed', return_value=True), \
                 patch.object(recovery.automation, 'begin_recovery', return_value=1), \
                 patch.object(recovery.automation, 'finish_recovery') as finish, \
                 patch.object(recovery.subprocess, 'run') as command, \
                 patch.object(recovery, 'verify_recovery') as verify, \
                 patch.object(recovery, 'record_recovery_result'), patch.object(recovery, 'emit'):
                if isinstance(failure, Exception): command.side_effect = failure
                else: command.return_value = failure
                recovery.recover_asterisk()
                command.assert_called_once()
                self.assertIn('start', command.call_args.args[0])
                self.assertNotIn('restart', command.call_args.args[0])
                self.assertFalse(finish.call_args.args[0])
                verify.assert_not_called()

    def test_installer_grants_only_exact_recovery_start(self):
        template = (Path(__file__).resolve().parents[1] / 'install/nodesmart.sudoers.example').read_text()
        rules = [line for line in template.splitlines() if ' start ' in line]
        self.assertEqual(rules, ['NODESMART_USER ALL=(root) NOPASSWD: /usr/bin/systemctl --job-mode=fail start asterisk'])

    def test_post_recovery_requires_fresh_stable_state(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            system = root / "system.json"
            intelligence = root / "intelligence.json"
            allstar = root / "allstar.json"
            system.write_text(json.dumps({
                "asterisk": "online",
                "asterisk_evidence": {"service": {"status": "online", "observed_at": time.time()},
                                      "query": {"status": "available"}, "node": {"status": "available"}},
                "health": {"asterisk": "normal"},
                "last_health_check": datetime.now(timezone.utc).isoformat(),
            }))
            intelligence.write_text("{}")
            allstar.write_text("{}")
            with patch.object(recovery, "STATE_FILE", system), \
                 patch.object(recovery, "INTELLIGENCE_FILE", intelligence), \
                 patch.object(recovery, "ALLSTAR_STATE_FILE", allstar), \
                 patch.object(recovery, "VERIFY_STABLE_CHECKS", 1), \
                 patch.object(recovery.asterisk_observation, "service_evidence", side_effect=lambda: {
                     "status": "online", "observed_at": time.time(), "main_pid": 123}), \
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
