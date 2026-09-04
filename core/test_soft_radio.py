import json
import os
import base64
import socket
import struct
import tempfile
import threading
import unittest
from pathlib import Path
from unittest.mock import patch

import soft_radio


class Clock:
    def __init__(self): self.now = 1000
    def __call__(self): return self.now


class Result:
    def __init__(self, code=0): self.returncode, self.stdout, self.stderr = code, "", ""


def masked_frame(opcode, payload=b""):
    mask = b"abcd"
    length = len(payload)
    if length < 126:
        header = bytes((0x80 | opcode, 0x80 | length))
    else:
        header = bytes((0x80 | opcode, 0xfe)) + struct.pack("!H", length)
    return header + mask + bytes(
        value ^ mask[index % 4] for index, value in enumerate(payload))


class SoftRadioTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.config = Path(self.temp.name) / "soft-radio.json"
        self.patch = patch.object(soft_radio, "CONFIG_FILE", self.config)
        self.patch.start()
        self.clock = Clock()
        self.audit = []
        self.commands = []
        self.radio = soft_radio.SoftRadio(clock=self.clock,
            runner=self.runner, audit=lambda action, outcome: self.audit.append((action, outcome)))
        self.write_config()

    def tearDown(self):
        self.radio.stop()
        self.patch.stop()
        self.temp.cleanup()

    def runner(self, command, **_kwargs):
        self.commands.append(command)
        return Result()

    def write_config(self, **changes):
        data = {"enabled":True, "listen_host":"127.0.0.1", "listen_port":18767,
                "media_path":"/asterisk-media", "media_username":"fixture_user",
                "media_password":"fixture-value-not-secret-12345",
                "connection_name":"bluenode_soft_radio_rx", "local_node":"12345",
                "ticket_seconds":30, "buffer_frames":3, "start_channel":False}
        data.update(changes)
        self.config.write_text(json.dumps(data), encoding="utf-8")
        os.chmod(self.config, 0o640)

    def test_disabled_and_malformed_config_fail_closed(self):
        self.write_config(enabled=False)
        self.assertFalse(soft_radio._safe_config()["enabled"])
        self.config.write_text("not-json", encoding="utf-8")
        self.assertFalse(soft_radio._safe_config()["enabled"])
        self.write_config(listen_host="0.0.0.0")
        self.assertFalse(soft_radio._safe_config()["enabled"])

    def test_ticket_expiry_binding_and_one_time_use(self):
        ticket = self.radio.issue_ticket("session-a")
        self.assertFalse(self.radio.consume_ticket(ticket, "session-b"))
        ticket = self.radio.issue_ticket("session-a")
        self.assertTrue(self.radio.consume_ticket(ticket, "session-a"))
        self.assertFalse(self.radio.consume_ticket(ticket, "session-a"))
        ticket = self.radio.issue_ticket("session-a")
        self.clock.now += 31
        self.assertFalse(self.radio.consume_ticket(ticket, "session-a"))

    def test_bounded_buffer_drops_oldest_media(self):
        class Stream:
            def __init__(self): self.sent = []
            def sendall(self, data): self.sent.append(data)
        client = soft_radio.BrowserClient(Stream(), "session", 3)
        for value in range(5): client.enqueue(bytes((value,)))
        self.assertEqual(client.dropped, 2)
        self.assertEqual(list(client.queue), [b"\x02", b"\x03", b"\x04"])

    def test_browser_media_is_rejected_not_forwarded(self):
        server, browser = socket.socketpair()
        thread = threading.Thread(target=self.radio.serve_browser,
                                  args=(server, "session", lambda _token: True))
        thread.start()
        browser.sendall(masked_frame(2, b"browser audio"))
        reply = browser.recv(64)
        thread.join(2)
        browser.close(); server.close()
        self.assertEqual(reply[0] & 0x0f, 8)
        self.assertIn(("soft-radio-rx-session", "browser-media-rejected"), self.audit)

    def test_session_expiration_terminates_browser(self):
        server, browser = socket.socketpair()
        valid = {"value": True}
        thread = threading.Thread(target=self.radio.serve_browser,
            args=(server, "session", lambda _token: valid["value"]))
        thread.start()
        valid["value"] = False
        thread.join(1)
        browser.close(); server.close()
        self.assertFalse(thread.is_alive())

    def test_fixed_origin_command_is_monitor_only_and_outbound_media(self):
        self.radio._start_asterisk_channel(soft_radio._safe_config())
        command = self.commands[-1]
        self.assertEqual(command,
            ["sudo", "-n", "/usr/local/bin/bluenode-soft-radio-rx-start"])
        helper = (Path(__file__).parents[1] / "install" / "helpers" /
                  "bluenode-soft-radio-rx-start").read_text(encoding="utf-8")
        self.assertIn("c(ulaw)f(json)d(in)", helper)
        self.assertIn(",Pm,BlueNode-RX-P", helper)
        self.assertNotIn(",D,", helper)
        self.assertNotIn("d(out)", helper)

    def test_asterisk_media_is_received_without_upstream_media(self):
        server, asterisk = socket.socketpair()
        received = []
        self.radio.broadcast = received.append
        thread = threading.Thread(target=self.radio._handle_asterisk,
                                  args=(server, ("127.0.0.1", 1234)))
        thread.start()
        credential = base64.b64encode(
            b"fixture_user:fixture-value-not-secret-12345").decode()
        request = ("GET /asterisk-media HTTP/1.1\r\nHost: 127.0.0.1\r\n"
                   "Upgrade: websocket\r\nConnection: Upgrade\r\n"
                   "Sec-WebSocket-Key: MDEyMzQ1Njc4OWFiY2RlZg==\r\n"
                   "Sec-WebSocket-Protocol: media\r\n"
                   f"Authorization: Basic {credential}\r\n\r\n")
        asterisk.sendall(request.encode("ascii"))
        response = asterisk.recv(2048)
        self.assertIn(b"101 Switching Protocols", response)
        start = json.dumps({"event":"MEDIA_START", "format":"ulaw",
                            "optimal_frame_size":160}).encode()
        asterisk.sendall(masked_frame(1, start))
        asterisk.sendall(masked_frame(2, b"\xff" * 160))
        asterisk.sendall(masked_frame(8))
        thread.join(1)
        asterisk.settimeout(0.05)
        with self.assertRaises(socket.timeout): asterisk.recv(1)
        asterisk.close(); server.close()
        self.assertEqual(received, [b"\xff" * 160])

    def test_websocket_parser_rejects_unmasked_and_oversize_frames(self):
        left, right = socket.socketpair()
        left.sendall(b"\x82\x01x")
        with self.assertRaises(ValueError): soft_radio.read_frame(right, 8)
        left.close(); right.close()

    def test_broker_start_failure_is_safe(self):
        occupied = socket.socket()
        occupied.bind(("127.0.0.1", 0)); occupied.listen()
        self.write_config(listen_port=occupied.getsockname()[1])
        self.assertFalse(self.radio.start())
        self.assertEqual(self.radio.public_state(True, True)["status"], "fault")
        self.assertEqual(self.radio.last_error, "loopback media broker could not bind")
        self.assertIn(("soft-radio-rx-broker", "start-failed"), self.audit)
        occupied.close()
        left, right = socket.socketpair()
        left.sendall(b"\x82\xfe" + struct.pack("!H", 9) + b"abcd" + b"x" * 9)
        with self.assertRaises(ValueError): soft_radio.read_frame(right, 8)
        left.close(); right.close()

    def test_broker_starts_on_loopback_without_channel_origination(self):
        probe = socket.socket()
        probe.bind(("127.0.0.1", 0))
        port = probe.getsockname()[1]
        probe.close()
        self.write_config(listen_port=port, start_channel=False)
        self.assertTrue(self.radio.start())
        self.assertEqual(self.radio.server.server_address, ("127.0.0.1", port))
        self.assertEqual(self.commands, [])
        self.assertTrue(self.radio.public_state(True, True)["listening"])

    def test_invalid_enabled_configuration_surfaces_startup_failure(self):
        self.write_config(listen_host="0.0.0.0")
        self.assertTrue(soft_radio.activation_requested())
        self.assertFalse(self.radio.start())
        self.assertEqual(self.radio.last_error,
                         "enabled configuration is invalid or unreadable")
        self.assertIn(("soft-radio-rx-broker", "configuration-rejected"), self.audit)


if __name__ == "__main__": unittest.main()
