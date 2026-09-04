#!/usr/bin/env python3
"""RX-only Soft Radio admission, media fan-out, and Asterisk supervision.

The Asterisk side is a loopback-only WebSocket server.  Browser sockets are
accepted only by the authenticated BlueNode HTTP server.  No code in this
module sends media or Asterisk control messages toward Asterisk.
"""

import base64
import hashlib
import hmac
import json
import os
import socket
import socketserver
import struct
import subprocess
import threading
import time
from collections import deque
from pathlib import Path
from urllib.parse import urlsplit


CONFIG_FILE = Path(os.environ.get(
    "BLUENODE_SOFT_RADIO_CONFIG", "/etc/bluenode/soft-radio.json"))
PERMISSION = "soft_radio_rx"
TICKET_SECONDS = 30
MAX_BROWSER_FRAME = 4096
MAX_ASTERISK_FRAME = 8192


def _safe_config():
    """Load validated external configuration, failing closed on any error."""
    disabled = {"enabled": False}
    try:
        if CONFIG_FILE.is_symlink():
            return disabled
        stat = CONFIG_FILE.stat()
        if os.name == "posix" and stat.st_mode & 0o007:
            return disabled
        raw = json.loads(CONFIG_FILE.read_text(encoding="utf-8"))
        if not isinstance(raw, dict) or raw.get("enabled") is not True:
            return disabled
        allowed = {"enabled", "listen_host", "listen_port", "media_path",
                   "media_username", "media_password", "connection_name",
                   "local_node", "ticket_seconds", "buffer_frames",
                   "start_channel"}
        if set(raw) - allowed:
            return disabled
        host = str(raw.get("listen_host", "127.0.0.1"))
        port = int(raw.get("listen_port", 8767))
        path = str(raw.get("media_path", "/asterisk-media"))
        username = str(raw.get("media_username", ""))
        credential_secret = str(raw.get("media_password", ""))
        connection = str(raw.get("connection_name", "bluenode_soft_radio_rx"))
        node = str(raw.get("local_node", ""))
        ticket_seconds = int(raw.get("ticket_seconds", TICKET_SECONDS))
        buffer_frames = int(raw.get("buffer_frames", 12))
        if host not in ("127.0.0.1", "::1") or not 1024 <= port <= 65535:
            return disabled
        if path != "/asterisk-media" or len(username) < 8 or len(credential_secret) < 24:
            return disabled
        if not connection.replace("_", "").isalnum() or len(connection) > 64:
            return disabled
        if not node.isdigit() or not 1 <= len(node) <= 10:
            return disabled
        if not 10 <= ticket_seconds <= 60 or not 3 <= buffer_frames <= 50:
            return disabled
        return {"enabled": True, "listen_host": host, "listen_port": port,
                "media_path": path, "media_username": username,
                "media_password": credential_secret, "connection_name": connection,
                "local_node": node, "ticket_seconds": ticket_seconds,
                "buffer_frames": buffer_frames,
                "start_channel": raw.get("start_channel") is True}
    except (OSError, ValueError, TypeError, json.JSONDecodeError):
        return disabled


def _read_exact(stream, length):
    data = bytearray()
    while len(data) < length:
        chunk = stream.recv(length - len(data))
        if not chunk:
            raise ConnectionError("WebSocket closed")
        data.extend(chunk)
    return bytes(data)


def read_frame(stream, maximum):
    """Read one RFC 6455 client frame; client masking is mandatory."""
    first, second = _read_exact(stream, 2)
    opcode = first & 0x0F
    if not first & 0x80 or not second & 0x80:
        raise ValueError("fragmented or unmasked WebSocket frame")
    length = second & 0x7F
    if length == 126:
        length = struct.unpack("!H", _read_exact(stream, 2))[0]
    elif length == 127:
        length = struct.unpack("!Q", _read_exact(stream, 8))[0]
    if length > maximum:
        raise ValueError("WebSocket frame exceeds limit")
    mask = _read_exact(stream, 4)
    payload = _read_exact(stream, length)
    return opcode, bytes(value ^ mask[index % 4]
                         for index, value in enumerate(payload))


def make_frame(opcode, payload=b""):
    payload = bytes(payload)
    if len(payload) < 126:
        header = bytes((0x80 | opcode, len(payload)))
    elif len(payload) <= 65535:
        header = bytes((0x80 | opcode, 126)) + struct.pack("!H", len(payload))
    else:
        header = bytes((0x80 | opcode, 127)) + struct.pack("!Q", len(payload))
    return header + payload


def websocket_accept(key):
    digest = hashlib.sha1((key + "258EAFA5-E914-47DA-95CA-C5AB0DC85B11").encode(
        "ascii")).digest()
    return base64.b64encode(digest).decode("ascii")


