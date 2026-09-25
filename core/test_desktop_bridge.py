"""No live node operations: desktop protocol boundaries and detached-job behavior."""
import base64
import importlib.util
import json
import os
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'install'))
spec = importlib.util.spec_from_file_location('desktop_bridge', ROOT / 'install/desktop_bridge.py')
bridge = importlib.util.module_from_spec(spec)
spec.loader.exec_module(bridge)
sys.path.pop(0)


class DesktopBridgeTests(unittest.TestCase):
    def test_request_and_job_boundaries(self):
        value = base64.b64encode(b'{"action":"probe"}').decode()
        self.assertEqual(bridge.decode(value), {'action': 'probe'})
        for value in ('!', 'x' * 8193, base64.b64encode(b'[]').decode()):
            with self.assertRaises(ValueError):
                bridge.decode(value)
        for value in ('../etc', '', None, 'A' * 32, 'a' * 33):
            with self.assertRaises(ValueError):
                bridge.job_path(value)

    def test_station_does_not_leak_optional_secrets(self):
        config = {'node': '23456', 'callsign': 'W1AW', 'web': {'host': '127.0.0.1', 'port': 8080},
                  'private': {'credential': 'not-for-client'}}
        self.assertNotIn('private', bridge.station(config))
        for host in ('0.0.0.0', '8.8.8.8', 'example.com', '127.0.0.1;id'):
            config['web']['host'] = host
            with self.assertRaises(ValueError):
                bridge.station(config)

    def test_confirmation_and_local_nodes_only(self):
        with patch.object(bridge.q, 'discover_nodes', return_value={'23456': 'W1AW'}), \
             patch.object(bridge.q, 'run', return_value='RPT_TEST=1') as run:
            for request in ({'confirmed': False}, {'confirmed': True, 'node': '23456;id'},
                            {'confirmed': True, 'node': '34567'}):
                with self.assertRaises(ValueError):
                    bridge.validated_config(request)
            run.assert_not_called()
            config = bridge.validated_config({'confirmed': True, 'node': '23456', 'callsign': 'w1aw'})
            self.assertEqual(config['web'], {'host': '127.0.0.1', 'port': 8080})
            self.assertFalse(config['recovery']['asterisk_enabled'])

    def test_running_job_resumes_before_inspecting_partial_install(self):
        with patch.object(bridge, 'active_job', return_value={'state': 'running', 'job': 'a' * 32}), \
             patch.object(bridge.q, 'preflight') as preflight:
            self.assertEqual(bridge.probe()['mode'], 'running')
            preflight.assert_not_called()

    def test_missing_job_does_not_create_directory(self):
        with tempfile.TemporaryDirectory() as temp, patch.object(bridge, 'JOBS', Path(temp)):
            with self.assertRaises(ValueError):
                bridge.status('b' * 32)
            self.assertEqual(list(Path(temp).iterdir()), [])

    @unittest.skipUnless(sys.platform == 'linux', 'Requires POSIX file locks')
    def test_lock_refuses_concurrent_install(self):
        with tempfile.TemporaryDirectory() as temp, patch.object(bridge, 'LOCK', str(Path(temp) / 'lock')):
            with bridge.lock():
                with self.assertRaises(ValueError):
                    with bridge.lock():
                        self.fail('Second installer entered lock')
            with bridge.lock():
                pass

    @unittest.skipUnless(sys.platform == 'linux', 'POSIX descriptor inheritance')
    def test_worker_writes_success_and_failure_without_credentials(self):
        with tempfile.TemporaryDirectory() as temp, patch.object(bridge, 'JOBS', Path(temp)), \
             patch.object(bridge.q, 'preflight'), patch.object(bridge.q, 'install') as install:
            job = Path(temp) / ('c' * 32)
            job.mkdir()
            config = {'node': '23456', 'callsign': 'W1AW', 'web': {'host': '127.0.0.1', 'port': 8080}}
            (job / 'config.json').write_text(json.dumps(config))
            for failure in (None, RuntimeError('simulated installer failure')):
                install.side_effect = failure
                fd = os.open(str(job / 'lock'), os.O_CREAT | os.O_RDWR, 0o600)
                bridge.worker('c' * 32, fd)
                result = json.loads((job / 'status.json').read_text())
                self.assertEqual(result['state'], 'failed' if failure else 'complete')
                with self.assertRaises(OSError):
                    os.fstat(fd)

    def test_payload_copies_only_release_directories(self):
        with tempfile.TemporaryDirectory() as temp:
            source, target = Path(temp) / 'source', Path(temp) / 'target'
            source.mkdir()
            for name in bridge.PAYLOAD:
                (source / name).mkdir()
                (source / name / 'example').write_text('public')
            (source / 'private').write_text('not-for-client')
            with patch.object(bridge.q, 'SOURCE', source):
                bridge.copy_source(target)
            self.assertEqual({p.name for p in target.iterdir()}, set(bridge.PAYLOAD))


if __name__ == '__main__':
    unittest.main()
