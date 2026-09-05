#!/usr/bin/env python3
"""Deny-by-default application authentication and fixed Remote Admin actions."""

import hashlib
import hmac
import json
import os
import secrets
import subprocess
import threading
import time
from collections import defaultdict, deque
from datetime import datetime, timezone
from pathlib import Path


CONFIG_FILE = Path(os.environ.get(
    "BLUENODE_REMOTE_ADMIN_CONFIG", "/etc/bluenode/remote-admin.json"))
AUDIT_FILE = Path(os.environ.get(
    "BLUENODE_ADMIN_AUDIT_FILE", "/opt/nodesmart/logs/admin-audit.jsonl"))
APP_ROOT = Path(os.environ.get("BLUENODE_APP_ROOT", "/opt/nodesmart"))
MAX_BODY_BYTES = 16384
MAX_LOG_LINES = 200
ALLOWED_LOG_SOURCES = {
    "bluenode": ("nodesmart.service", "nodesmart-web.service"),
    "asterisk": ("asterisk.service",),
}
ALLOWED_ACTIONS = {
    "restart-monitor", "restart-asterisk", "refresh-diagnostics",
}
ALLOWED_PERMISSIONS = {"soft_radio_rx"}


def _utc_now():
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _safe_config():
    """Return validated public settings, never secrets; disabled on any error."""
    base = {"enabled": False, "session_seconds": 1800, "secure_cookie": True,
            "max_login_attempts": 5, "login_window_seconds": 300}
    try:
        if CONFIG_FILE.is_symlink() or (os.name == "posix" and CONFIG_FILE.stat().st_mode & 0o007):
            return base
        raw = json.loads(CONFIG_FILE.read_text(encoding="utf-8"))
        if not isinstance(raw, dict) or raw.get("enabled") is not True:
            return base
        required = ("username", "password_salt", "password_hash", "session_secret")
        if any(not isinstance(raw.get(key), str) or not raw[key] for key in required):
            return base
        iterations = int(raw.get("password_iterations", 600000))
        session_seconds = int(raw.get("session_seconds", 1800))
        attempts = int(raw.get("max_login_attempts", 5))
        window = int(raw.get("login_window_seconds", 300))
        permissions = raw.get("permissions", [])
        if not 200000 <= iterations <= 5000000:
            return base
        if not 300 <= session_seconds <= 86400 or not 1 <= attempts <= 20:
            return base
        if not 30 <= window <= 3600:
            return base
        if (not isinstance(permissions, list) or
                any(item not in ALLOWED_PERMISSIONS for item in permissions)):
            return base
        base.update(raw)
        base.update({"password_iterations": iterations, "session_seconds": session_seconds,
                     "max_login_attempts": attempts, "login_window_seconds": window,
                     "permissions": tuple(permissions)})
        return base
    except (OSError, ValueError, TypeError, json.JSONDecodeError):
        return base


def hash_password(password, salt=None, iterations=600000):
    salt_bytes = secrets.token_bytes(24) if salt is None else bytes.fromhex(salt)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt_bytes,
                                 int(iterations))
    return salt_bytes.hex(), digest.hex()


def verify_password(password, config):
    try:
        _, candidate = hash_password(password, config["password_salt"],
                                     config["password_iterations"])
        return hmac.compare_digest(candidate, config["password_hash"])
    except (KeyError, TypeError, ValueError):
        return False


def validate_new_credentials(username, first, second):
    """Validate interactive credentials without retaining terminal CR residue."""
    normalized_username = str(username).strip()
    if (not normalized_username or len(normalized_username) > 64 or
            not all(char.isalnum() or char in "._@-" for char in normalized_username)):
        raise ValueError("Username contains unsupported characters")
    # getpass normally removes the line terminator. Some nested Windows SSH
    # pseudo-terminal paths can leave a single carriage return on one read.
    # It is terminal framing, not an intentional password character.
    first = str(first).removesuffix("\r")
    second = str(second).removesuffix("\r")
    if not hmac.compare_digest(first, second):
        raise ValueError("Password confirmation does not match")
    if len(first) < 14:
        raise ValueError("Password must contain at least 14 characters")
    if any(ord(char) < 32 or ord(char) == 127 for char in first):
        raise ValueError("Password contains an unsupported control character")
    return normalized_username, first


