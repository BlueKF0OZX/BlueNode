#!/usr/bin/env python3
"""Create or disable the untracked BlueNode Remote Admin credential file."""

import argparse
import json
import os
import pwd
import secrets
import sys
from pathlib import Path

sys.path.insert(0, "/opt/nodesmart/core")
from remote_admin import (hash_password, read_hidden_secret,
                          validate_new_credentials)  # noqa: E402

TARGET = Path("/etc/bluenode/remote-admin.json")


def write_config(data, service_user):
    account = pwd.getpwnam(service_user)
    TARGET.parent.mkdir(mode=0o750, parents=True, exist_ok=True)
    os.chown(TARGET.parent, 0, account.pw_gid)
    temporary = TARGET.with_name(TARGET.name + ".tmp")
    descriptor = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o640)
    with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
        json.dump(data, handle, indent=2)
        handle.write("\n")
        handle.flush()
        os.fsync(handle.fileno())
    os.chown(temporary, 0, account.pw_gid)
    os.chmod(temporary, 0o640)
    os.replace(temporary, TARGET)


def main():
    parser = argparse.ArgumentParser(description="Initialize BlueNode Remote Admin")
    parser.add_argument("mode", choices=("enable", "disable", "status",
                                         "grant-soft-radio-rx",
                                         "revoke-soft-radio-rx"))
    parser.add_argument("--service-user", default=os.environ.get("NODESMART_USER", ""))
    parser.add_argument("--username", default="")
    args = parser.parse_args()
    if os.geteuid() != 0:
        raise SystemExit("Run with sudo")
    if args.mode == "status":
        enabled = False
        try:
            enabled = json.loads(TARGET.read_text(encoding="utf-8")).get("enabled") is True
        except (OSError, ValueError):
            pass
        print("Remote Admin is " + ("enabled" if enabled else "disabled"))
        return
    if args.mode in ("grant-soft-radio-rx", "revoke-soft-radio-rx"):
        try:
            current = json.loads(TARGET.read_text(encoding="utf-8"))
        except (OSError, ValueError) as exc:
            raise SystemExit("Initialize Remote Admin before changing permissions") from exc
        if current.get("enabled") is not True:
            raise SystemExit("Remote Admin must be enabled before granting Soft Radio RX")
        permissions = set(current.get("permissions", []))
        if args.mode == "grant-soft-radio-rx":
            permissions.add("soft_radio_rx")
        else:
            permissions.discard("soft_radio_rx")
        current["permissions"] = sorted(permissions)
        write_config(current, args.service_user)
        print("Soft Radio RX permission " +
              ("granted" if "soft_radio_rx" in permissions else "revoked"))
        return
    if not args.service_user:
        raise SystemExit("Provide --service-user or NODESMART_USER")
    if args.mode == "disable":
        write_config({"enabled": False}, args.service_user)
        print("Remote Admin disabled; active sessions are invalid after web service restart")
        return
    username = args.username.strip() or input("Remote Admin username: ").strip()
    first = read_hidden_secret("Remote Admin password: ")
    second = read_hidden_secret("Confirm password: ")
    try:
        username, first = validate_new_credentials(username, first, second)
    except ValueError as exc:
        raise SystemExit(str(exc)) from exc
    salt, digest = hash_password(first)
    write_config({"enabled": True, "username": username, "password_salt": salt,
                  "password_hash": digest, "password_iterations": 600000,
                  "session_secret": secrets.token_hex(32), "session_seconds": 2592000,
                  "secure_cookie": True, "max_login_attempts": 5,
                  "login_window_seconds": 300, "permissions": []}, args.service_user)
    print("Remote Admin credentials initialized outside Git; restart nodesmart-web.service")


if __name__ == "__main__":
    main()
