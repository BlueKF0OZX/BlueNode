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
                          validate_new_credentials, INTENT_CONTENT, _safe_config)  # noqa: E402

TARGET = Path("/etc/bluenode/remote-admin.json")


def preserve_intent(service_user):
    """Sticky root-owned marker: missing credentials must not enable local mode."""
    account = pwd.getpwnam(service_user)
    TARGET.parent.mkdir(mode=0o750, parents=True, exist_ok=True)
    if TARGET.parent.is_symlink():
        raise SystemExit("Unsafe Remote Admin directory")
    info = TARGET.parent.stat()
    if info.st_uid != 0 or info.st_mode & 0o022:
        raise SystemExit("Unsafe Remote Admin directory ownership/permissions")
    os.chown(TARGET.parent, 0, account.pw_gid)
    marker = TARGET.with_suffix(".intent")
    # Exclusive temporary creation; never follow a pre-created temporary symlink.
    import tempfile
    descriptor, name = tempfile.mkstemp(prefix=".remote-admin-intent-", dir=TARGET.parent)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
            handle.write(INTENT_CONTENT)
            handle.flush()
            os.fchown(handle.fileno(), 0, account.pw_gid)
            os.fchmod(handle.fileno(), 0o640)
            os.fsync(handle.fileno())
        os.replace(name, marker)
        directory = os.open(TARGET.parent, os.O_RDONLY | os.O_DIRECTORY)
        try:
            os.fsync(directory)
        finally:
            os.close(directory)
    finally:
        if os.path.exists(name):
            os.unlink(name)


def write_config(data, service_user):
    preserve_intent(service_user)
    account = pwd.getpwnam(service_user)
    TARGET.parent.mkdir(mode=0o750, parents=True, exist_ok=True)
    os.chown(TARGET.parent, 0, account.pw_gid)
    import tempfile
    descriptor, name = tempfile.mkstemp(prefix=".remote-admin-config-", dir=TARGET.parent)
    temporary = Path(name)
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
    parser.add_argument("mode", choices=("enable", "disable", "status", "migrate-intent",
                                         "grant-soft-radio-rx",
                                         "revoke-soft-radio-rx"))
    parser.add_argument("--service-user", default=os.environ.get("NODESMART_USER", ""))
    parser.add_argument("--username", default="")
    args = parser.parse_args()
    if os.geteuid() != 0:
        raise SystemExit("Run with sudo")
    if args.mode == "status":
        print("Remote Admin state: " + _safe_config()["state"])
        return
    if args.mode == "migrate-intent":
        # Called by the supported installer before starting the new backend.
        if TARGET.exists() or TARGET.is_symlink() or TARGET.with_suffix(".intent").exists():
            preserve_intent(args.service_user)
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
    preserve_intent(args.service_user)  # Persist attempted enablement before prompting.
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
