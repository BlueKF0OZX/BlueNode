#!/bin/bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
INSTALL_ROOT="/opt/nodesmart"
SERVICE_FILE="/etc/systemd/system/nodesmart.service"
WEB_SERVICE_FILE="/etc/systemd/system/nodesmart-web.service"
SUDOERS_FILE="/etc/sudoers.d/nodesmart"

fail() {
  echo "ERROR: $1" >&2
  exit 1
}

if [[ ${EUID} -ne 0 ]]; then
  fail "Run this installer with sudo."
fi

SERVICE_USER="${NODESMART_USER:-${SUDO_USER-}}"

if [[ -z "${SERVICE_USER}" || "${SERVICE_USER}" == "root" ]]; then
  fail "Unable to determine the BlueNode service user. Run with sudo from the intended user account, or set NODESMART_USER."
fi

id "${SERVICE_USER}" >/dev/null 2>&1 || fail "User ${SERVICE_USER} does not exist."
SERVICE_GROUP="$(id -gn "${SERVICE_USER}")"

for cmd in /usr/bin/python3 /usr/sbin/asterisk /usr/bin/systemctl /usr/sbin/visudo; do
  [[ -x "${cmd}" ]] || fail "Required command not found: ${cmd}"
done

[[ -f "${REPO_ROOT}/config/nodesmart.example.json" ]] || fail "Missing config/nodesmart.example.json"
[[ -f "${REPO_ROOT}/systemd/nodesmart.service" ]] || fail "Missing systemd/nodesmart.service"
[[ -f "${REPO_ROOT}/systemd/nodesmart-web.service" ]] || fail "Missing systemd/nodesmart-web.service"
[[ -f "${REPO_ROOT}/install/nodesmart.sudoers.example" ]] || fail "Missing install/nodesmart.sudoers.example"
[[ -f "${REPO_ROOT}/install/remote-access.sh" ]] || fail "Missing install/remote-access.sh"
[[ -f "${REPO_ROOT}/install/remote-access/apache-vhost.conf.template" ]] || fail "Missing remote-access Apache template"
[[ -f "${REPO_ROOT}/install/tailscale-funnel.sh" ]] || fail "Missing install/tailscale-funnel.sh"
[[ -f "${REPO_ROOT}/install/remote-access/apache-funnel-gateway.conf.template" ]] || fail "Missing Funnel gateway template"
[[ -f "${REPO_ROOT}/install/remote-admin-init.py" ]] || fail "Missing Remote Admin initializer"
[[ -f "${REPO_ROOT}/install/remote-admin.sh" ]] || fail "Missing Remote Admin lifecycle helper"
[[ -f "${REPO_ROOT}/install/soft-radio-rx.sh" ]] || fail "Missing Soft Radio RX lifecycle helper"
[[ -f "${REPO_ROOT}/install/soft-radio/websocket-client.conf.template" ]] || fail "Missing Soft Radio RX Asterisk template"

echo "Preparing BlueNode files and directories..."
mkdir -p "${INSTALL_ROOT}"

if [[ "${REPO_ROOT}" != "${INSTALL_ROOT}" ]]; then
  rm -rf "${INSTALL_ROOT}/core" "${INSTALL_ROOT}/web"
  cp -a "${REPO_ROOT}/core" "${INSTALL_ROOT}/core"
  cp -a "${REPO_ROOT}/web" "${INSTALL_ROOT}/web"
  mkdir -p "${INSTALL_ROOT}/config" "${INSTALL_ROOT}/install/helpers" "${INSTALL_ROOT}/install/remote-access" "${INSTALL_ROOT}/install/soft-radio" "${INSTALL_ROOT}/systemd"
  cp -f "${REPO_ROOT}/config/nodesmart.example.json" "${INSTALL_ROOT}/config/"
  cp -f "${REPO_ROOT}/install/nodesmart.sudoers.example" "${INSTALL_ROOT}/install/"
  install -m 0755 "${REPO_ROOT}/install/remote-access.sh" "${INSTALL_ROOT}/install/remote-access.sh"
  install -m 0755 "${REPO_ROOT}/install/tailscale-funnel.sh" "${INSTALL_ROOT}/install/tailscale-funnel.sh"
  install -m 0755 "${REPO_ROOT}/install/remote-admin-init.py" "${INSTALL_ROOT}/install/remote-admin-init.py"
  install -m 0755 "${REPO_ROOT}/install/remote-admin.sh" "${INSTALL_ROOT}/install/remote-admin.sh"
  install -m 0755 "${REPO_ROOT}/install/soft-radio-rx.sh" "${INSTALL_ROOT}/install/soft-radio-rx.sh"
  cp -f "${REPO_ROOT}/install/remote-access.conf.example" "${INSTALL_ROOT}/install/"
  cp -f "${REPO_ROOT}/install/remote-access/apache-vhost.conf.template" "${INSTALL_ROOT}/install/remote-access/"
  cp -f "${REPO_ROOT}/install/remote-access/apache-funnel-gateway.conf.template" "${INSTALL_ROOT}/install/remote-access/"
  cp -f "${REPO_ROOT}/install/soft-radio/websocket-client.conf.template" "${INSTALL_ROOT}/install/soft-radio/"
  cp -a "${REPO_ROOT}/install/helpers/." "${INSTALL_ROOT}/install/helpers/"
  cp -f "${REPO_ROOT}/systemd/nodesmart.service" "${INSTALL_ROOT}/systemd/"
  cp -f "${REPO_ROOT}/systemd/nodesmart-web.service" "${INSTALL_ROOT}/systemd/"
