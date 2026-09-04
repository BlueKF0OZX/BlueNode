#!/bin/bash
set -euo pipefail

ACTION="${1:-}"
SERVICE_USER="${NODESMART_USER:-${SUDO_USER:-}}"
SUDOERS_FILE=/etc/sudoers.d/bluenode-remote-admin
INITIALIZER=/opt/nodesmart/install/remote-admin-init.py

fail() { printf 'FAIL remote-admin: %s\n' "$1" >&2; exit 1; }
[[ $EUID -eq 0 ]] || fail "run with sudo"
[[ -n "$SERVICE_USER" && "$SERVICE_USER" != root ]] || fail "set NODESMART_USER to the BlueNode service account"
id "$SERVICE_USER" >/dev/null 2>&1 || fail "service account does not exist"

case "$ACTION" in
  enable)
    temporary="$(mktemp)"
    trap 'rm -f "$temporary"' EXIT
    printf '%s ALL=(root) NOPASSWD: /usr/bin/systemctl restart nodesmart.service\n' "$SERVICE_USER" > "$temporary"
    chmod 0440 "$temporary"
    /usr/sbin/visudo -cf "$temporary" >/dev/null || fail "restricted sudo rule is invalid"
    install -o root -g root -m 0440 "$temporary" "$SUDOERS_FILE"
    if ! /usr/bin/python3 "$INITIALIZER" enable --service-user "$SERVICE_USER"; then
      rm -f "$SUDOERS_FILE"
      fail "credential initialization failed; restricted sudo rule rolled back"
    fi
    /usr/bin/systemctl restart nodesmart-web.service
    printf 'PASS remote-admin: enabled; verify only through trusted HTTPS\n'
    ;;
  disable)
    /usr/bin/python3 "$INITIALIZER" disable --service-user "$SERVICE_USER"
    rm -f "$SUDOERS_FILE"
    /usr/sbin/visudo -c >/dev/null || fail "sudoers validation failed after rollback"
    /usr/bin/systemctl restart nodesmart-web.service
    printf 'PASS remote-admin: disabled and optional privilege removed\n'
    ;;
  status)
    /usr/bin/python3 "$INITIALIZER" status
    [[ -f "$SUDOERS_FILE" ]] && printf 'Restricted monitor-restart privilege is installed\n' ||
      printf 'Restricted monitor-restart privilege is absent\n'
    ;;
  grant-soft-radio-rx|revoke-soft-radio-rx)
    /usr/bin/python3 "$INITIALIZER" "$ACTION" --service-user "$SERVICE_USER"
    /usr/bin/systemctl restart nodesmart-web.service
    printf 'PASS remote-admin: permission updated; active sessions invalidated\n'
    ;;
  *) fail "usage: $0 {enable|disable|status|grant-soft-radio-rx|revoke-soft-radio-rx}" ;;
esac
