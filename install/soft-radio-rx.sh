#!/bin/bash
set -euo pipefail

ACTION="${1:-}"
SERVICE_USER="${NODESMART_USER:-${SUDO_USER:-}}"
CONFIG=/etc/bluenode/soft-radio.json
STAGED_ASTERISK=/etc/bluenode/soft-radio-websocket-client.conf
SUDOERS_FILE=/etc/sudoers.d/bluenode-soft-radio-rx
START_HELPER=/usr/local/bin/bluenode-soft-radio-rx-start

fail() { printf 'FAIL soft-radio-rx: %s\n' "$1" >&2; exit 1; }
[[ $EUID -eq 0 ]] || fail "run with sudo"
[[ -n "$SERVICE_USER" && "$SERVICE_USER" != root ]] || fail "set NODESMART_USER"
id "$SERVICE_USER" >/dev/null 2>&1 || fail "service account does not exist"
SERVICE_GROUP="$(id -gn "$SERVICE_USER")"

write_enabled() {
  local value="$1" start="$2" temporary
  temporary="$(mktemp)"
  trap 'rm -f "$temporary"' RETURN
  /usr/bin/python3 - "$CONFIG" "$temporary" "$value" "$start" <<'PY'
import json, os, sys
source, target, enabled, start = sys.argv[1:]
with open(source, encoding="utf-8") as handle:
    data = json.load(handle)
data["enabled"] = enabled == "true"
data["start_channel"] = start == "true"
with open(target, "w", encoding="utf-8") as handle:
    json.dump(data, handle, indent=2)
    handle.write("\n")
    handle.flush()
    os.fsync(handle.fileno())
PY
  install -o root -g "$SERVICE_GROUP" -m 0640 "$temporary" "$CONFIG"
}

wait_for_broker() {
  local attempt
  for attempt in {1..50}; do
    if /usr/bin/python3 - "$CONFIG" <<'PY'
import json, socket, sys
with open(sys.argv[1], encoding="utf-8") as handle:
    config = json.load(handle)
host = config["listen_host"]
port = int(config["listen_port"])
try:
    with socket.create_connection((host, port), timeout=0.1):
        pass
except OSError:
    raise SystemExit(1)
PY
    then
      return 0
    fi
    sleep 0.1
  done
  return 1
}

require_remote_admin_permission() {
  /usr/bin/python3 -c 'import json; c=json.load(open("/etc/bluenode/remote-admin.json")); assert c.get("enabled") and "soft_radio_rx" in c.get("permissions",[])' \
    || fail "Remote Admin and soft_radio_rx permission are required"
}

module_running() {
  /usr/sbin/asterisk -rx "module show like $1" | /usr/bin/awk -v name="$1" \
    '$1 == name && $(NF-2) ~ /^[0-9]+$/ && $(NF-1) == "Running" { found=1 } END { exit !found }'
}

