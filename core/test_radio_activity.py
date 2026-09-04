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
        self.state_patch.start()
        self.names_patch.start()
        self.emit_patch.start()

    def tearDown(self):
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
        self.assertEqual(radio_activity.update(parsed, NOW)["status"], "idle")

    def test_local_receiver_and_separate_transmitter(self):
        state = radio_activity.update(self.sample(local_rx=True, local_tx=True), NOW)
        self.assertEqual(state["status"], "local_rx")
        self.assertTrue(state["local_rx"])
        self.assertTrue(state["local_tx"])
        self.assertEqual(state["node"], radio_activity.NODE)

    def test_remote_node_and_friendly_name(self):
        state = radio_activity.update(self.sample(local_tx=True, links=[
            {"node": "54321", "mode": "T", "keyed": True},
        ]), NOW)
        self.assertEqual(state["status"], "remote_tx")
        self.assertEqual(state["node"], "54321")
        self.assertEqual(state["friendly_name"], "Example Link")

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

    def test_unavailable_and_ambiguous_fail_safely(self):
        self.assertIsNone(radio_activity.parse_variables("RPT_RXKEYED=1\n"))
        self.assertEqual(radio_activity.update(None, NOW)["status"], "unavailable")
        ambiguous = radio_activity.update(self.sample(links=[
            {"node": "11111", "mode": "T", "keyed": True},
            {"node": "22222", "mode": "T", "keyed": True},
        ]), NOW + timedelta(seconds=2))
        self.assertEqual(ambiguous["status"], "ambiguous")
        self.assertNotIn("node", ambiguous)

    def test_malformed_persisted_state_fails_safely(self):
        self.state_file.write_text("not json")
        self.assertEqual(radio_activity.public_state(NOW)["status"], "unavailable")


if __name__ == "__main__":
    unittest.main()
