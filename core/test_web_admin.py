import http.client
import json
import os
import socket
import tempfile
import threading
import unittest
from pathlib import Path
from unittest.mock import patch

from http.server import ThreadingHTTPServer
import remote_admin
import soft_radio
import web_server
import emergency_mode

PASSWORD_KEY = "pass" + "word"


class Result:
    returncode = 0
    stdout = "active\n"
    stderr = ""


class WebAdminTests(unittest.TestCase):
    def test_persistent_cookie_rotation_and_all_control_auth_guards(self):
        self.enable()
        config = json.loads(self.config.read_text())
        config['session_seconds'] = 2592000
        self.config.write_text(json.dumps(config))
        actions = ['node-connect', 'node-disconnect', 'dodropin-connect', 'dodropin-disconnect',
                   'skywarn-enable', 'skywarn-disable', 'emergency-enable', 'emergency-disable',
                   'maintenance-enable', 'maintenance-disable']
        for action in actions:
            self.assertEqual(self.request('POST', '/api/control/' + action, {})[0], 401)
        self.assertEqual(self.request('POST', '/api/admin/action', {'action':'refresh-diagnostics'})[0], 401)
        credentials = {'username':'operator', PASSWORD_KEY:'correct horse battery staple'}
        _, headers, login = self.request('POST', '/api/admin/login', credentials)
        for attribute in ['Max-Age=2592000', 'HttpOnly', 'Secure', 'SameSite=Strict']:
            self.assertIn(attribute, headers['Set-Cookie'])
        cookie = headers['Set-Cookie'].split(';', 1)[0]
        for action in actions:
            self.assertEqual(self.request('POST', '/api/control/' + action, {}, {'Cookie':cookie})[0], 403)
        self.assertTrue(self.request('GET', '/api/admin/session', headers={'Cookie':cookie})[2]['authenticated'])
        _, rotated, _ = self.request('POST', '/api/admin/login', credentials, {'Cookie':cookie})
        self.assertNotEqual(rotated['Set-Cookie'], headers['Set-Cookie'])
        self.assertFalse(self.request('GET', '/api/admin/session', headers={'Cookie':cookie})[2]['authenticated'])
        new_cookie = rotated['Set-Cookie'].split(';', 1)[0]
        now = self.admin.clock()
        with patch.object(self.admin, 'clock', return_value=now + 2592001):
            self.assertEqual(self.request('POST', '/api/control/node-connect', {'node':'12345'},
                                         {'Cookie':new_cookie, 'X-CSRF-Token':login['csrf_token']})[0], 401)

    @classmethod
    def setUpClass(cls):
        cls.temp = tempfile.TemporaryDirectory()
        root = Path(cls.temp.name)
        cls.config = root / "remote-admin.json"
        cls.audit = root / "audit.jsonl"
        cls.soft_config = root / "soft-radio.json"
        cls.config_patch = patch.object(remote_admin, "CONFIG_FILE", cls.config)
        cls.audit_patch = patch.object(remote_admin, "AUDIT_FILE", cls.audit)
        cls.owner_patch = patch.object(remote_admin, "CONFIG_OWNER_UID", getattr(os, "geteuid", lambda: 0)())
        cls.owner_patch.start()
        cls.config_patch.start(); cls.audit_patch.start()
        cls.soft_patch = patch.object(soft_radio, "CONFIG_FILE", cls.soft_config)
        cls.soft_patch.start()
        cls.emergency_file = root / "emergency_mode.json"
        cls.emergency_patch = patch.object(emergency_mode, "STATE_FILE", cls.emergency_file)
        cls.emergency_emit_patch = patch.object(emergency_mode, "emit")
        cls.emergency_patch.start(); cls.emergency_emit_patch.start()
        cls.admin = remote_admin.RemoteAdmin(runner=lambda *_args, **_kwargs: Result())
        cls.admin_patch = patch.object(web_server, "ADMIN", cls.admin)
        cls.admin_patch.start()
        cls.server = ThreadingHTTPServer(("127.0.0.1", 0), web_server.NodeSmartHandler)
        cls.thread = threading.Thread(target=cls.server.serve_forever, daemon=True)
        cls.thread.start()

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown(); cls.server.server_close(); cls.thread.join()
        cls.owner_patch.stop()
        cls.admin_patch.stop(); cls.emergency_emit_patch.stop(); cls.emergency_patch.stop(); cls.soft_patch.stop(); cls.audit_patch.stop(); cls.config_patch.stop(); cls.temp.cleanup()

    def request(self, method, path, payload=None, headers=None):
        connection = http.client.HTTPConnection("127.0.0.1", self.server.server_port, timeout=3)
        body = json.dumps(payload) if payload is not None else None
        request_headers = dict(headers or {})
        if payload is not None: request_headers["Content-Type"] = "application/json"
        connection.request(method, path, body=body, headers=request_headers)
        response = connection.getresponse(); raw = response.read(); connection.close()
        return response.status, dict(response.getheaders()), json.loads(raw)

    def enable(self, permissions=None):
        salt, digest = remote_admin.hash_password("correct horse battery staple", iterations=200000)
        self.config.write_text(json.dumps({"enabled":True, "username":"operator",
            "password_salt":salt, "password_hash":digest, "password_iterations":200000,
            "session_secret":"ab" * 32, "session_seconds":300,
            "secure_cookie":True, "max_login_attempts":5, "login_window_seconds":60}))
        data = json.loads(self.config.read_text())
        data["permissions"] = list(permissions or [])
        self.config.write_text(json.dumps(data))
        os.chmod(self.config, 0o640)
        self.config.with_suffix(".intent").write_text(remote_admin.INTENT_CONTENT)
        self.config.with_suffix(".intent").chmod(0o640)

    def setUp(self):
        self.admin.sessions.clear(); self.admin.login_attempts.clear()
        if self.config.exists(): self.config.unlink()
        self.config.with_suffix(".intent").unlink(missing_ok=True)
        if self.soft_config.exists(): self.soft_config.unlink()
        if self.emergency_file.exists(): self.emergency_file.unlink()
        soft_radio.SOFT_RADIO.tickets.clear()

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

    def test_emergency_mode_default_auth_csrf_validation_and_persistence(self):
        self.assertEqual(self.request("GET", "/api/emergency-mode")[2]["mode"], "normal")
        self.enable()
        self.assertEqual(self.request("POST", "/api/control/emergency-enable", {})[0], 401)
        status, headers, login = self.request("POST", "/api/admin/login",
            {"username":"operator", PASSWORD_KEY:"correct horse battery staple"})
        self.assertEqual(status, 200)
        cookie = headers["Set-Cookie"].split(";", 1)[0]
        self.assertEqual(self.request("POST", "/api/control/emergency-enable", {},
                                     {"Cookie":cookie})[0], 403)
        authorized = {"Cookie":cookie, "X-CSRF-Token":login["csrf_token"]}
        status, _, body = self.request("POST", "/api/control/emergency-enable", {}, authorized)
        self.assertEqual(status, 200)
        self.assertTrue(body["emergency_mode"]["active"])
        self.assertEqual(body["emergency_mode"]["activation_source"], "remote_admin")
        self.assertEqual(self.request("GET", "/api/emergency-mode")[2]["mode"], "emergency")
        self.assertEqual(self.request("POST", "/api/control/emergency-enable",
                                     {"reason":"injected"}, authorized)[0], 400)
        self.assertEqual(self.request("POST", "/api/control/emergency-invalid", {},
                                     authorized)[0], 403)
        status, _, body = self.request("POST", "/api/control/emergency-disable", {}, authorized)
        self.assertEqual(status, 200)
        self.assertEqual(body["emergency_mode"]["mode"], "normal")

    def test_soft_radio_ticket_requires_permission_and_is_one_time(self):
        self.enable(["soft_radio_rx"])
        self.soft_config.write_text(json.dumps({"enabled":True, "listen_host":"127.0.0.1",
            "listen_port":18767, "media_path":"/asterisk-media",
            "media_username":"fixture_user", "media_password":"fixture-value-not-secret-12345",
            "connection_name":"bluenode_soft_radio_rx", "local_node":"12345",
            "ticket_seconds":30, "buffer_frames":12, "start_channel":False}))
        os.chmod(self.soft_config, 0o640)
        status, headers, login = self.request("POST", "/api/admin/login",
            {"username":"operator", PASSWORD_KEY:"correct horse battery staple"})
        self.assertEqual(status, 200)
        cookie = headers["Set-Cookie"].split(";", 1)[0]
        request_headers = {"Cookie":cookie, "X-CSRF-Token":login["csrf_token"],
                           "Content-Type":"application/json"}
        status, _, body = self.request("POST", "/api/soft-radio/ticket", {}, request_headers)
        self.assertEqual(status, 200)
        token = cookie.split("=", 1)[1]
        self.assertTrue(soft_radio.SOFT_RADIO.consume_ticket(body["ticket"], token))
        self.assertFalse(soft_radio.SOFT_RADIO.consume_ticket(body["ticket"], token))

    def test_soft_radio_rejects_authenticated_session_without_permission(self):
        self.enable([])
        status, headers, login = self.request("POST", "/api/admin/login",
            {"username":"operator", PASSWORD_KEY:"correct horse battery staple"})
        self.assertEqual(status, 200)
        request_headers = {"Cookie":headers["Set-Cookie"].split(";", 1)[0],
                           "X-CSRF-Token":login["csrf_token"]}
        self.assertEqual(self.request("POST", "/api/soft-radio/ticket", {}, request_headers)[0], 403)

    def test_soft_radio_websocket_requires_same_origin_and_consumes_ticket(self):
        self.enable(["soft_radio_rx"])
        self.soft_config.write_text(json.dumps({"enabled":True, "listen_host":"127.0.0.1",
            "listen_port":18767, "media_path":"/asterisk-media",
            "media_username":"fixture_user", "media_password":"fixture-value-not-secret-12345",
            "connection_name":"bluenode_soft_radio_rx", "local_node":"12345",
            "ticket_seconds":30, "buffer_frames":12, "start_channel":False}))
        os.chmod(self.soft_config, 0o640)
        status, headers, login = self.request("POST", "/api/admin/login",
            {"username":"operator", PASSWORD_KEY:"correct horse battery staple"})
        self.assertEqual(status, 200)
        cookie = headers["Set-Cookie"].split(";", 1)[0]
        status, _, issued = self.request("POST", "/api/soft-radio/ticket", {},
            {"Cookie":cookie, "X-CSRF-Token":login["csrf_token"]})
        self.assertEqual(status, 200)
        stream = socket.create_connection(("127.0.0.1", self.server.server_port))
        request = ("GET /api/soft-radio/ws HTTP/1.1\r\nHost: example.test\r\n"
                   "Origin: https://example.test\r\nUpgrade: websocket\r\n"
                   "Connection: Upgrade\r\nSec-WebSocket-Version: 13\r\n"
                   "Sec-WebSocket-Key: MDEyMzQ1Njc4OWFiY2RlZg==\r\n"
                   f"Sec-WebSocket-Protocol: bluenode-rx, ticket.{issued['ticket']}\r\n"
                   f"Cookie: {cookie}\r\n\r\n")
        stream.sendall(request.encode("ascii"))
        self.assertIn(b"101 Switching Protocols", stream.recv(2048))
        stream.sendall(b"\x88\x80abcd")
        stream.close()
        reused = socket.create_connection(("127.0.0.1", self.server.server_port))
        reused.sendall(request.encode("ascii"))
        self.assertIn(b"403", reused.recv(2048))
        reused.close()


if __name__ == "__main__": unittest.main()
