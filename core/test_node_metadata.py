import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import patch

import node_metadata


NOW = datetime(2026, 9, 4, 12, 0, tzinfo=timezone.utc)


class NodeMetadataTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.file_patch = patch.object(
            node_metadata, "CACHE_FILE", Path(self.temp.name) / "node_metadata.json")
        self.file_patch.start()
        node_metadata._MEMORY_CACHE = None
        node_metadata._REFRESHING = False
        node_metadata._LAST_REFRESH_ATTEMPT = 0

    def tearDown(self):
        self.file_patch.stop()
        node_metadata._MEMORY_CACHE = None
        node_metadata._REFRESHING = False
        node_metadata._LAST_REFRESH_ATTEMPT = 0
        self.temp.cleanup()

    @staticmethod
    def directory():
        return {
            "54321": {"node": "54321", "callsign": "W1ABC",
                      "description": "Example repeater",
                      "location": "Orlando, Florida",
                      "display_location": "Orlando, Florida"}
        }

    def seed(self, age=0, nodes=None, negative=None):
        node_metadata._save_cache({
            "version": 1, "source": node_metadata.SOURCE_URL,
            "fetched_at": (NOW - timedelta(seconds=age)).isoformat(),
            "nodes": self.directory() if nodes is None else nodes,
            "negative": negative or {},
        })

    def test_successful_lookup_and_cache_hit(self):
        self.seed()
        with patch.object(node_metadata, "schedule_refresh") as schedule:
            first = node_metadata.lookup("54321", NOW)
            second = node_metadata.lookup("54321", NOW + timedelta(seconds=5))
        self.assertEqual(first["callsign"], "W1ABC")
        self.assertEqual(first["display_location"], "Orlando, Florida")
        self.assertEqual(second["status"], "available")
        self.assertNotIn("latitude", first)
        schedule.assert_not_called()

    def test_missing_metadata_uses_short_negative_cache(self):
        self.seed(nodes={}, negative={"99999": NOW.isoformat()})
        with patch.object(node_metadata, "schedule_refresh") as schedule:
            result = node_metadata.lookup("99999", NOW + timedelta(seconds=10))
        self.assertEqual(result["status"], "not_found")
        schedule.assert_not_called()

    def test_cache_expiry_schedules_refresh_without_blocking(self):
        self.seed(age=node_metadata.SUCCESS_TTL_SECONDS + 1)
        with patch.object(node_metadata, "schedule_refresh", return_value=True) as schedule:
            result = node_metadata.lookup("54321", NOW)
        self.assertEqual(result["status"], "unavailable")
        schedule.assert_called_once_with()

    def test_negative_expiry_schedules_refresh(self):
        old = (NOW - timedelta(seconds=node_metadata.NEGATIVE_TTL_SECONDS + 1)).isoformat()
        self.seed(nodes={}, negative={"99999": old})
        with patch.object(node_metadata, "schedule_refresh", return_value=True) as schedule:
            result = node_metadata.lookup("99999", NOW)
        self.assertEqual(result["status"], "not_found")
        schedule.assert_called_once_with()

    def test_source_unavailable_preserves_existing_cache(self):
        self.seed()
        with self.assertRaises(OSError):
            node_metadata.refresh(NOW, fetcher=lambda: (_ for _ in ()).throw(OSError("offline")))
        self.assertEqual(node_metadata.lookup("54321", NOW)["callsign"], "W1ABC")

    def test_malformed_directory_and_cache_fail_safely(self):
        self.assertEqual(node_metadata.parse_directory("bad\n123|too|short"), {})
        node_metadata.CACHE_FILE.write_text("not json", encoding="utf-8")
        node_metadata._MEMORY_CACHE = None
        with patch.object(node_metadata, "schedule_refresh", return_value=True):
            self.assertEqual(node_metadata.lookup("54321", NOW)["status"], "unavailable")

    def test_official_directory_record_parsing(self):
        parsed = node_metadata.parse_directory(
            "54321|W1ABC|Example repeater|Orlando, Florida\n")
        self.assertEqual(parsed, self.directory())

    def test_refresh_attempts_are_rate_limited(self):
        node_metadata._LAST_REFRESH_ATTEMPT = node_metadata.utc_now().timestamp()
        with patch.object(node_metadata.threading, "Thread") as thread:
            self.assertFalse(node_metadata.schedule_refresh())
        thread.assert_not_called()


if __name__ == "__main__":
    unittest.main()
