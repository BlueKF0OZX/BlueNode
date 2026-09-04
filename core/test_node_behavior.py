#!/usr/bin/env python3

import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import patch

import node_behavior


NOW = 2_000_000_000


def event(age, name, message=""):
    return {"timestamp": NOW - age, "event": name, "message": message}


def radio(local=False, started_age=0):
    return {"telemetry_available": True, "stale": False, "local_rx": local,
            "started_at": datetime.fromtimestamp(NOW - started_age, timezone.utc).isoformat(),
            "status": "local_rx" if local else "idle"}


class NodeBehaviorTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.state = Path(self.temp.name) / "node_behavior.json"
        self.state_patch = patch.object(node_behavior, "STATE_FILE", self.state)
        self.emit_patch = patch.object(node_behavior, "emit")
        self.emit = self.emit_patch.start()
        self.state_patch.start()

    def tearDown(self):
        self.state_patch.stop(); self.emit_patch.stop(); self.temp.cleanup()

    def analyze(self, events=None, radio_state=None, automation=None, connectivity=None):
        return node_behavior.analyze(events or [], radio_state or radio(), automation or {},
                                     connectivity or {"diagnosis": "healthy"}, NOW)

    def test_quiet_and_ordinary_connection_activity_are_normal(self):
        self.assertEqual(self.analyze()["assessment"], "normal")
        events = [event(100, "CONTROL.NODE.CONNECT", "Connect command sent for node 12345"),
                  event(95, "NODE.CONNECTED", "Node 12345 connected"),
                  event(40, "NODE.DISCONNECTED", "Node 12345 disconnected")]
        self.assertEqual(self.analyze(events)["assessment"], "normal")

    def test_repeated_attempts_and_unconfirmed_establishment(self):
        events = [event(200 - index * 20, "CONTROL.NODE.CONNECT",
                        "Connect command sent for node 12345") for index in range(8)]
        result = self.analyze(events)
        self.assertEqual(result["assessment"], "warning")
        codes = {item["code"] for item in result["reasons"]}
        self.assertIn("repeated_connection_attempts", codes)
        self.assertIn("repeated_link_failures", codes)
        failure = next(item for item in result["reasons"] if item["code"] == "repeated_link_failures")
        self.assertIn("local connectivity and Asterisk are healthy", failure["evidence"])
        self.assertNotIn("reason", failure)

    def test_established_links_are_not_counted_as_failures(self):
        events = []
        for index in range(5):
            age = 240 - index * 30
            events.extend([event(age, "CONTROL.NODE.CONNECT", "Connect command sent for node 12345"),
                           event(age - 5, "NODE.CONNECTED", "Node 12345 connected")])
        result = self.analyze(events)
        self.assertNotIn("repeated_link_failures", {item["code"] for item in result["reasons"]})

    def test_friendly_connection_message_confirms_establishment(self):
        events = []
        for index in range(5):
            age = 240 - index * 30
            events.extend([event(age, "CONTROL.NODE.CONNECT", "Connect command sent for node 12345"),
                           event(age - 5, "NODE.CONNECTED", "Example Node (12345) connected")])
        result = self.analyze(events)
        self.assertNotIn("repeated_link_failures", {item["code"] for item in result["reasons"]})

    def test_connection_churn(self):
        events = [event(250 - index * 20,
                        "NODE.CONNECTED" if index % 2 else "NODE.DISCONNECTED",
                        "Node 23456 changed") for index in range(10)]
        result = self.analyze(events)
        self.assertEqual(result["assessment"], "warning")
        self.assertIn("connection_churn", {item["code"] for item in result["reasons"]})

    def test_extended_local_rf_and_linked_audio_distinction(self):
        notice = self.analyze(radio_state=radio(True, 95))
        self.assertEqual(notice["assessment"], "notice")
        result = self.analyze(radio_state=radio(True, 181))
        self.assertEqual(result["assessment"], "warning")
        self.assertEqual(result["reasons"][0]["code"], "extended_local_rf")
        remote = radio(False)
        remote.update({"status": "remote_tx", "remote_rx_nodes": ["12345"]})
        self.assertEqual(self.analyze(radio_state=remote)["assessment"], "normal")

    def test_rapid_local_keying_uses_only_local_transitions(self):
        local = [event(100 - index * 5, "RADIO.LOCAL_RX.START" if index % 2 else
                       "RADIO.LOCAL_RX.END") for index in range(16)]
        remote = [event(100 - index * 5, "RADIO.REMOTE_TX.START" if index % 2 else
                        "RADIO.REMOTE_TX.END") for index in range(20)]
        self.assertEqual(self.analyze(local)["assessment"], "warning")
        self.assertEqual(self.analyze(remote)["assessment"], "normal")

    def test_frequent_controls_and_automation(self):
        controls = [event(200 - index * 5, "CONTROL.SKYWARN.ENABLE") for index in range(20)]
        self.assertIn("frequent_controls", {x["code"] for x in self.analyze(controls)["reasons"]})
        result = self.analyze(automation={"recent_recovery_attempts": [NOW - 20, NOW - 40, NOW - 60]})
        self.assertEqual(result["assessment"], "warning")
        self.assertEqual(result["reasons"][0]["code"], "frequent_automation")

    def test_frequent_remote_admin_actions_are_control_activity(self):
        actions = [event(200 - index * 5, "ADMIN.CONTROL", "refresh-connectivity")
                   for index in range(20)]
        result = self.analyze(actions)
        self.assertEqual(result["assessment"], "warning")
        self.assertEqual(result["reasons"][0]["code"], "frequent_controls")

    def test_stale_and_ambiguous_telemetry_fail_safely(self):
        result = self.analyze(radio_state={"telemetry_available": False, "stale": True})
        self.assertEqual(result["assessment"], "normal")
        self.assertEqual(result["evidence_status"], "partial")
        self.assertIn("not assessed", result["ambiguity"])
        state = node_behavior.default_state()
        state["last_check"] = datetime.fromtimestamp(NOW - 1000, timezone.utc).isoformat()
        state["stale_after_seconds"] = 60
        public = node_behavior.public_state(state, NOW)
        self.assertTrue(public["stale"])
        self.assertFalse(public["operator_review_recommended"])

    def test_transition_events_are_deduplicated_and_recover_to_normal(self):
        warning = [event(200 - index * 20, "CONTROL.NODE.CONNECT",
                         "Connect command sent for node 12345") for index in range(8)]
        node_behavior.observe(radio(), {}, {"diagnosis": "healthy"}, NOW, warning)
        node_behavior.observe(radio(), {}, {"diagnosis": "healthy"}, NOW + 1, warning)
        self.assertEqual(self.emit.call_count, 1)
        node_behavior.observe(radio(), {}, {"diagnosis": "healthy"}, NOW + 400, [])
        self.assertEqual(self.emit.call_count, 2)
        self.assertEqual(self.emit.call_args_list[-1].args[0], "BEHAVIOR.NORMAL")
        self.assertEqual(node_behavior.load_state()["assessment"], "normal")

    def test_malformed_persisted_state_fails_safe(self):
        self.state.write_text("not json", encoding="utf-8")
        state = node_behavior.public_state(now=NOW)
        self.assertEqual(state["assessment"], "normal")
        self.assertTrue(state["stale"])


if __name__ == "__main__":
    unittest.main()