fi

mkdir -p "${INSTALL_ROOT}/events" "${INSTALL_ROOT}/history" "${INSTALL_ROOT}/logs" "${INSTALL_ROOT}/state"

echo "Installing helper commands..."
for helper in dodropin dodropoff skywarnon skywarnoff; do
  src="${INSTALL_ROOT}/install/helpers/${helper}"
  [[ -f "${src}" ]] || fail "Missing helper: ${src}"
  install -o root -g root -m 0755 "${src}" "/usr/local/bin/${helper}"
done

echo "Installing restricted sudo permissions..."
tmp_sudoers="$(mktemp)"
tmp_service=""
tmp_web_service=""
trap 'rm -f "${tmp_sudoers:-}" "${tmp_service:-}" "${tmp_web_service:-}"' EXIT
sed "s/NODESMART_USER/${SERVICE_USER}/g" "${INSTALL_ROOT}/install/nodesmart.sudoers.example" > "${tmp_sudoers}"
/usr/sbin/visudo -cf "${tmp_sudoers}" >/dev/null || fail "Generated sudoers file failed validation."
install -o root -g root -m 0440 "${tmp_sudoers}" "${SUDOERS_FILE}"

echo "Installing systemd services..."
tmp_service="$(mktemp)"
sed "s/NODESMART_USER/${SERVICE_USER}/g" "${INSTALL_ROOT}/systemd/nodesmart.service" > "${tmp_service}"
install -o root -g root -m 0644 "${tmp_service}" "${SERVICE_FILE}"
tmp_web_service="$(mktemp)"
sed "s/NODESMART_USER/${SERVICE_USER}/g" "${INSTALL_ROOT}/systemd/nodesmart-web.service" > "${tmp_web_service}"
install -o root -g root -m 0644 "${tmp_web_service}" "${WEB_SERVICE_FILE}"
/usr/bin/systemctl daemon-reload

if [[ ! -f "${INSTALL_ROOT}/config/nodesmart.json" ]]; then
  cp "${INSTALL_ROOT}/config/nodesmart.example.json" "${INSTALL_ROOT}/config/nodesmart.json"
  chown "${SERVICE_USER}:${SERVICE_GROUP}" "${INSTALL_ROOT}/config/nodesmart.json"
  chmod 0644 "${INSTALL_ROOT}/config/nodesmart.json"
  chown -R "${SERVICE_USER}:${SERVICE_GROUP}" "${INSTALL_ROOT}"
  echo
  echo "BlueNode configuration created:"
  echo "  ${INSTALL_ROOT}/config/nodesmart.json"
  echo "Edit the node number, callsign, and friendly nodes, then rerun this installer."
  echo "BlueNode has NOT been started yet."
  exit 0
fi

chown -R "${SERVICE_USER}:${SERVICE_GROUP}" "${INSTALL_ROOT}"
find "${INSTALL_ROOT}" -type d -exec chmod 0755 {} \;

if [[ ! -e "/usr/local/bin/SkywarnPlus/SkyControl.py" ]]; then
  echo "WARNING: SkywarnPlus was not detected. Skywarn controls will not work until it is installed."
fi

echo "Validating Python files..."
/usr/bin/python3 -m py_compile "${INSTALL_ROOT}/core/config.py" "${INSTALL_ROOT}/core/monitor.py" || fail "Python syntax validation failed."

echo "Configuring dashboard firewall access..."
WEB_PORT="$("/usr/bin/python3" -c 'import json,sys; print(json.load(open(sys.argv[1]))["web"]["port"])' "${INSTALL_ROOT}/config/nodesmart.json")"

[[ "${WEB_PORT}" =~ ^[0-9]+$ ]] || fail "Invalid web.port in nodesmart.json"
(( WEB_PORT >= 1 && WEB_PORT <= 65535 )) || fail "web.port must be between 1 and 65535"

if command -v firewall-cmd >/dev/null 2>&1 && firewall-cmd --state >/dev/null 2>&1; then
  DEFAULT_INTERFACE="$(ip route show default 2>/dev/null | awk 'NR==1 {print $5}')"
  FIREWALL_ZONE=""

  if [[ -n "${DEFAULT_INTERFACE}" ]]; then
    FIREWALL_ZONE="$(firewall-cmd --get-zone-of-interface="${DEFAULT_INTERFACE}" 2>/dev/null || true)"
  fi

  if [[ -z "${FIREWALL_ZONE}" || "${FIREWALL_ZONE}" == "no zone" ]]; then
    FIREWALL_ZONE="$(firewall-cmd --get-default-zone)"
  fi

  firewall-cmd --permanent --zone="${FIREWALL_ZONE}" --add-port="${WEB_PORT}/tcp" >/dev/null
  firewall-cmd --reload >/dev/null
  echo "Allowed BlueNode dashboard TCP port ${WEB_PORT} in firewalld zone ${FIREWALL_ZONE}."
else
  echo "WARNING: Active firewalld was not detected."
  echo "Ensure TCP port ${WEB_PORT} is allowed on the host firewall for dashboard access."
fi

echo "Enabling and starting BlueNode..."
/usr/bin/systemctl enable nodesmart nodesmart-web
/usr/bin/systemctl restart nodesmart nodesmart-web

if /usr/bin/systemctl is-active --quiet nodesmart && /usr/bin/systemctl is-active --quiet nodesmart-web; then
  echo "BlueNode installation complete."
else
  echo "BlueNode is installed but the service is not running." >&2
  /usr/bin/systemctl status nodesmart --no-pager || true
  exit 1
fi
