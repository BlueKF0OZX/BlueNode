import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import remote_admin


class Result:
    def __init__(self, code=0, out="active\n", err=""):
        self.returncode, self.stdout, self.stderr = code, out, err


class Clock:
    def __init__(self): self.now = 1000
    def __call__(self): return self.now


class RemoteAdminTests(unittest.TestCase):
    def test_persistent_lifetime_revocation_and_policy_changes(self):
        self.enable(session_seconds=2592000)
        _, _, token = self.admin.login('operator', 'correct horse battery staple', 'fixture')
        self.clock.now += 2591999
        self.assertIsNotNone(self.admin.authenticate(token))
        self.clock.now += 1
        self.assertIsNone(self.admin.authenticate(token))
        for key, value in [('password_hash', 'changed'), ('session_secret', 'rotated'),
                           ('permissions', ['soft_radio_rx']), ('session_seconds', 600)]:
            self.enable(session_seconds=2592000)
            _, _, token = self.admin.login('operator', 'correct horse battery staple', 'fixture')
            config = json.loads(self.config.read_text())
            config[key] = value
            self.config.write_text(json.dumps(config))
            self.assertIsNone(self.admin.authenticate(token), key)
        self.enable(session_seconds=2592000)
        _, _, token = self.admin.login('operator', 'correct horse battery staple', 'fixture')
        self.assertIsNone(remote_admin.RemoteAdmin().authenticate(token), 'restart invalidates sessions')
        self.admin.logout(token)
        self.assertIsNone(self.admin.authenticate(token))

    def test_long_sessions_require_secure_cookie_and_bounded_lifetime(self):
        self.enable(session_seconds=2592001)
        self.assertFalse(remote_admin._safe_config()['enabled'])
        self.enable(session_seconds=2592000)
        config = json.loads(self.config.read_text())
        config['secure_cookie'] = False
        self.config.write_text(json.dumps(config))
        self.assertEqual(remote_admin._safe_config()['state'], 'CONFIG_ERROR')

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.config = self.root / "remote-admin.json"
        self.audit = self.root / "admin-audit.jsonl"
        self.clock = Clock()
        self.commands = []
        def runner(command, **_kwargs):
            self.commands.append(command)
            if command[:2] == ["git", "-C"]: return Result(0, "a" * 40 + "\n")
            if command[:2] == ["sudo", "-n"] and "core show uptime seconds" in command:
                return Result(0, "System uptime: 10\n")
            return Result()
        self.patches = [patch.object(remote_admin, "CONFIG_OWNER_UID", getattr(os, "geteuid", lambda: 0)()), patch.object(remote_admin, "CONFIG_FILE", self.config),
                        patch.object(remote_admin, "AUDIT_FILE", self.audit),
                        patch.object(remote_admin, "APP_ROOT", self.root)]
        for item in self.patches: item.start()
        self.admin = remote_admin.RemoteAdmin(clock=self.clock, runner=runner)

    def tearDown(self):
        for item in reversed(self.patches): item.stop()
        self.temp.cleanup()

    def enable(self, attempts=5, session_seconds=300):
        salt, digest = remote_admin.hash_password("correct horse battery staple", iterations=200000)
        self.config.write_text(json.dumps({"enabled": True, "username": "operator",
            "password_salt": salt, "password_hash": digest, "password_iterations": 200000,
            "session_secret": "ab" * 32, "session_seconds": session_seconds,
            "secure_cookie": True, "max_login_attempts": attempts,
            "login_window_seconds": 60}), encoding="utf-8")
        os.chmod(self.config, 0o640)
        self.config.with_suffix(".intent").write_text(remote_admin.INTENT_CONTENT)
        self.config.with_suffix(".intent").chmod(0o640)

    def test_disabled_and_rejected_config_are_distinct(self):
        self.assertEqual(self.admin.public_state()["state"], "DISABLED")
        self.config.write_text("not json", encoding="utf-8"); os.chmod(self.config, 0o640)
        self.assertEqual(self.admin.public_state()["state"], "CONFIG_ERROR")
        self.assertEqual(self.admin.login("operator", "anything", "peer")[0], 503)
        self.enable()
        data = json.loads(self.config.read_text(encoding="utf-8"))
        data["permissions"] = ["arbitrary_shell"]
        self.config.write_text(json.dumps(data), encoding="utf-8")
        self.assertFalse(self.admin.public_state()["enabled"])

    def test_valid_invalid_authentication_csrf_logout(self):
        self.enable()
        self.assertEqual(self.admin.login("operator", "wrong", "peer")[0], 401)
        status, body, token = self.admin.login("operator", "correct horse battery staple", "peer")
        self.assertEqual(status, 200); self.assertTrue(token)
        self.assertTrue(self.admin.csrf_valid(token, body["csrf_token"]))
        self.assertFalse(self.admin.csrf_valid(token, "wrong"))
        self.admin.logout(token); self.assertIsNone(self.admin.authenticate(token))

    def test_interactive_credentials_accept_terminal_cr_and_match_confirmation(self):
        username, secret = remote_admin.validate_new_credentials(
            "operator", "fixture passphrase value\r", "fixture passphrase value")
        self.assertEqual(username, "operator")
        self.assertEqual(secret, "fixture passphrase value")
        with self.assertRaisesRegex(ValueError, "confirmation does not match"):
            remote_admin.validate_new_credentials(
                "operator", "fixture passphrase value", "different fixture value")
        with self.assertRaisesRegex(ValueError, "at least 14"):
            remote_admin.validate_new_credentials("operator", "too short", "too short")

    def test_rate_limit_session_expiration_and_permissions(self):
        self.enable(attempts=2)
        self.admin.login("operator", "bad", "peer"); self.admin.login("operator", "bad", "peer")
        self.assertEqual(self.admin.login("operator", "correct horse battery staple", "peer")[0], 429)
        self.clock.now += 61
        status, _, token = self.admin.login("operator", "correct horse battery staple", "peer")
        self.assertEqual(status, 200); self.clock.now += 301
        self.assertIsNone(self.admin.authenticate(token))
        if os.name == "posix":
            os.chmod(self.config, 0o644)
            self.assertFalse(self.admin.public_state()["enabled"])

    def test_allowlist_verification_failure_and_injection_rejection(self):
        self.assertEqual(self.admin.action("restart-asterisk", {"action":"restart-asterisk"})[0], 400)
        status, body = self.admin.action("restart-asterisk", {"action":"restart-asterisk",
                                                               "confirmation":"RESTART ASTERISK"})
        self.assertEqual(status, 200); self.assertTrue(body["ok"])
        self.assertIn(["sudo", "-n", "systemctl", "restart", "asterisk"], self.commands)
        for action in ("shell", "restart-unit", "../../etc/passwd", "asterisk -rx help"):
            self.assertEqual(self.admin.action(action, {"action": action})[0], 403)
        self.assertEqual(self.admin.action("restart-monitor",
            {"action":"restart-monitor", "unit":"ssh.service"})[0], 400)
        self.assertEqual(self.admin.logs("../../etc/passwd", 10)[0], 400)
        self.assertEqual(self.admin.logs("bluenode", "10;id")[0], 400)
        failed = remote_admin.RemoteAdmin(clock=self.clock,
            runner=lambda _command, **_kwargs: Result(1, "", "failed"))
        self.assertEqual(failed.action("restart-monitor", {"action":"restart-monitor"})[0], 500)

    def test_constrained_logs_status_and_audit(self):
        status, body = self.admin.logs("asterisk", 20)
        self.assertEqual(status, 200); self.assertEqual(body["source"], "asterisk")
        self.assertEqual(self.commands[-1][-2:], ["-u", "asterisk.service"])
        self.assertEqual(self.admin.status()["version"]["commit"], "a" * 40)
        records = [json.loads(line) for line in self.audit.read_text().splitlines()]
        self.assertEqual(set(records[-1]), {"timestamp", "action", "outcome"})
        self.assertNotIn("password", self.audit.read_text().lower())


if __name__ == "__main__": unittest.main()