def read_hidden_secret(prompt, tty_path="/dev/tty"):
    """Read a secret without canonical PTY editing, echo, logging, or argv use."""
    if os.name != "posix":
        import getpass
        return getpass.getpass(prompt)
    import termios
    descriptor = os.open(tty_path, os.O_RDWR | getattr(os, "O_NOCTTY", 0))
    original = termios.tcgetattr(descriptor)
    changed = termios.tcgetattr(descriptor)
    changed[3] &= ~(termios.ECHO | termios.ICANON)
    changed[6][termios.VMIN] = 1
    changed[6][termios.VTIME] = 0
    secret = bytearray()
    try:
        termios.tcsetattr(descriptor, termios.TCSANOW, changed)
        os.write(descriptor, prompt.encode("utf-8"))
        while True:
            chunk = os.read(descriptor, 1)
            if not chunk:
                raise EOFError("Credential input ended unexpectedly")
            value = chunk[0]
            if value in (10, 13):
                break
            if value in (8, 127):
                if secret:
                    removed = secret.pop()
                    if removed & 0xC0 == 0x80:
                        while secret and secret[-1] & 0xC0 == 0x80:
                            secret.pop()
                        if secret:
                            secret.pop()
                continue
            if len(secret) >= 4096:
                raise ValueError("Credential input exceeds the supported limit")
            secret.append(value)
    finally:
        termios.tcsetattr(descriptor, termios.TCSANOW, original)
        try:
            os.write(descriptor, b"\n")
        finally:
            os.close(descriptor)
    try:
        return secret.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise ValueError("Credential input is not valid UTF-8") from exc