case "$ACTION" in
  prepare)
    [[ $# -eq 2 && "$2" =~ ^[0-9]{1,10}$ ]] || fail "usage: $0 prepare LOCAL_NODE"
    command -v openssl >/dev/null 2>&1 || fail "openssl is required to generate credentials"
    install -d -o root -g "$SERVICE_GROUP" -m 0750 /etc/bluenode
    [[ ! -e "$CONFIG" ]] || fail "$CONFIG already exists; inspect it first"
    media_user="bluenode_rx_$(openssl rand -hex 8)"
    media_secret="$(openssl rand -base64 36 | tr -d '\n')"
    /usr/bin/python3 - "$CONFIG" "$2" "$media_user" "$media_secret" <<'PY'
import json, os, sys
target, node, username, credential_secret = sys.argv[1:]
data = {"enabled": False, "listen_host": "127.0.0.1", "listen_port": 8767,
        "media_path": "/asterisk-media", "media_username": username,
        "media_password": credential_secret, "connection_name": "bluenode_soft_radio_rx",
        "local_node": node, "ticket_seconds": 30, "buffer_frames": 12,
        "start_channel": False}
fd = os.open(target, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o640)
with os.fdopen(fd, "w", encoding="utf-8") as handle:
    json.dump(data, handle, indent=2)
    handle.write("\n")
PY
    chown root:"$SERVICE_GROUP" "$CONFIG"
    temporary="$(mktemp)"
    trap 'rm -f "$temporary"' EXIT
    sed -e "s/@MEDIA_USERNAME@/$media_user/" -e "s#@MEDIA_PASSWORD@#$media_secret#" \
      /opt/nodesmart/install/soft-radio/websocket-client.conf.template > "$temporary"
    ASTERISK_GROUP="$(id -gn asterisk 2>/dev/null || printf asterisk)"
    getent group "$ASTERISK_GROUP" >/dev/null || fail "Asterisk group is unavailable"
    install -o root -g "$ASTERISK_GROUP" -m 0640 "$temporary" "$STAGED_ASTERISK"
    install -o root -g root -m 0755 \
      /opt/nodesmart/install/helpers/bluenode-soft-radio-rx-start "$START_HELPER"
    sudoers_temporary="$(mktemp)"
    printf '%s ALL=(root) NOPASSWD: %s\n' "$SERVICE_USER" "$START_HELPER" > "$sudoers_temporary"
    chmod 0440 "$sudoers_temporary"
    /usr/sbin/visudo -cf "$sudoers_temporary" >/dev/null || fail "restricted sudo rule is invalid"
    install -o root -g root -m 0440 "$sudoers_temporary" "$SUDOERS_FILE"
    rm -f "$sudoers_temporary"
    printf 'PASS soft-radio-rx: prepared disabled external configuration\n'
    printf 'Asterisk client stanza staged at %s; no Asterisk configuration was changed\n' "$STAGED_ASTERISK"
    ;;
  enable)
    [[ -f "$CONFIG" ]] || fail "run prepare first"
    require_remote_admin_permission
    module_running chan_websocket.so \
      || fail "chan_websocket is not loaded; activation requires explicit operator approval"
    module_running res_websocket_client.so \
      || fail "res_websocket_client is not loaded; activation requires explicit operator approval"
    grep -q '^\[bluenode_soft_radio_rx\]' /etc/asterisk/websocket_client.conf \
      || fail "the staged fixed client stanza has not been installed"
    write_enabled true true
    /usr/bin/systemctl restart nodesmart-web.service
    /usr/bin/systemctl is-active --quiet nodesmart-web.service || fail "web service did not restart"
    printf 'PASS soft-radio-rx: RX-only broker enabled\n'
    ;;
  enable-broker)
    [[ -f "$CONFIG" ]] || fail "run prepare first"
    require_remote_admin_permission
    safety_baseline="$(mktemp)"
    trap 'rm -f "$safety_baseline"' EXIT
    local_node=$(/usr/bin/python3 -c 'import json; print(json.load(open("/etc/bluenode/soft-radio.json"))["local_node"])')
    /usr/bin/python3 /opt/nodesmart/core/soft_radio_safety.py snapshot \
      --node "$local_node" > "$safety_baseline"
    write_enabled true false
    /usr/bin/systemctl restart nodesmart-web.service
    if ! wait_for_broker; then
      write_enabled false false
      /usr/bin/systemctl restart nodesmart-web.service || true
      fail "loopback RX broker did not become ready; Soft Radio was disabled"
    fi
    if ! /usr/bin/python3 /opt/nodesmart/core/soft_radio_safety.py verify \
        --node "$local_node" --baseline "$safety_baseline"; then
      write_enabled false false
      /usr/bin/systemctl restart nodesmart-web.service || true
      fail "broker-only Asterisk safety gate failed; Soft Radio was disabled"
    fi
    /usr/bin/systemctl is-active --quiet nodesmart-web.service \
      || fail "web service is not active after broker readiness check"
    printf 'PASS soft-radio-rx: loopback RX broker ready; channel origination disabled\n'
    ;;
  disable)
    [[ -f "$CONFIG" ]] || fail "configuration does not exist"
    write_enabled false false
    /usr/bin/systemctl restart nodesmart-web.service
    /usr/bin/systemctl is-active --quiet nodesmart-web.service || fail "web service did not restart"
    printf 'PASS soft-radio-rx: disabled; browser and Asterisk media sockets closed\n'
    ;;
  status)
    [[ -f "$CONFIG" ]] || { printf 'Soft Radio RX is unconfigured and disabled\n'; exit 0; }
    /usr/bin/python3 -c 'import json; print("Soft Radio RX is " + ("enabled" if json.load(open("/etc/bluenode/soft-radio.json")).get("enabled") else "disabled"))'
    ;;
  *) fail "usage: $0 {prepare LOCAL_NODE|enable-broker|enable|disable|status}" ;;
esac
