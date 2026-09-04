import copy
import json
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import patch

import intelligence as intel

NOW = datetime.now(timezone.utc)
NORMAL = {
    'status': 'healthy', 'asterisk': 'online', 'internet': 'online',
    'health': {c: 'normal' for c in ('asterisk', 'internet', 'cpu', 'memory', 'disk')},
    'health_reasons': [], 'last_health_check': NOW.isoformat(),
}

def event(name, seconds):
    return {'event': name, 'timestamp': NOW + timedelta(seconds=seconds), 'message': ''}

class LifecycleTests(unittest.TestCase):
    def build(self, state, events, recovery=None):
        with patch.object(intel, 'load_events', return_value=events), \
             patch.object(intel, 'load_recovery_state', return_value=recovery or {}), \
             patch.object(intel, 'load_json', return_value={}), \
             patch.object(intel, 'save_intelligence'):
            return intel.build_intelligence(state)

    def test_online_closes_asterisk_and_preserves_history(self):
        records = intel.build_incident_records([event('ASTERISK.OFFLINE', -90),
                    event('RECOVERY.ASTERISK.FAILED', -60), event('ASTERISK.ONLINE', -30)])
        self.assertEqual(len(records), 1)
        self.assertTrue(records[0]['resolved'])
        self.assertEqual(records[0]['recovery_outcome'], 'failed')
        self.assertEqual(records[0]['duration_seconds'], 60)

    def test_duplicate_outage_is_one_incident(self):
        for component in ('ASTERISK', 'INTERNET'):
            records = intel.build_incident_records([event(component+'.OFFLINE', -90),
                       event(component+'.OFFLINE', -60), event(component+'.ONLINE', -30)])
            self.assertEqual(len(records), 1)
            self.assertTrue(records[0]['resolved'])

    def test_same_second_internet_recovery(self):
        records = intel.build_incident_records([event('INTERNET.OFFLINE', -30),
                                               event('INTERNET.ONLINE', -30)])
        self.assertTrue(records[0]['resolved'])

    def test_warning_recovers_without_losing_incident(self):
        events = [event('HEALTH.CPU.WARNING', -90), event('HEALTH.CPU.CRITICAL', -60),
                  event('HEALTH.CPU.NORMAL', -30)]
        result = self.build(NORMAL, events)
        self.assertEqual(result['level'], 'normal')
        self.assertFalse(result['recommendation']['action_required'])
        self.assertEqual(result['unresolved_issues'], [])
        self.assertEqual(result['incidents'][0]['highest_state'], 'critical')
        self.assertTrue(result['incidents'][0]['resolved'])

    def test_missing_closure_uses_newer_observation(self):
        result = self.build(NORMAL, [event('HEALTH.CPU.WARNING', -90)])
        record = result['incidents'][0]
        self.assertTrue(record['resolved'])
        self.assertEqual(record['resolution_source'], 'health_observation')
        self.assertIsNone(record['duration_seconds'])
        self.assertEqual(result['level'], 'normal')

    def test_older_observation_does_not_close_new_outage(self):
        state = copy.deepcopy(NORMAL)
        state['last_health_check'] = (NOW-timedelta(seconds=120)).isoformat()
        result = self.build(state, [event('ASTERISK.OFFLINE', -90)])
        self.assertFalse(result['incidents'][0]['resolved'])
        self.assertEqual(result['level'], 'critical')

    def test_inferred_internet_resolution_survives_a_later_outage(self):
        events = [event('INTERNET.OFFLINE', -90)]
        with tempfile.TemporaryDirectory() as directory, \
             patch.object(intel, 'INTELLIGENCE_FILE', Path(directory)/'intelligence.json'), \
             patch.object(intel, 'load_events', side_effect=lambda: events), \
             patch.object(intel, 'load_recovery_state', return_value={}):
            recovered = intel.build_intelligence(NORMAL)
            self.assertTrue(recovered['incidents'][0]['resolved'])
            self.assertEqual(recovered['incidents'][0]['resolution_source'],
                             'health_observation')

            # A later build must retain the inferred recovery boundary.
            repeated = intel.build_intelligence(NORMAL)
            self.assertTrue(repeated['incidents'][0]['resolved'])

            events.append(event('INTERNET.OFFLINE', 30))
            outage = copy.deepcopy(NORMAL)
            outage.update(status='fault', internet='offline')
            outage['health']['internet'] = 'critical'
            outage['last_health_check'] = (NOW+timedelta(seconds=30)).isoformat()
            current = intel.build_intelligence(outage)

        self.assertEqual(len(current['incidents']), 2)
        self.assertTrue(current['incidents'][0]['resolved'])
        self.assertFalse(current['incidents'][1]['resolved'])
        self.assertEqual(current['incidents'][1]['started_at'],
                         events[-1]['timestamp'].isoformat())
        self.assertEqual(current['level'], 'critical')

    def test_live_online_state_durably_resolves_stale_internet_outage(self):
        events = [event('INTERNET.OFFLINE', -90)]
        online = copy.deepcopy(NORMAL)
        # Status presentation is case-insensitive; reconciliation must be too.
        online['internet'] = 'ONLINE'
        with tempfile.TemporaryDirectory() as directory, \
             patch.object(intel, 'INTELLIGENCE_FILE', Path(directory)/'intelligence.json'), \
             patch.object(intel, 'load_events', side_effect=lambda: events), \
             patch.object(intel, 'load_recovery_state', return_value={}):
            recovered = intel.build_intelligence(online)
            repeated = intel.build_intelligence(online)

            events.append(event('INTERNET.OFFLINE', 30))
            outage = copy.deepcopy(NORMAL)
            outage.update(status='fault', internet='offline')
            outage['health']['internet'] = 'critical'
            outage['last_health_check'] = (NOW+timedelta(seconds=30)).isoformat()
            current = intel.build_intelligence(outage)

        for result in (recovered, repeated):
            self.assertEqual(result['level'], 'normal')
            self.assertFalse(result['attention_required'])
            self.assertEqual(len(result['incidents']), 1)
            self.assertTrue(result['incidents'][0]['resolved'])
            self.assertEqual(result['incidents'][0]['resolution_source'],
                             'health_observation')
        self.assertEqual(len(current['incidents']), 2)
        self.assertTrue(current['incidents'][0]['resolved'])
        self.assertFalse(current['incidents'][1]['resolved'])
        self.assertEqual(current['level'], 'critical')

    def test_unknown_measurement_does_not_resolve_warning(self):
        state = copy.deepcopy(NORMAL)
        state['status'] = 'degraded'
        state['health']['cpu'] = 'unknown'
        result = self.build(state, [event('HEALTH.CPU.WARNING', -90)])
        self.assertFalse(result['incidents'][0]['resolved'])
        self.assertEqual(result['level'], 'warning')

    def test_failed_recovery_history_does_not_keep_healthy_alert(self):
        events = [event('ASTERISK.OFFLINE', -90), event('RECOVERY.ASTERISK.FAILED', -60),
                  event('ASTERISK.ONLINE', -30)]
        result = self.build(NORMAL, events)
        self.assertEqual(result['recovery_failures_24h'], 1)
        self.assertEqual(result['level'], 'normal')
        self.assertFalse(result['attention_required'])
        self.assertFalse(result['recommendation']['action_required'])
        self.assertNotIn('Manual investigation', result['summary'])

    def test_recovery_expiry_and_preservation(self):
        for status in ('success', 'cancelled'):
            recovery = {'last_recovery': {'status': status,
                        'timestamp': (NOW-timedelta(hours=6)).isoformat()}}
            before = copy.deepcopy(recovery)
            self.assertIsNone(intel.recovery_display(NORMAL, recovery, NOW))
            self.assertEqual(recovery, before)
            recovery['last_recovery']['timestamp'] = (NOW-timedelta(hours=5)).isoformat()
            self.assertIsNotNone(intel.recovery_display(NORMAL, recovery, NOW))

    def test_failed_recovery_stays_visible_until_online(self):
        recovery = {'last_recovery': {'status': 'failed',
                    'timestamp': (NOW-timedelta(days=3)).isoformat()}}
        self.assertIsNone(intel.recovery_display(NORMAL, recovery, NOW))
        self.assertIsNotNone(intel.recovery_display({'asterisk':'offline'}, recovery, NOW))

    def test_invalid_recovery_timestamp_does_not_persist(self):
        self.assertIsNone(intel.recovery_display(NORMAL,
                          {'last_recovery': {'status': 'cancelled', 'timestamp':'bad'}}, NOW))

    def test_active_lockout_is_not_hidden_by_online_state(self):
        recovery = {'last_recovery': {'status': 'lockout'},
                    'asterisk_lockout_until': NOW.timestamp()+600}
        self.assertIsNotNone(intel.recovery_display(NORMAL, recovery, NOW))
        recovery['asterisk_lockout_until'] = NOW.timestamp()-1
        self.assertIsNone(intel.recovery_display(NORMAL, recovery, NOW))

    def test_atomic_intelligence_publication(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory)/'intelligence.json'
            with patch.object(intel, 'INTELLIGENCE_FILE', path):
                intel.save_intelligence({'level':'normal'})
            self.assertEqual(json.loads(path.read_text()), {'level':'normal'})
            self.assertEqual(list(Path(directory).iterdir()), [path])

    def test_active_automation_recovery_explains_no_operator_action(self):
        state = copy.deepcopy(NORMAL)
        state["automation"] = {"mode": "recovering", "last_result": "Verifying"}
        result = self.build(state, [])
        self.assertEqual(result["level"], "warning")
        self.assertFalse(result["attention_required"])
        self.assertFalse(result["recommendation"]["action_required"])
        self.assertIn("actively recovering", result["recommendation"]["message"])

    def test_maintenance_is_intentional_not_malfunction(self):
        state = copy.deepcopy(NORMAL)
        state["automation"] = {"mode": "maintenance", "maintenance_mode": True}
        result = self.build(state, [])
        self.assertEqual(result["level"], "normal")
        self.assertFalse(result["attention_required"])
        self.assertIn("intentionally suspended", result["recommendation"]["message"])

    def test_automation_escalation_requires_attention(self):
        state = copy.deepcopy(NORMAL)
        state["automation"] = {"mode": "attention", "escalation_reason": "Repeated instability"}
        result = self.build(state, [])
        self.assertEqual(result["level"], "warning")
        self.assertTrue(result["attention_required"])
        self.assertTrue(result["recommendation"]["action_required"])
        self.assertIn("Repeated instability", result["recommendation"]["message"])

    def test_transient_connectivity_does_not_escalate(self):
        state = copy.deepcopy(NORMAL)
        state["connectivity"] = {"status": "degraded", "diagnosis": "transient",
                                 "failure_domain": "dns", "sustained": False,
                                 "message": "A DNS check failed"}
        result = self.build(state, [])
        self.assertFalse(result["recommendation"]["action_required"])
        self.assertIn("transient", result["recommendation"]["message"].lower())

    def test_connectivity_failure_domains_explain_remaining_service(self):
        scenarios = {
            "gateway": ("offline", "gateway_failure", "Local BlueNode monitoring"),
            "dns": ("degraded", "dns_failure", "direct-IP Internet"),
            "external_internet": ("offline", "external_internet_failure", "default gateway"),
            "allstar_services": ("degraded", "allstar_services_failure", "general Internet"),
            "allstar_registration": ("degraded", "allstar_registration_failure", "AllStar service"),
            "asterisk": ("degraded", "asterisk_failure", "network"),
            "iax": ("degraded", "iax_failure", "Asterisk core"),
            "remote_link": ("degraded", "remote_link_failure", "Core network"),
            "local_network": ("offline", "local_network_failure", "local system monitoring"),
        }
        for domain, (status, diagnosis, expected) in scenarios.items():
            with self.subTest(domain=domain):
                state = copy.deepcopy(NORMAL)
                state["status"] = "fault" if status == "offline" else "degraded"
                state["connectivity"] = {
                    "status": status, "diagnosis": diagnosis,
                    "failure_domain": domain, "sustained": True,
                    "message": f"{domain} diagnosed",
                }
                state["health"]["internet"] = "critical" if status == "offline" else "warning"
                state["health_reasons"] = [f"{domain} diagnosed"]
                result = self.build(state, [])
                self.assertTrue(result["recommendation"]["action_required"])
                self.assertIn(expected, result["recommendation"]["message"])

    def test_connectivity_verified_recovery_needs_no_action(self):
        state = copy.deepcopy(NORMAL)
        state["connectivity"] = {"status": "degraded", "diagnosis": "recovering",
                                 "failure_domain": "healthy", "sustained": False,
                                 "message": "Connectivity returned"}
        result = self.build(state, [])
        self.assertFalse(result["recommendation"]["action_required"])
        self.assertIn("verifying", result["recommendation"]["message"])

if __name__ == '__main__':
    unittest.main()
