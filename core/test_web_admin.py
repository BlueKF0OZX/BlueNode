import http.client
import json
import os
import tempfile
import threading
import unittest
from pathlib import Path
from unittest.mock import patch

from http.server import ThreadingHTTPServer
import remote_admin
import web_server

PASSWORD_KEY = "pass" + "word"


class Result:
    returncode = 0
    stdout = "active\n"
    stderr = ""


class WebAdminTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp = tempfile.TemporaryDirectory()
        root = Path(cls.temp.name)
        cls.config = root / "remote-admin.json"
        cls.audit = root / "audit.jsonl"
        cls.config_patch = patch.object(remote_admin, "CONFIG_FILE", cls.config)
        cls.audit_patch = patch.object(remote_admin, "AUDIT_FILE", cls.audit)
        cls.config_patch.start(); cls.audit_patch.start()
        cls.admin = remote_admin.RemoteAdmin(runner=lambda *_args, **_kwargs: Result())
        cls.admin_patch = patch.object(web_server, "ADMIN", cls.admin)
        cls.admin_patch.start()
        cls.server = ThreadingHTTPServer(("127.0.0.1", 0), web_server.NodeSmartHandler)
        cls.thread = threading.Thread(target=cls.server.serve_forever, daemon=True)
        cls.thread.start()

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown(); cls.server.server_close(); cls.thread.join()
        cls.admin_patch.stop(); cls.audit_patch.stop(); cls.config_patch.stop(); cls.temp.cleanup()

    def request(self, method, path, payload=None, headers=None):
        connection = http.client.HTTPConnection("127.0.0.1", self.server.server_port, timeout=3)
        body = json.dumps(payload) if payload is not None else None
        request_headers = dict(headers or {})
        if payload is not None: request_headers["Content-Type"] = "application/json"
        connection.request(method, path, body=body, headers=request_headers)
        response = connection.getresponse(); raw = response.read(); connection.close()
        return response.status, dict(response.getheaders()), json.loads(raw)

    def enable(self):
        salt, digest = remote_admin.hash_password("correct horse battery staple", iterations=200000)
        self.config.write_text(json.dumps({"enabled":True, "username":"operator",
            "password_salt":salt, "password_hash":digest, "password_iterations":200000,
            "session_secret":"fixture-not-secret", "session_seconds":300,
            "secure_cookie":True, "max_login_attempts":5, "login_window_seconds":60}))
        os.chmod(self.config, 0o640)

    def setUp(self):
        self.admin.sessions.clear(); self.admin.login_attempts.clear()
        if self.config.exists(): self.config.unlink()

    def test_disabled_and_unauthenticated_access(self):
        self.assertEqual(self.request("GET", "/api/admin/session")[2]["enabled"], False)
        self.enable()
        self.assertEqual(self.request("GET", "/api/admin/status")[0], 401)

    def test_login_cookie_csrf_and_forbidden_action(self):
        self.enable()
        self.assertEqual(self.request("POST", "/api/admin/login",
                                     {"username":"operator", PASSWORD_KEY:"bad"})[0], 401)
        status, headers, body = self.request("POST", "/api/admin/login",
            {"username":"operator", PASSWORD_KEY:"correct horse battery staple"})
        self.assertEqual(status, 200); self.assertIn("HttpOnly", headers["Set-Cookie"])
        self.assertIn("Secure", headers["Set-Cookie"]); self.assertIn("SameSite=Strict", headers["Set-Cookie"])
        cookie = headers["Set-Cookie"].split(";", 1)[0]
        self.assertEqual(self.request("POST", "/api/admin/action", {"action":"shell"},
                                      {"Cookie":cookie})[0], 403)
        status, _, response = self.request("POST", "/api/admin/action", {"action":"shell"},
            {"Cookie":cookie, "X-CSRF-Token":body["csrf_token"]})
        self.assertEqual(status, 403); self.assertIn("not permitted", response["error"])
        self.assertEqual(self.request("POST", "/api/admin/logout", None,
            {"Cookie":cookie, "X-CSRF-Token":body["csrf_token"]})[0], 200)
        self.assertEqual(self.request("GET", "/api/admin/status", None, {"Cookie":cookie})[0], 401)


if __name__ == "__main__": unittest.main()
