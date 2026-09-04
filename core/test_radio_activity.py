import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import patch

import radio_activity


NOW = datetime(2026, 9, 4, 12, 0, tzinfo=timezone.utc)


class RadioActivityTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.state_file = Path(self.temp.name) / "radio_activity.json"
        self.state_patch = patch.object(radio_activity, "STATE_FILE", self.state_file)
        self.names_patch = patch.object(radio_activity, "NODE_NAMES", {"54321": "Example Link"})
        self.emit_patch = patch.object(radio_activity, "emit")
        self.metadata_patch = patch.object(
            radio_activity.node_metadata, "lookup",
            return_value={"status": "unavailable"})
        self.state_patch.start()
        self.names_patch.start()
        self.emit_patch.start()
        self.metadata = self.metadata_patch.start()

    def tearDown(self):
        self.metadata_patch.stop()
        self.emit_patch.stop()
        self.names_patch.stop()
        self.state_patch.stop()
        self.temp.cleanup()

    @staticmethod
    def sample(local_rx=False, local_tx=False, links=None):
        return {"local_rx": local_rx, "local_tx": local_tx, "links": links or []}

    def test_parser_and_idle(self):
        parsed = radio_activity.parse_variables(
            "RPT_TXKEYED=0\nRPT_RXKEYED=0\nRPT_ALINKS=1,54321TU\n")
        self.assertEqual(parsed["links"], [{"node": "54321", "mode": "T", "keyed": False}])
        state = radio_activity.update(parsed, NOW)
        self.assertEqual(state["status"], "idle")
        self.assertEqual(state["tx_origin"]["source_type"], "none")

    def test_local_receiver_and_separate_transmitter(self):
        state = radio_activity.update(self.sample(local_rx=True, local_tx=True), NOW)
        self.assertEqual(state["status"], "local_rx")
        self.assertTrue(state["local_rx"])
        self.assertTrue(state["local_tx"])
        self.assertEqual(state["node"], radio_activity.NODE)
        self.assertEqual(state["tx_origin"]["source_type"], "local_rf")
        self.assertEqual(state["tx_origin"]["confidence"], "verified")

    def test_remote_node_and_friendly_name(self):
        self.metadata.return_value = {
            "status": "available", "callsign": "W1ABC",
            "location": "Orlando, Florida", "display_location": "Orlando, Florida",
            "source": "https://allmondb.allstarlink.org/allmondb.php"}
        state = radio_activity.update(self.sample(local_tx=True, links=[
            {"node": "54321", "mode": "T", "keyed": True},
        ]), NOW)
        self.assertEqual(state["status"], "remote_tx")
        self.assertEqual(state["node"], "54321")
        self.assertEqual(state["friendly_name"], "Example Link")
        self.assertEqual(state["callsign"], "W1ABC")
        self.assertEqual(state["display_location"], "Orlando, Florida")
        self.assertNotIn("latitude", state)
        self.assertEqual(state["tx_origin"]["source_node"], "54321")
        self.assertEqual(state["tx_origin"]["friendly_name"], "Example Link")
        self.assertEqual(state["tx_origin"]["confidence"], "verified_ingress")
        self.assertFalse(state["tx_origin"]["ultimate_source_known"])
        self.assertEqual(state["tx_origin"]["started_at"], NOW.isoformat())

    def test_start_end_transitions_are_not_repeated(self):
        active = self.sample(links=[{"node": "54321", "mode": "T", "keyed": True}])
        with patch.object(radio_activity, "emit") as emit:
            first = radio_activity.update(active, NOW)
            second = radio_activity.update(active, NOW + timedelta(seconds=2))
            radio_activity.update(self.sample(), NOW + timedelta(seconds=4))
        self.assertEqual(first["started_at"], second["started_at"])
        self.assertEqual([call.args[0] for call in emit.call_args_list],
                         ["RADIO.REMOTE_TX.START", "RADIO.REMOTE_TX.END"])

    def test_stale_activity_clears(self):
        radio_activity.update(self.sample(local_rx=True), NOW)
        current = radio_activity.public_state(NOW + timedelta(seconds=2))
        stale = radio_activity.public_state(
            NOW + timedelta(seconds=radio_activity.STALE_SECONDS + 1))
        self.assertEqual(current["status"], "local_rx")
        self.assertEqual(stale["status"], "unavailable")
        self.assertTrue(stale["stale"])
        self.assertFalse(stale["tx_origin"]["active"])
        self.assertEqual(stale["tx_origin"]["confidence"], "unavailable")

    def test_unavailable_and_ambiguous_fail_safely(self):
        self.assertIsNone(radio_activity.parse_variables("RPT_RXKEYED=1\n"))
        self.assertEqual(radio_activity.update(None, NOW)["status"], "unavailable")
        ambiguous = radio_activity.update(self.sample(links=[
            {"node": "11111", "mode": "T", "keyed": True},
            {"node": "22222", "mode": "T", "keyed": True},
        ]), NOW + timedelta(seconds=2))
        self.assertEqual(ambiguous["status"], "ambiguous")
        self.assertNotIn("node", ambiguous)
        self.assertEqual(ambiguous["tx_origin"]["confidence"], "ambiguous")
        self.assertEqual(ambiguous["tx_origin"]["candidate_nodes"], ["11111", "22222"])
        self.metadata.assert_not_called()

    def test_simultaneous_local_and_remote_is_not_falsely_attributed(self):
        state = radio_activity.update(self.sample(local_rx=True, local_tx=True, links=[
            {"node": "54321", "mode": "T", "keyed": True},
        ]), NOW)
        self.assertEqual(state["status"], "local_rx")
        self.assertEqual(state["tx_origin"]["source_type"], "ambiguous")
        self.assertEqual(state["tx_origin"]["direction"], "mixed")

    def test_disconnect_and_unkey_clear_origin(self):
        radio_activity.update(self.sample(links=[
            {"node": "54321", "mode": "T", "keyed": True}]), NOW)
        idle = radio_activity.update(self.sample(), NOW + timedelta(seconds=2))
        self.assertFalse(idle["tx_origin"]["active"])
        self.assertEqual(idle["tx_origin"]["source_type"], "none")
        self.assertNotIn("source_node", idle["tx_origin"])
        reconnected = radio_activity.update(self.sample(links=[
            {"node": "54321", "mode": "T", "keyed": True}]),
            NOW + timedelta(seconds=4))
        self.assertTrue(reconnected["tx_origin"]["active"])
        self.assertEqual(reconnected["tx_origin"]["source_node"], "54321")
        self.assertEqual(reconnected["tx_origin"]["started_at"],
                         (NOW + timedelta(seconds=4)).isoformat())

    def test_metadata_does_not_leak_to_a_new_active_node(self):
        self.metadata.side_effect = [
            {"status": "available", "callsign": "W1ABC", "location": "Orlando",
             "display_location": "Orlando"},
            {"status": "not_found"},
        ]
        first = radio_activity.update(self.sample(links=[
            {"node": "54321", "mode": "T", "keyed": True}]), NOW)
        second = radio_activity.update(self.sample(links=[
            {"node": "99999", "mode": "T", "keyed": True}]),
            NOW + timedelta(seconds=2))
        self.assertEqual(first["callsign"], "W1ABC")
        self.assertEqual(second["node"], "99999")
        self.assertNotIn("callsign", second)
        self.assertNotIn("display_location", second)

    def test_malformed_persisted_state_fails_safely(self):
        self.state_file.write_text("not json")
        self.assertEqual(radio_activity.public_state(NOW)["status"], "unavailable")


if __name__ == "__main__":
    unittest.main()
