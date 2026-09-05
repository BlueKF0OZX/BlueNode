#!/bin/bash
set -euo pipefail
umask 027
export PATH=/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin

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
[[ "$SERVICE_USER" =~ ^[a-z_][a-z0-9_-]*[$]?$ ]] || fail "Unsupported service user name"
[[ "$SERVICE_GROUP" =~ ^[a-z_][a-z0-9_-]*[$]?$ ]] || fail "Unsupported service group name"

for cmd in /usr/bin/python3 /usr/sbin/asterisk /usr/bin/systemctl /usr/sbin/visudo /usr/bin/sudo; do
  [[ -x "${cmd}" ]] || fail "Required command not found: ${cmd}"
done

for cmd in ip ping getent; do
  command -v "$cmd" >/dev/null || fail "Required command not found: $cmd (install iproute2, iputils-ping, libc-bin)"
done
[[ -f "$REPO_ROOT/install/validate-config.py" ]] || fail "Missing config validator"

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
[[ -f "${REPO_ROOT}/install/soft-radio-transaction.sh" ]] || fail "Missing Soft Radio RX transaction helper"
[[ -f "${REPO_ROOT}/install/soft-radio/websocket-client.conf.template" ]] || fail "Missing Soft Radio RX Asterisk template"

# Validate the complete public source before replacing any installed files.
/usr/bin/python3 - "$REPO_ROOT" <<'PY'
import ast, pathlib, sys
root = pathlib.Path(sys.argv[1])
for directory in ('core', 'web', 'install/helpers'):
    if not (root / directory).is_dir():
        raise SystemExit('Missing source directory: ' + directory)
for source in [*(root / 'core').glob('*.py'), *(root / 'install').glob('*.py'),
               root / 'install/helpers/bluenode-asterisk']:
    ast.parse(source.read_text(), filename=str(source))
for name in ('dodropin', 'dodropoff', 'skywarnon', 'skywarnoff', 'bluenode-asterisk'):
    if not (root / 'install/helpers' / name).is_file():
        raise SystemExit('Missing helper: ' + name)
for name in ('install/remote-access.conf.example', 'web/index.html'):
    if not (root / name).is_file():
        raise SystemExit('Missing source: ' + name)
PY

# First pass only prepares configuration. No units, privileges, or services yet.
if [[ ! -f "$INSTALL_ROOT/config/nodesmart.json" ]]; then
  install -d -o root -g "$SERVICE_GROUP" -m 0750 "$INSTALL_ROOT" "$INSTALL_ROOT/config"
  install -o root -g "$SERVICE_GROUP" -m 0640 \
    "$REPO_ROOT/config/nodesmart.example.json" "$INSTALL_ROOT/config/nodesmart.json"
  echo "Configuration created: $INSTALL_ROOT/config/nodesmart.json"
  echo "Edit with sudo: set your node and callsign; choose a trusted listener address."
  echo "Rerun this installer. BlueNode has NOT been started yet."
  exit 0
fi

/usr/bin/python3 "$REPO_ROOT/install/validate-config.py" "$INSTALL_ROOT/config/nodesmart.json"

echo "Installing restricted sudo permissions..."
tmp_sudoers="$(mktemp)"
tmp_service=""
tmp_web_service=""
staging=""
cleanup() {
  rm -f "${tmp_sudoers:-}" "${tmp_service:-}" "${tmp_web_service:-}"
  if [[ -n "$staging" && "$staging" == "$INSTALL_ROOT"/.install.* ]]; then
    rm -rf -- "$staging"
  fi
}
trap cleanup EXIT
sed "s/NODESMART_USER/${SERVICE_USER}/g" "${REPO_ROOT}/install/nodesmart.sudoers.example" > "${tmp_sudoers}"
/usr/sbin/visudo -cf "${tmp_sudoers}" >/dev/null || fail "Generated sudoers file failed validation."

echo "Preparing BlueNode files and directories..."
mkdir -p "${INSTALL_ROOT}"

