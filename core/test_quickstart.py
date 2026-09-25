"""Guided setup validation; no privileged commands or live radio operations."""
import importlib.util
import json
from pathlib import Path
import socket
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('quickstart', ROOT / 'install/quickstart.py')
setup = importlib.util.module_from_spec(spec)
spec.loader.exec_module(setup)


class QuickstartTests(unittest.TestCase):
    def test_includes_templates_and_callsign(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            (root / 'rpt.conf').write_text('[nodes]\n23456 = remote\n[11111](!)\n#include "local.conf"\n#exec touch /never\n')
            (root / 'local.conf').write_text('[23456](node-main)\nidrecording = |iW1AW\n#include "rpt.conf"\n[34567]\n')
            self.assertEqual(setup.discover_nodes(root / 'rpt.conf'), {'23456': 'W1AW', '34567': ''})

    def test_include_escape_rejected(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            (root / 'inner').mkdir()
            (root / 'outer.conf').write_text('[23456]\n')
            (root / 'inner/rpt.conf').write_text('#include "../outer.conf"\n')
            with self.assertRaises(ValueError):
                setup.discover_nodes(root / 'inner/rpt.conf')

    def test_choices_are_restricted_and_defaults_preserved(self):
        example = json.loads((ROOT / 'config/nodesmart.example.json').read_text())
        before = json.dumps(example)
        config = setup.build_config(example, '23456', 'W1AW', '127.0.0.1', 8080, {'23456': ''}, [])
        self.assertEqual(config['node'], '23456')
        self.assertEqual(config['friendly_nodes'], {})
        self.assertFalse(config['recovery']['asterisk_enabled'])
        self.assertEqual(json.dumps(example), before)
        for node, call, host, port in [('99999','W1AW','127.0.0.1',8080),
                                      ('23456','bad;command','127.0.0.1',8080),
                                      ('23456','N0CALL','127.0.0.1',8080),
                                      ('23456','W1AW','0.0.0.0',8080),
                                      ('23456','W1AW','127.0.0.1',80),
                                      ('23456','W1AW','127.0.0.1',True)]:
            with self.assertRaises(ValueError):
                setup.build_config(example,node,call,host,port,{'23456':''},[])

    def test_only_rfc1918_for_lan(self):
        for address in ['10.0.1.2','172.16.1.2','192.168.1.2']:
            self.assertTrue(setup.trusted_address(address))
        for address in ['0.0.0.0','127.0.0.1','100.64.1.2','8.8.8.8','169.254.1.2','::1','bad']:
            self.assertFalse(setup.trusted_address(address))

    def test_occupied_port(self):
        with socket.socket() as busy:
            busy.bind(('127.0.0.1',0))
            busy.listen()
            with self.assertRaises(ValueError):
                setup.probe_port('127.0.0.1', busy.getsockname()[1])

    def test_existing_path_blocks_before_service_queries(self):
        with tempfile.TemporaryDirectory() as temp, patch.object(setup, 'run') as run:
            path = Path(temp) / 'existing'
            path.write_text('operator data')
            with patch.object(setup, 'MANAGED', [path]), self.assertRaises(ValueError):
                setup.fresh_guard()
            run.assert_not_called()
            self.assertEqual(path.read_text(), 'operator data')

    def test_lan_requires_explicit_confirmation(self):
        with patch('builtins.input', side_effect=['23456','W1AW','192.168.1.2','no']):
            with self.assertRaises(ValueError):
                setup.choose_config({'23456':''}, ['192.168.1.2'])

    def test_incomplete_backup_refused_before_removal(self):
        with tempfile.TemporaryDirectory() as temp, patch.object(setup, 'private_directory'):
            target = Path(temp) / 'operator-file'
            target.write_text('keep')
            backup = Path(temp) / 'backup'
            backup.mkdir()
            (backup/'manifest.json').write_text(json.dumps({'paths':[str(target)],'present':[0]}))
            with patch.object(setup, 'UPDATE_PATHS',[target]), self.assertRaises(ValueError):
                setup.restore_snapshot(backup)
            self.assertEqual(target.read_text(),'keep')

    @unittest.skipUnless(sys.platform == 'linux', 'cp -a ownership-preserving transaction is Linux-only')
    def test_failed_update_restores_code_settings_and_history(self):
        with tempfile.TemporaryDirectory() as temp:
            base = Path(temp)
            app = base/'app'; app.mkdir()
            source = base/'source'; source.mkdir()
            config = app/'config.json'; config.write_text('{"recovery":{"asterisk_enabled":false}}')
            (app/'history').write_text('old history')
            (app/'code').write_text('old code')
            backups = base/'backups'
            original_run = subprocess.run
            def command(*args, **kwargs):
                if args[0]=='cp':
                    result = original_run(args,check=True,capture_output=True,text=True)
                    return result.stdout
                if args[1]=='is-enabled': return 'enabled'
                if 'LoadState' in args: return 'not-found'
                if 'User' in args: return 'operator'
                return ''
            def installer(*args, **kwargs):
                (app/'code').write_text('broken new code')
                (app/'history').write_text('changed history')
                config.write_text('changed settings')
                return subprocess.CompletedProcess(args,99)
            with patch.multiple(setup, ROOT=app, CONFIG=config, SOURCE=source,
                                BACKUP_ROOT=backups, UPDATE_PATHS=[app]), \
                 patch.object(setup,'run',side_effect=command), \
                 patch.object(setup.subprocess,'run',side_effect=installer), \
                 patch.object(setup,'verify'), patch.object(setup,'radio_identity',return_value='same'), \
                 patch.object(setup,'radio_files',return_value={}), \
                 patch.object(setup,'private_directory',side_effect=lambda p:p.mkdir(mode=0o700,parents=True,exist_ok=True)):
                with self.assertRaises(RuntimeError):
                    setup.update({'recovery':{'asterisk_enabled':False}})
            self.assertEqual((app/'code').read_text(),'old code')
            self.assertEqual((app/'history').read_text(),'old history')
            self.assertEqual(json.loads(config.read_text()),{'recovery':{'asterisk_enabled':False}})


if __name__ == '__main__':
    unittest.main()
