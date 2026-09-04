import unittest

import soft_radio_safety as safety


def state(**changes):
    base = {
        "asterisk_active": True,
        "pid": "321",
        "start_marker": "654",
        "tx_keyed": "0",
        "channels": ["SimpleUSB/radio-1"],
        "modules": {module: False for module in safety.MODULES},
        "uptime_seconds": 1000,
        "reload_seconds": 1000,
        "listeners": [],
    }
    base.update(changes)
    return base


class SoftRadioSafetyTests(unittest.TestCase):
    def verify(self, before=None, after=None):
        before = before or state()
        after = after or state(listeners=["127.0.0.1:8767"],
                               uptime_seconds=1012, reload_seconds=1012)
        return safety.verify_broker_only(before, after)

    def test_volatile_counters_and_cli_formatting_do_not_fail_semantic_state(self):
        self.assertEqual(self.verify(), [])
        output_a = "SimpleUSB/radio-1!context!exten!1!Up!App!Data!Caller!1!2!3\n1 active channel\n"
        output_b = "SimpleUSB/radio-1!context!exten!1!Up!App!Data!Caller!9!88!777\n9 calls processed\n"
        self.assertEqual(safety._channels(output_a), safety._channels(output_b))

    def test_actual_new_channel_fails(self):
        errors = self.verify(after=state(
            channels=["SimpleUSB/radio-1", "IAX2/fixture-1"],
            listeners=["127.0.0.1:8767"], reload_seconds=1001))
        self.assertIn("Asterisk channel set changed", errors)

    def test_soft_radio_channel_fails(self):
        errors = self.verify(after=state(
            channels=["SimpleUSB/radio-1", "WebSocket/fixture-1"],
            listeners=["127.0.0.1:8767"], reload_seconds=1001))
        self.assertIn("Soft Radio Asterisk channel exists", errors)

    def test_module_state_change_fails(self):
        modules = {module: False for module in safety.MODULES}
        modules[safety.MODULES[0]] = True
        errors = self.verify(after=state(modules=modules,
            listeners=["127.0.0.1:8767"], reload_seconds=1001))
        self.assertIn("Soft Radio module state changed", errors)

    def test_pid_or_start_marker_change_fails(self):
        errors = self.verify(after=state(pid="999", start_marker="888",
            listeners=["127.0.0.1:8767"], reload_seconds=1))
        self.assertIn("Asterisk PID changed", errors)
        self.assertIn("Asterisk start marker changed", errors)
        self.assertIn("Asterisk reload state changed or is unavailable", errors)

    def test_tx_key_state_change_fails(self):
        errors = self.verify(after=state(tx_keyed="1",
            listeners=["127.0.0.1:8767"], reload_seconds=1001))
        self.assertIn("RPT_TXKEYED is not zero", errors)

    def test_broker_bind_failure_or_non_loopback_listener_fails(self):
        self.assertIn("broker is not listening exclusively on expected loopback",
                      self.verify(after=state(reload_seconds=1001)))
        self.assertIn("broker is not listening exclusively on expected loopback",
                      self.verify(after=state(listeners=["0.0.0.0:8767"],
                                              reload_seconds=1001)))

    def test_reload_counter_reset_fails_but_normal_increase_passes(self):
        self.assertEqual(self.verify(), [])
        errors = self.verify(after=state(listeners=["127.0.0.1:8767"],
                                         reload_seconds=2))
        self.assertIn("Asterisk reload state changed or is unavailable", errors)


if __name__ == "__main__":
    unittest.main()