class RemoteAdmin:
    def __init__(self, clock=time.time, runner=subprocess.run):
        self.clock = clock
        self.runner = runner
        self.lock = threading.RLock()
        self.sessions = {}
        self.login_attempts = defaultdict(deque)

    def public_state(self, cookie_token=None):
        config = _safe_config()
        session = self.authenticate(cookie_token, config)
        return {"enabled": config["enabled"], "authenticated": session is not None,
                "csrf_token": session["csrf"] if session else None,
                "expires_at": session["expires_at"] if session else None}

    def _purge(self):
        now = self.clock()
        for token in list(self.sessions):
            if self.sessions[token]["expires"] <= now:
                del self.sessions[token]

    def authenticate(self, token, config=None):
        config = config or _safe_config()
        if not config["enabled"] or not token:
            return None
        with self.lock:
            self._purge()
            session = self.sessions.get(token)
            if not session:
                return None
            return {"csrf": session["csrf"], "expires_at": session["expires_at"],
                    "permissions": tuple(config.get("permissions", ()))}

    def has_permission(self, token, permission):
        session = self.authenticate(token)
        return bool(session and permission in session.get("permissions", ()))

    def login(self, username, password, client_key):
        config = _safe_config()
        if not config["enabled"]:
            self.audit("login", "disabled")
            return 404, {"ok": False, "error": "Remote Admin is disabled"}, None
        now = self.clock()
        key = str(client_key)[:128]
        with self.lock:
            attempts = self.login_attempts[key]
            while attempts and attempts[0] <= now - config["login_window_seconds"]:
                attempts.popleft()
            if len(attempts) >= config["max_login_attempts"]:
                self.audit("login", "rate_limited")
                return 429, {"ok": False, "error": "Too many authentication attempts"}, None
        valid_user = hmac.compare_digest(str(username), config["username"])
        valid_password = verify_password(str(password), config)
        if not (valid_user and valid_password):
            with self.lock:
                self.login_attempts[key].append(now)
            self.audit("login", "rejected")
            return 401, {"ok": False, "error": "Invalid credentials"}, None
        token, csrf = secrets.token_urlsafe(32), secrets.token_urlsafe(24)
        expires = now + config["session_seconds"]
        with self.lock:
            self.login_attempts.pop(key, None)
            self.sessions[token] = {"csrf": csrf, "expires": expires,
                                    "expires_at": datetime.fromtimestamp(
                                        expires, timezone.utc).isoformat(timespec="seconds")}
        self.audit("login", "success")
        return 200, {"ok": True, "csrf_token": csrf,
                     "expires_at": self.sessions[token]["expires_at"]}, token

    def logout(self, token):
        with self.lock:
            existed = bool(token and self.sessions.pop(token, None))
        self.audit("logout", "success" if existed else "no_session")

    def csrf_valid(self, token, csrf):
        session = self.authenticate(token)
        return bool(session and csrf and hmac.compare_digest(session["csrf"], str(csrf)))

    def audit(self, action, outcome):
        record = json.dumps({"timestamp": _utc_now(), "action": str(action)[:64],
                             "outcome": str(outcome)[:64]}, separators=(",", ":"))
        try:
            AUDIT_FILE.parent.mkdir(parents=True, exist_ok=True)
            with self.lock, AUDIT_FILE.open("a", encoding="utf-8") as handle:
                handle.write(record + "\n")
        except OSError:
            pass

    def status(self):
        return {
            "ok": True,
            "services": {
                "monitor": self._service_active("nodesmart.service"),
                "web": self._service_active("nodesmart-web.service"),
                "asterisk": self._asterisk_reachable(),
            },
            "version": self._version(),
            "actions": sorted(ALLOWED_ACTIONS),
        }

    def _run(self, command, timeout=15):
        try:
            return self.runner(command, capture_output=True, text=True, timeout=timeout)
        except (OSError, subprocess.TimeoutExpired) as exc:
            return type("Failed", (), {"returncode": 1, "stdout": "", "stderr": str(exc)})()

    def _service_active(self, unit):
        result = self._run(["systemctl", "is-active", unit], 5)
        return {"active": result.returncode == 0 and result.stdout.strip() == "active"}

    def _asterisk_reachable(self):
        result = self._run(["sudo", "-n", "/usr/local/sbin/bluenode-asterisk", "-rx", "core show uptime seconds"], 8)
        return {"active": result.returncode == 0}

    def _version(self):
        result = self._run(["git", "-C", str(APP_ROOT), "rev-parse", "HEAD"], 5)
        commit = result.stdout.strip() if result.returncode == 0 else "unavailable"
        return {"commit": commit if len(commit) == 40 else "unavailable"}

    def logs(self, source, lines):
        if source not in ALLOWED_LOG_SOURCES:
            return 400, {"ok": False, "error": "Log source is not permitted"}
        try:
            count = int(lines)
        except (TypeError, ValueError):
            return 400, {"ok": False, "error": "Invalid line count"}
        if not 1 <= count <= MAX_LOG_LINES:
            return 400, {"ok": False, "error": "Line count is outside the allowed range"}
        command = ["journalctl", "--no-pager", "--output=short-iso", "-n", str(count)]
        for unit in ALLOWED_LOG_SOURCES[source]:
            command.extend(["-u", unit])
        result = self._run(command, 10)
        outcome = "success" if result.returncode == 0 else "failure"
        self.audit("view-logs-" + source, outcome)
        if result.returncode != 0:
            return 500, {"ok": False, "error": "Unable to retrieve permitted logs"}
        return 200, {"ok": True, "source": source,
                     "lines": result.stdout.splitlines()[-count:]}

    def action(self, action, payload):
        if action not in ALLOWED_ACTIONS:
            self.audit("invalid-action", "rejected")
            return 403, {"ok": False, "error": "Administrative action is not permitted"}
        if set(payload) - ({"action", "confirmation"} if action == "restart-asterisk" else {"action"}):
            self.audit(action, "invalid_parameters")
            return 400, {"ok": False, "error": "Unexpected parameters"}
        if action == "restart-asterisk":
            if payload.get("confirmation") != "RESTART ASTERISK":
                return 400, {"ok": False, "error": "Explicit confirmation is required"}
            command = ["sudo", "-n", "systemctl", "restart", "asterisk"]
        elif action == "restart-monitor":
            command = ["sudo", "-n", "systemctl", "restart", "nodesmart.service"]
        else:
            # Fixed lightweight connectivity refresh; no recovery or service action.
            command = ["/usr/bin/python3", str(APP_ROOT / "core" / "connectivity.py")]
        result = self._run(command, 30)
        verified = False
        if result.returncode == 0:
            verified = (self._asterisk_reachable()["active"] if action == "restart-asterisk"
                        else self._service_active("nodesmart.service")["active"]
                        if action == "restart-monitor" else True)
        outcome = "success" if verified else "failure"
        self.audit(action, outcome)
        status = 200 if verified else 500
        return status, {"ok": verified, "action": action, "outcome": outcome,
                        "message": "Action completed and health was verified" if verified
                        else "Action failed or post-action verification did not pass"}


ADMIN = RemoteAdmin()