class BrowserClient:
    def __init__(self, stream, session_token, maximum_frames):
        self.stream = stream
        self.session_token = session_token
        self.queue = deque(maxlen=maximum_frames)
        self.lock = threading.Lock()
        self.dropped = 0

    def enqueue(self, payload):
        with self.lock:
            if len(self.queue) == self.queue.maxlen:
                self.queue.popleft()
                self.dropped += 1
            self.queue.append(bytes(payload))

    def drain(self):
        with self.lock:
            frames = list(self.queue)
            self.queue.clear()
        for payload in frames:
            self.stream.sendall(make_frame(2, payload))


class SoftRadio:
    """One-way media broker with one-time, session-bound browser tickets."""

    def __init__(self, clock=time.time, runner=subprocess.run, audit=None):
        self.clock = clock
        self.runner = runner
        self.audit = audit or (lambda _action, _outcome: None)
        self.lock = threading.RLock()
        self.tickets = {}
        self.clients = set()
        self.media_connected = False
        self.last_error = ""
        self.server = None
        self.server_thread = None

    def public_state(self, authenticated=False, permitted=False):
        config = _safe_config()
        state = {"enabled": config.get("enabled", False),
                 "authorized": bool(authenticated and permitted),
                 "listening": False, "listeners": 0, "media_connected": False,
                 "status": "disabled"}
        if config.get("enabled"):
            with self.lock:
                state.update({"listening": self.server is not None,
                              "listeners": len(self.clients),
                              "media_connected": self.media_connected})
            state["status"] = ("fault" if self.last_error else
                               "listening" if state["media_connected"] else "idle")
        return state

    @staticmethod
    def _ticket_digest(ticket):
        return hashlib.sha256(ticket.encode("ascii")).digest()

    def issue_ticket(self, session_token):
        config = _safe_config()
        if not config.get("enabled"):
            return None
        import secrets
        ticket = secrets.token_urlsafe(32)
        digest = self._ticket_digest(ticket)
        with self.lock:
            now = self.clock()
            self._purge_tickets(now)
            self.tickets[digest] = (str(session_token), now + config["ticket_seconds"])
        self.audit("soft-radio-rx-ticket", "issued")
        return ticket

    def _purge_tickets(self, now):
        for digest, (_session, expires) in list(self.tickets.items()):
            if expires <= now:
                del self.tickets[digest]

    def consume_ticket(self, ticket, session_token):
        if not ticket or not session_token:
            return False
        digest = self._ticket_digest(str(ticket))
        with self.lock:
            now = self.clock()
            self._purge_tickets(now)
            record = self.tickets.pop(digest, None)
        return bool(record and record[1] > now and
                    hmac.compare_digest(record[0], str(session_token)))

    def disconnect_session(self, session_token):
        with self.lock:
            clients = [client for client in self.clients
                       if hmac.compare_digest(client.session_token,
                                              str(session_token or ""))]
        for client in clients:
            try:
                client.stream.shutdown(socket.SHUT_RDWR)
            except OSError:
                pass

    def broadcast(self, payload):
        if not payload or len(payload) > MAX_ASTERISK_FRAME:
            return
        with self.lock:
            clients = list(self.clients)
        for client in clients:
            client.enqueue(payload)

    def serve_browser(self, stream, session_token, session_valid):
        config = _safe_config()
        client = BrowserClient(stream, str(session_token), config.get("buffer_frames", 12))
        with self.lock:
            self.clients.add(client)
        self.audit("soft-radio-rx-session", "started")
        outcome = "stopped"
        try:
            stream.settimeout(0.025)
            next_authorization_check = 0
            authorized = True
            while authorized:
                if time.monotonic() >= next_authorization_check:
                    authorized = (_safe_config().get("enabled") and
                                  session_valid(session_token))
                    next_authorization_check = time.monotonic() + 1
                    if not authorized:
                        break
                client.drain()
                try:
                    opcode, payload = read_frame(stream, MAX_BROWSER_FRAME)
                except socket.timeout:
                    continue
                if opcode == 8:
                    break
                if opcode == 9:
                    stream.sendall(make_frame(10, payload))
                    continue
                # Browser-originated text and binary data are never forwarded.
                outcome = "browser-media-rejected"
                stream.sendall(make_frame(8, struct.pack("!H", 1008)))
                break
        except (ConnectionError, OSError, ValueError):
            outcome = "connection-closed"
        finally:
            with self.lock:
                self.clients.discard(client)
            self.audit("soft-radio-rx-session", outcome)

    def start(self):
        config = _safe_config()
        if not config.get("enabled"):
            return False
        with self.lock:
            if self.server is not None:
                return True
            broker = self

            class Handler(socketserver.BaseRequestHandler):
                def handle(self):
                    broker._handle_asterisk(self.request, self.client_address)

            class Server(socketserver.ThreadingTCPServer):
                allow_reuse_address = True
                daemon_threads = True

            try:
                server = Server((config["listen_host"], config["listen_port"]), Handler)
            except OSError as exc:
                self.last_error = "media broker unavailable"
                self.audit("soft-radio-rx-broker", "start-failed")
                return False
            self.server = server
            self.server_thread = threading.Thread(target=server.serve_forever,
                                                  name="soft-radio-rx", daemon=True)
            self.server_thread.start()
            self.last_error = ""
        if config.get("start_channel"):
            self._start_asterisk_channel(config)
        return True

    def stop(self):
        with self.lock:
            server, thread = self.server, self.server_thread
            clients = list(self.clients)
            self.server = self.server_thread = None
        for client in clients:
            try:
                client.stream.shutdown(socket.SHUT_RDWR)
            except OSError:
                pass
        if server:
            server.shutdown()
            server.server_close()
        if thread and thread is not threading.current_thread():
            thread.join(timeout=2)

    def _start_asterisk_channel(self, config):
        # The root-owned no-argument helper independently validates the fixed
        # external configuration and constructs only d(in) + App_Rpt Pm.
        command = ["sudo", "-n", "/usr/local/bin/bluenode-soft-radio-rx-start"]
        try:
            result = self.runner(command, capture_output=True, text=True, timeout=10)
            if result.returncode != 0:
                self.last_error = "Asterisk RX channel unavailable"
                self.audit("soft-radio-rx-channel", "start-failed")
            else:
                self.audit("soft-radio-rx-channel", "started")
        except (OSError, subprocess.TimeoutExpired):
            self.last_error = "Asterisk RX channel unavailable"
            self.audit("soft-radio-rx-channel", "start-failed")

    def _handle_asterisk(self, stream, address):
        config = _safe_config()
        if address[0] not in ("127.0.0.1", "::1") or not config.get("enabled"):
            return
        try:
            stream.settimeout(5)
            request = bytearray()
            while b"\r\n\r\n" not in request and len(request) <= 16384:
                chunk = stream.recv(2048)
                if not chunk:
                    raise ConnectionError("incomplete WebSocket handshake")
                request.extend(chunk)
            head = request.decode("iso-8859-1").split("\r\n")
            method, target, _version = head[0].split(" ", 2)
            headers = {}
            for line in head[1:]:
                if ":" in line:
                    key, value = line.split(":", 1)
                    headers[key.strip().lower()] = value.strip()
            expected = base64.b64encode(
                f"{config['media_username']}:{config['media_password']}".encode()).decode()
            if (method != "GET" or urlsplit(target).path != config["media_path"] or
                    not hmac.compare_digest(headers.get("authorization", ""),
                                            "Basic " + expected) or
                    "media" not in headers.get("sec-websocket-protocol", "").split(", ")):
                stream.sendall(b"HTTP/1.1 403 Forbidden\r\nConnection: close\r\n\r\n")
                return
            key = headers.get("sec-websocket-key", "")
            if not key:
                return
            response = ("HTTP/1.1 101 Switching Protocols\r\nUpgrade: websocket\r\n"
                        "Connection: Upgrade\r\nSec-WebSocket-Protocol: media\r\n"
                        f"Sec-WebSocket-Accept: {websocket_accept(key)}\r\n\r\n")
            stream.sendall(response.encode("ascii"))
            media_started = False
            stream.settimeout(1)
            enabled = True
            next_config_check = 0
            while enabled:
                if time.monotonic() >= next_config_check:
                    enabled = _safe_config().get("enabled", False)
                    next_config_check = time.monotonic() + 1
                    if not enabled:
                        break
                try:
                    opcode, payload = read_frame(stream, MAX_ASTERISK_FRAME)
                except socket.timeout:
                    continue
                if opcode == 8:
                    break
                if opcode == 9:
                    stream.sendall(make_frame(10, payload))
                elif opcode == 1:
                    event = json.loads(payload.decode("utf-8"))
                    if (not media_started and event.get("event") == "MEDIA_START" and
                            event.get("format") == "ulaw" and
                            int(event.get("optimal_frame_size", 0)) == 160):
                        media_started = True
                        with self.lock:
                            self.media_connected = True
                        self.audit("soft-radio-rx-media", "connected")
                elif opcode == 2 and media_started:
                    self.broadcast(payload)
                # Text is status from Asterisk. It is never echoed or treated
                # as a command, and this broker never sends control text back.
        except (ConnectionError, OSError, ValueError, UnicodeError):
            pass
        finally:
            with self.lock:
                self.media_connected = False
            self.audit("soft-radio-rx-media", "disconnected")


SOFT_RADIO = SoftRadio()
