import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import patch
from subprocess import CompletedProcess

import connectivity


NOW = datetime(2026, 9, 4, 12, 0, tzinfo=timezone.utc)


class ConnectivityTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.state_patch = patch.object(connectivity, "STATE_FILE", Path(self.temp.name) / "connectivity.json")
        self.emit_patch = patch.object(connectivity, "emit")
        self.state_patch.start()
        self.emit = self.emit_patch.start()

    def tearDown(self):
        self.emit_patch.stop()
        self.state_patch.stop()
        self.temp.cleanup()

    @staticmethod
    def healthy():
        return {"interface": True, "gateway": True, "dns": True,
                "internet": True, "allstar_services": True,
                "allstar": True, "asterisk": True, "iax": True,
                "remote_links": []}

    def sustained(self, field):
        checks = self.healthy()
        checks[field] = False
        first = connectivity.update(checks, NOW)
        second = connectivity.update(checks, NOW + timedelta(seconds=30))
        self.assertEqual(first["diagnosis"], "transient")
        self.assertFalse(first["sustained"])
        self.assertEqual(connectivity.legacy_internet_state(first), "online")
        self.assertTrue(second["sustained"])
        return second

    def test_everything_healthy(self):
        self.assertGreaterEqual(connectivity.INTERVAL_SECONDS, 10)
        state = connectivity.update(self.healthy(), NOW)
        self.assertEqual(state["status"], "healthy")
        self.assertEqual(state["diagnosis"], "healthy")
        self.assertEqual(connectivity.legacy_internet_state(state), "online")

    def test_gateway_unavailable(self):
        state = self.sustained("gateway")
        self.assertEqual((state["diagnosis"], state["status"]), ("gateway_failure", "offline"))
        self.assertEqual(state["layers"]["dns"]["status"], "blocked_by_upstream")
        self.assertEqual(state["layers"]["internet"]["status"], "blocked_by_upstream")

    def test_local_interface_unavailable(self):
        state = self.sustained("interface")
        self.assertEqual((state["diagnosis"], state["status"]),
                         ("local_network_failure", "offline"))

    def test_dns_failure_with_gateway_healthy(self):
        state = self.sustained("dns")
        self.assertEqual((state["diagnosis"], state["status"]), ("dns_failure", "degraded"))
        self.assertTrue(state["checks"]["gateway"])
        self.assertEqual(connectivity.legacy_internet_state(state), "online")
        self.assertEqual(state["layers"]["internet"]["status"], "ok")
        self.assertEqual(state["layers"]["allstar_services"]["status"],
                         "blocked_by_upstream")

    def test_external_internet_failure_with_lan_healthy(self):
        state = self.sustained("internet")
        self.assertEqual(state["diagnosis"], "external_internet_failure")
        self.assertEqual(state["status"], "offline")
        self.assertTrue(state["checks"]["interface"])

    def test_allstar_service_failure_with_general_internet_healthy(self):
        state = self.sustained("allstar_services")
        self.assertEqual((state["diagnosis"], state["status"]),
                         ("allstar_services_failure", "degraded"))
        self.assertEqual(state["layers"]["internet"]["status"], "ok")
        self.assertEqual(state["layers"]["allstar_registration"]["status"],
                         "ok")

    def test_registration_failure(self):
        state = self.sustained("allstar")
        self.assertEqual((state["diagnosis"], state["status"]),
                         ("allstar_registration_failure", "degraded"))
        self.assertEqual(state["layers"]["allstar_services"]["status"], "ok")

    def test_negative_registration_is_blocked_when_service_is_unreachable(self):
        checks = self.healthy()
        checks["allstar_services"] = False
        checks["allstar"] = False
        state = connectivity.update(checks, NOW)
        self.assertEqual(state["failure_domain"], "allstar_services")
        self.assertEqual(state["layers"]["allstar_registration"]["status"],
                         "blocked_by_upstream")

    def test_asterisk_and_iax_failures(self):
        asterisk = self.sustained("asterisk")
        self.assertEqual(asterisk["diagnosis"], "asterisk_failure")
        self.state_file_reset()
        iax = self.sustained("iax")
        self.assertEqual(iax["diagnosis"], "iax_failure")

    def state_file_reset(self):
        if connectivity.STATE_FILE.exists():
            connectivity.STATE_FILE.unlink()

    def test_remote_link_specific_failure_uses_only_explicit_state(self):
        checks = self.healthy()
        checks["remote_links"] = [{"node": "54321", "state": "connecting",
                                    "evidence": "App_Rpt reports connecting"}]
        connectivity.update(checks, NOW)
        state = connectivity.update(checks, NOW + timedelta(seconds=30))
        self.assertEqual(state["diagnosis"], "remote_link_failure")
        self.assertIn("54321", state["layers"]["remote_links"]["evidence"])
        self.assertNotIn("reason", state["checks"]["remote_links"][0])

    def test_unknown_is_distinct_from_failed_and_blocked(self):
        checks = self.healthy()
        checks["dns"] = None
        state = connectivity.update(checks, NOW)
        self.assertEqual(state["failure_domain"], "unavailable")
        self.assertEqual(state["layers"]["dns"]["status"], "unknown")
        self.assertEqual(state["layers"]["allstar_services"]["status"],
                         "blocked_by_upstream")

    def test_remote_link_parser_uses_explicit_app_rpt_state(self):
        output = (
            "NODE      PEER RECONNECTS DIRECTION CONNECT TIME CONNECT STATE\n"
            "54321     203.0.113.10:4569 0 OUT 00:00:10:00 ESTABLISHED\n"
            "23456     (none) 2 IN 00:00:03:00 CONNECTING\n"
        )
        with patch.object(connectivity, "_run",
                          return_value=CompletedProcess([], 0, output, "")):
            links = connectivity.remote_link_states()
        self.assertEqual(links[0]["state"], "established")
        self.assertEqual(links[1]["state"], "connecting")
        self.assertEqual(links[1]["direction"], "in")

    def test_run_checks_does_not_probe_blocked_network_layers(self):
        with patch.object(connectivity, "default_route", return_value=("eth0", "192.0.2.1")), \
             patch.object(connectivity, "interface_available", return_value=True), \
             patch.object(connectivity, "gateway_reachable", return_value=False), \
             patch.object(connectivity, "dns_resolves") as dns, \
             patch.object(connectivity, "external_reachable") as internet, \
             patch.object(connectivity, "tcp_reachable") as allstar_service, \
             patch.object(connectivity, "asterisk_available", return_value=True), \
             patch.object(connectivity, "allstar_registered", return_value=True), \
             patch.object(connectivity, "iax_available", return_value=True), \
             patch.object(connectivity, "remote_link_states", return_value=[]):
            checks = connectivity.run_checks()
        self.assertIsNone(checks["dns"])
        self.assertIsNone(checks["internet"])
        self.assertIsNone(checks["allstar_services"])
        dns.assert_not_called()
        internet.assert_not_called()
        allstar_service.assert_not_called()

    def test_verified_recovery_requires_confirmation(self):
        self.sustained("gateway")
        first = connectivity.update(self.healthy(), NOW + timedelta(seconds=60))
        second = connectivity.update(self.healthy(), NOW + timedelta(seconds=90))
        self.assertEqual(first["diagnosis"], "recovering")
        self.assertEqual(connectivity.legacy_internet_state(first), "offline")
        self.assertEqual(second["diagnosis"], "healthy")
        self.assertFalse(second["sustained"])

    def test_stale_state_clears(self):
        connectivity.update(self.healthy(), NOW)
        state = connectivity.public_state(NOW + timedelta(seconds=connectivity.STALE_SECONDS + 1))
        self.assertEqual(state["diagnosis"], "unavailable")
        self.assertTrue(state["stale"])

    def test_malformed_state_fails_safely(self):
        connectivity.STATE_FILE.write_text("bad json")
        self.assertEqual(connectivity.public_state(NOW)["status"], "unavailable")
        connectivity.STATE_FILE.write_text('{"consecutive_failures": []}')
        self.assertEqual(connectivity.update(self.healthy(), NOW)["status"], "healthy")

    def test_events_are_emitted_only_for_transitions(self):
        connectivity.update(self.healthy(), NOW)
        checks = self.healthy()
        checks["dns"] = False
        connectivity.update(checks, NOW + timedelta(seconds=30))
        connectivity.update(checks, NOW + timedelta(seconds=60))
        connectivity.update(checks, NOW + timedelta(seconds=90))

        events = [call.args[0] for call in self.emit.call_args_list]
        self.assertEqual(events, ["CONNECTIVITY.TRANSIENT", "CONNECTIVITY.DNS_FAILURE"])


if __name__ == "__main__":
    unittest.main()
