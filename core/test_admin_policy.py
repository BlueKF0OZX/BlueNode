"""Adversarial request-level policy tests. All effects are intercepted."""
import io
import json
import os
import tempfile
import unittest
from contextlib import ExitStack
from pathlib import Path
from unittest.mock import Mock, patch

import remote_admin as admin
import web_server as web


ROUTES = ('node-connect', 'node-disconnect', 'dodropin-connect', 'dodropin-disconnect',
          'skywarn-enable', 'skywarn-disable', 'emergency-enable', 'emergency-disable',
          'maintenance-enable', 'maintenance-disable')


class PolicyTests(unittest.TestCase):
    def setUp(self):
        self.stack = ExitStack()
        self.addCleanup(self.stack.close)
        root = Path(self.stack.enter_context(tempfile.TemporaryDirectory()))
        self.config = root / 'remote-admin.json'
        self.marker = self.config.with_suffix('.intent')
        self.stack.enter_context(patch.object(admin, 'CONFIG_FILE', self.config))
        self.stack.enter_context(patch.object(admin, 'CONFIG_OWNER_UID', getattr(os, 'geteuid', lambda: 0)()))
        self.auth = admin.RemoteAdmin()
        self.auth.audit = Mock()
        self.stack.enter_context(patch.object(web, 'ADMIN', self.auth))
        self.effects = [self.stack.enter_context(patch.object(obj, name)) for obj, name in (
            (web.subprocess, 'run'), (web, 'emit'), (web.automation, 'set_maintenance'),
            (web.emergency_mode, 'set_emergency'), (self.auth, 'action'))]
        self.stack.enter_context(patch.object(web, 'CONFIG', {'node': '12345'}))
        salt, digest = admin.hash_password('fixture password value', iterations=200000)
        self.valid = dict(enabled=True, username='operator', password_salt=salt,
                          password_hash=digest, session_secret='ab' * 32, password_iterations=200000)
        self.marker.write_text(admin.INTENT_CONTENT)
        self.marker.chmod(0o640)

    def write(self, data):
        self.config.write_text(json.dumps(data))
        self.config.chmod(0o640)

    def request(self, method, path, body=None, headers=None):
        handler = object.__new__(web.NodeSmartHandler)
        handler.path = path
        raw = json.dumps(body or {}).encode()
        handler.headers = {'Content-Length': str(len(raw)), 'Host': 'example.test',
                           'Origin': 'https://example.test', 'X-Forwarded-For': '127.0.0.1',
                           **(headers or {})}
        handler.client_address = ('untrusted-fixture-peer', 1234)
        handler.rfile = io.BytesIO(raw)
        output = []
        handler.send_json = lambda code, data: output.append((code, data))
        getattr(handler, 'do_' + method)()
        return output[0]

    def assert_locked(self, headers=None):
        self.auth.audit.reset_mock()
        self.assertEqual(self.request('GET', '/api/admin/session')[1]['state'], 'CONFIG_ERROR')
        for _ in range(2):
            for action in ROUTES:
                code, body = self.request('POST', '/api/control/' + action,
                                          {'node': '23456'} if action.startswith('node-') else {}, headers=headers)
                self.assertEqual(code, 503, action)
                self.assertEqual(body['state'], 'CONFIG_ERROR')
        for path in ('/api/admin/status', '/api/admin/logs'):
            self.assertEqual(self.request('GET', path)[0], 401)
        self.assertEqual(self.request('POST', '/api/admin/action', {'action': 'restart-asterisk'})[0], 401)
        self.assertEqual(self.request('POST', '/api/admin/login')[0], 503)
        for effect in self.effects:
            effect.assert_not_called()
        self.assertTrue(all(call.args[1] in ('config_error', 'rejected')
                            for call in self.auth.audit.call_args_list))

    def test_invalid_configuration_matrix_all_routes(self):
        cases = {'empty-object': {}, 'empty-array': [], 'partial': {'enabled': True}}
        for key in ('username', 'password_salt', 'password_hash', 'session_secret'):
            data = dict(self.valid); del data[key]
            cases['missing-' + key] = data
            cases['wrong-type-' + key] = dict(self.valid, **{key: []})
        for key, values in {
            'enabled': ['true', 1, None], 'secure_cookie': [False, None, 1, 'true'],
            'session_seconds': [0, 2592001, '300', True, float('inf'), float('nan'), []],
            'password_iterations': [199999, 5000001], 'max_login_attempts': [True, 21],
            'login_window_seconds': [29, 3601], 'permissions': ['shell', ['shell'], [{}]],
            'password_salt': ['zz' * 24, 'ab'], 'password_hash': ['zz' * 32, 'ab'],
            'session_secret': ['not-encoded', 'ab'], 'username': ['bad user', ''],
        }.items():
            for index, value in enumerate(values):
                cases[key + '-' + str(index)] = dict(self.valid, **{key: value})
        for name, data in cases.items():
            with self.subTest(case=name):
                self.write(data)
                self.assert_locked()
        for text in ('', '{', '[' * 1100 + ']' * 1100, ' ' * 16385):
            with self.subTest(raw_length=len(text)):
                self.config.write_text(text)
                self.assert_locked()

    def test_enabled_transitions_and_restart_keep_intent(self):
        for transition in ('missing', 'malformed', 'incomplete', 'unreadable'):
            with self.subTest(transition=transition):
                self.write(self.valid)
                self.assertEqual(admin._safe_config()['state'], 'ENABLED')
                _, _, token = self.auth.login('operator', 'fixture password value', 'fixture')
                if transition == 'missing': self.config.unlink()
                elif transition == 'malformed': self.config.write_text('{')
                elif transition == 'incomplete': self.write({'enabled': True})
                reader = admin._read_security_file
                def read(path):
                    if transition == 'unreadable' and path == self.config:
                        raise PermissionError('fixture')
                    return reader(path)
                with patch.object(admin, '_read_security_file', side_effect=read):
                    self.assert_locked(headers={'Cookie': 'bluenode_admin=' + token})
                    self.auth.sessions.clear()  # Simulated restart; intent remains on disk.
                    self.assert_locked()

    def test_unexpected_conversion_errors_are_controlled(self):
        self.write(self.valid)
        for error in (OverflowError, RecursionError, TypeError, ValueError, OSError):
            with self.subTest(error=error.__name__), patch.object(admin, '_read_security_file', side_effect=error):
                self.assert_locked()

    def test_intent_missing_or_corrupt_cannot_enable_auth(self):
        self.write(self.valid)
        self.marker.unlink()
        self.assert_locked()
        self.marker.write_text('invalid')
        self.assert_locked()

    def test_defaults_disabled_unknown_fields_and_valid_auth(self):
        self.marker.unlink()
        self.assertEqual(admin._safe_config()['state'], 'DISABLED')
        self.write({'enabled': False})
        self.assertEqual(admin._safe_config()['state'], 'DISABLED')
        self.effects[0].return_value.returncode = 0
        self.effects[0].return_value.stdout = ''
        self.assertEqual(self.request('POST', '/api/control/node-connect', {'node': '23456'})[0], 200)
        self.effects[0].assert_called_once()
        self.marker.write_text(admin.INTENT_CONTENT); self.marker.chmod(0o640)
        self.write(dict(self.valid, harmless={'future': True}, state='DISABLED'))
        self.assertEqual(admin._safe_config()['state'], 'ENABLED')
        self.assertEqual(self.request('POST', '/api/control/node-connect', {'node': '23456'})[0], 401)
        _, login, token = self.auth.login('operator', 'fixture password value', 'fixture')
        cookie = {'Cookie': 'bluenode_admin=' + token}
        for action in ROUTES:
            self.assertEqual(self.request('POST', '/api/control/' + action, headers=cookie)[0], 403)
        self.assertTrue(self.auth.csrf_valid(token, login['csrf_token']))

    @unittest.skipUnless(os.name == 'posix', 'POSIX file security is validated on Linux')
    def test_unsafe_file_directory_ownership_and_symlink(self):
        self.write(self.valid)
        for mode in (0o644, 0o660, 0o666):
            self.config.chmod(mode)
            self.assert_locked()
        self.config.chmod(0o640)
        with patch.object(admin, 'CONFIG_OWNER_UID', -1):
            self.assert_locked()
        self.config.parent.chmod(0o770)
        self.assert_locked()
        self.config.parent.chmod(0o700)
        target = self.config.with_suffix('.actual')
        self.config.rename(target); self.config.symlink_to(target)
        self.assert_locked()


if __name__ == '__main__':
    unittest.main()
