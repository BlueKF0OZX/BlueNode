import ast
import copy
import hashlib
import importlib.util
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import skywarn_snapshot_exporter as exporter
import weather_alerts as weather


def alert(end='2030-01-01T00:00:00Z', description='Example weather description'):
    return {'county_code': 'XXC001', 'severity': 4, 'description': description, 'end_time_utc': end}


class WeatherTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.directory = Path(self.temp.name)
        self.path = self.directory / 'bluenode-weather.json'

    def tearDown(self):
        self.temp.cleanup()

    def collect(self, alerts, successes=1, counties=None):
        def operation(_):
            for _ in range(successes): exporter.zone_success()
            return alerts
        with patch.object(exporter.time, 'time', return_value=1800000000):
            self.assertIs(exporter.collect(operation, counties or ['XXC001'], {}, self.directory), alerts)
        return json.loads(self.path.read_text())

    def test_current_zero_one_multiple_and_removal(self):
        for alerts, count in [({}, 0), ({'Tornado Warning': [alert()]}, 1),
                              ({'Tornado Warning': [alert()], 'Flash Flood Warning': [alert()]}, 2), ({}, 0)]:
            state = weather.normalize(self.collect(alerts), 'enabled', 1800000001)
            self.assertEqual(state['status'], 'current')
            self.assertEqual(len(state['alerts']), count)

    def test_changed_details_without_event_or_county_change(self):
        self.collect({'Tornado Warning': [alert()]})
        state = self.collect({'Tornado Warning': [alert('2031-01-01T00:00:00Z', 'Updated description')]})
        self.assertEqual(state['alerts'][0][1][0]['description'], 'Updated description')
        self.assertEqual(state['alerts'][0][1][0]['end_time_utc'], '2031-01-01T00:00:00Z')

    def test_failure_partial_and_exception_never_claim_current(self):
        self.collect({'Tornado Warning': [alert()]})
        for successes, status in [(0, 'failure'), (1, 'partial')]:
            snapshot = self.collect({'Tornado Warning': [alert()]}, successes, ['XXC001', 'XXC002'])
            self.assertEqual(snapshot['collection_status'], status)
            self.assertEqual(snapshot['last_success'], 1800000000)
            state = weather.normalize(snapshot, 'enabled', 1800000001)
            self.assertEqual(state['status'], 'unavailable'); self.assertEqual(state['alerts'], [])
        def failed(_): raise RuntimeError('upstream failure')
        with patch.object(exporter.time, 'time', return_value=1800000002), self.assertRaisesRegex(RuntimeError, 'upstream failure'):
            exporter.collect(failed, ['XXC001'], {}, self.directory)
        self.assertEqual(json.loads(self.path.read_text())['collection_status'], 'failure')

    def test_stale_expiration_disabled_and_invalid(self):
        snapshot = self.collect({'Tornado Warning': [alert()]})
        self.assertEqual(weather.normalize(snapshot, 'enabled', 1800000181)['status'], 'stale')
        self.assertEqual(weather.normalize(snapshot, 'disabled', 1800000001)['alerts'], [])
        expired = self.collect({'Tornado Warning': [alert('2020-01-01T00:00:00Z')]})
        self.assertEqual(weather.normalize(expired, 'enabled', 1800000001)['alerts'], [])
        for value in [None, [], {}, {'schema_version': 2}, dict(snapshot, last_success='bad'),
                      dict(snapshot, alerts=[['Bad', [{'severity': 9}]]]), dict(snapshot, observed_at=float('inf'))]:
            self.assertEqual(weather.normalize(value, 'enabled', 1800000001)['status'], 'unavailable')

    def test_missing_malformed_oversized_and_cached_reads(self):
        with patch.object(weather, 'SNAPSHOT_FILE', self.path):
            self.assertEqual(weather.public_state('enabled')['status'], 'unavailable')
            self.path.write_text('{')
            self.assertEqual(weather.public_state('enabled')['status'], 'unavailable')
            self.path.write_text('[' * 5000 + ']' * 5000)
            self.assertEqual(weather.public_state('enabled')['status'], 'unavailable')
            self.path.write_text(' ' * (weather.MAX_BYTES + 1))
            self.assertEqual(weather.public_state('enabled')['status'], 'unavailable')
            self.collect({})
            weather._cache = (None, None)
            with patch.object(weather.os, 'open', wraps=weather.os.open) as opened:
                self.assertEqual(weather.public_state('enabled', 1800000001)['status'], 'current')
                self.assertEqual(weather.public_state('enabled', 1800000181)['status'], 'stale')
                self.assertEqual(opened.call_count, 1)

    def test_atomic_failure_and_observer_failure_preserve_upstream(self):
        self.path.write_text('[]')
        self.collect({}); before = self.path.read_bytes()
        snapshot = json.loads(before); snapshot['last_attempt'] += 1
        with patch.object(exporter.os, 'replace', side_effect=OSError('fixture')):
            self.assertFalse(exporter.publish(self.directory, snapshot))
        self.assertEqual(self.path.read_bytes(), before)
        self.assertEqual(list(self.directory.glob('.bluenode-weather-*')), [])
        alerts = {'Tornado Warning': [alert()]}; original = copy.deepcopy(alerts)
        self.assertIs(exporter.collect(lambda _: alerts, ['XXC001'], {}, self.directory / 'missing'), alerts)
        self.assertEqual(alerts, original)

    def test_older_overlapping_run_cannot_overwrite_newer(self):
        snapshot = self.collect({}); before = self.path.read_bytes()
        snapshot['last_attempt'] -= 10
        self.assertFalse(exporter.publish(self.directory, snapshot))
        self.assertEqual(self.path.read_bytes(), before)

    def test_injection_not_reported_as_live_weather(self):
        exporter.collect(lambda _: {}, ['XXC001'], {'DEV': {'INJECT': True}}, self.directory)
        self.assertEqual(json.loads(self.path.read_text())['collection_status'], 'failure')

    def test_existing_county_names_are_exported_without_lookup(self):
        def operation(_):
            exporter.zone_success()
            return {'Tornado Warning': [alert()]}
        exporter.collect(operation, ['XXC001'], {}, self.directory, {'XXC001':'Example County'})
        snapshot = json.loads(self.path.read_text())
        state = weather.normalize(snapshot, 'enabled', snapshot['observed_at'])
        self.assertEqual(state['alerts'][0]['area'], 'Example County')


class PatchTests(unittest.TestCase):
    def test_guard_idempotency_and_behavior(self):
        file = Path(__file__).resolve().parents[1] / 'install/skywarn-snapshot.py'
        spec = importlib.util.spec_from_file_location('patch_weather', file)
        module = importlib.util.module_from_spec(spec); spec.loader.exec_module(module)
        source = '''def get_alerts(countyCodes):
    for county in countyCodes:
        try:
            pass
        except requests.exceptions.RequestException as e:
            break
    return {'Example': []}

def main():
    alerts = get_alerts(COUNTY_CODES)
    return alerts
'''
        supported = {n.name: module.fingerprint(n) for n in ast.parse(source).body}
        patched = module.patch_source(source, supported)
        self.assertEqual(module.patch_source(patched, supported), patched)
        with self.assertRaises(ValueError): module.patch_source(source.replace('pass', 'return None'), supported)
        with self.assertRaises(ValueError): module.patch_source(source)
        self.assertIn(module.NOTIFY, patched)
        # The optional helper's absence leaves the original operation and result intact.
        scope = {'COUNTY_CODES': ['XXC001'], 'config': {}, 'TMP_DIR': '.'}
        exec(patched, scope)
        self.assertEqual(scope['main'](), {'Example': []})