if [[ "${REPO_ROOT}" != "${INSTALL_ROOT}" ]]; then
  # Copy both trees completely before replacing the existing application.
  staging="$(mktemp -d "$INSTALL_ROOT/.install.XXXXXXXX")"
  cp -a "$REPO_ROOT/core" "$staging/core"
  cp -a "$REPO_ROOT/web" "$staging/web"
  rm -rf "${INSTALL_ROOT}/core" "${INSTALL_ROOT}/web"
  mv "$staging/core" "$INSTALL_ROOT/core"
  mv "$staging/web" "$INSTALL_ROOT/web"
  rmdir "$staging"
  mkdir -p "${INSTALL_ROOT}/config" "${INSTALL_ROOT}/install/helpers" "${INSTALL_ROOT}/install/remote-access" "${INSTALL_ROOT}/install/soft-radio" "${INSTALL_ROOT}/systemd"
  cp -f "${REPO_ROOT}/config/nodesmart.example.json" "${INSTALL_ROOT}/config/"
  cp -f "${REPO_ROOT}/install/nodesmart.sudoers.example" "${INSTALL_ROOT}/install/"
  install -m 0755 "${REPO_ROOT}/install/remote-access.sh" "${INSTALL_ROOT}/install/remote-access.sh"
  install -m 0755 "${REPO_ROOT}/install/tailscale-funnel.sh" "${INSTALL_ROOT}/install/tailscale-funnel.sh"
  install -m 0755 "${REPO_ROOT}/install/remote-admin-init.py" "${INSTALL_ROOT}/install/remote-admin-init.py"
  install -m 0755 "${REPO_ROOT}/install/remote-admin.sh" "${INSTALL_ROOT}/install/remote-admin.sh"
  install -m 0755 "${REPO_ROOT}/install/soft-radio-rx.sh" "${INSTALL_ROOT}/install/soft-radio-rx.sh"
  install -m 0755 "${REPO_ROOT}/install/soft-radio-transaction.sh" "${INSTALL_ROOT}/install/soft-radio-transaction.sh"
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
install -d -o root -g root -m 0755 /usr/local/sbin
install -o root -g root -m 0755 "$INSTALL_ROOT/install/helpers/bluenode-asterisk" /usr/local/sbin/bluenode-asterisk
for helper in dodropin dodropoff skywarnon skywarnoff; do
  src="${INSTALL_ROOT}/install/helpers/${helper}"
  [[ -f "${src}" ]] || fail "Missing helper: ${src}"
  install -o root -g root -m 0755 "${src}" "/usr/local/bin/${helper}"
done

install -o root -g root -m 0440 "${tmp_sudoers}" "${SUDOERS_FILE}"

echo "Installing systemd services..."
tmp_service="$(mktemp)"
sed -e "s/NODESMART_USER/${SERVICE_USER}/g" -e "s/NODESMART_GROUP/${SERVICE_GROUP}/g" "${INSTALL_ROOT}/systemd/nodesmart.service" > "${tmp_service}"
install -o root -g root -m 0644 "${tmp_service}" "${SERVICE_FILE}"
tmp_web_service="$(mktemp)"
sed -e "s/NODESMART_USER/${SERVICE_USER}/g" -e "s/NODESMART_GROUP/${SERVICE_GROUP}/g" "${INSTALL_ROOT}/systemd/nodesmart-web.service" > "${tmp_web_service}"
install -o root -g root -m 0644 "${tmp_web_service}" "${WEB_SERVICE_FILE}"
/usr/bin/systemctl daemon-reload

# Never make root-invoked installers or application code writable by the web user.
chown root:root "$INSTALL_ROOT"
chmod 0755 "$INSTALL_ROOT"
for directory in core web install systemd; do
  chown -R root:root "$INSTALL_ROOT/$directory"
  find "$INSTALL_ROOT/$directory" -type d -exec chmod 0755 {} \;
  find "$INSTALL_ROOT/$directory" -type f -exec chmod a+r,go-w {} \;
done
chown root:"$SERVICE_GROUP" "$INSTALL_ROOT/config" "$INSTALL_ROOT/config/nodesmart.json"
chmod 0750 "$INSTALL_ROOT/config"
chmod 0640 "$INSTALL_ROOT/config/nodesmart.json"
for directory in events history logs state; do
  chown -R "$SERVICE_USER:$SERVICE_GROUP" "$INSTALL_ROOT/$directory"
  find "$INSTALL_ROOT/$directory" -type d -exec chmod 0750 {} \;
  find "$INSTALL_ROOT/$directory" -type f -exec chmod 0640 {} \;
done

if [[ ! -e "/usr/local/bin/SkywarnPlus/SkyControl.py" ]]; then
  echo "WARNING: SkywarnPlus was not detected. Skywarn controls will not work until it is installed."
fi

echo "Validating Python files..."
/usr/bin/python3 -m py_compile "${INSTALL_ROOT}/core/config.py" "${INSTALL_ROOT}/core/monitor.py" || fail "Python syntax validation failed."

echo "Firewall and network settings are unchanged. See docs/INSTALL.md for access guidance."

echo "Enabling and starting BlueNode..."
/usr/bin/systemctl enable nodesmart nodesmart-web
/usr/bin/systemctl restart nodesmart nodesmart-web
sleep 2

if /usr/bin/systemctl is-active --quiet nodesmart && /usr/bin/systemctl is-active --quiet nodesmart-web; then
  echo "BlueNode installation complete."
else
  echo "BlueNode is installed but the service is not running." >&2
  /usr/bin/systemctl status nodesmart --no-pager || true
  exit 1
fi
