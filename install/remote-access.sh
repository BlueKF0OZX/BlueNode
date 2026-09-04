#!/bin/bash
set -Eeuo pipefail

CONFIG_FILE="${BLUENODE_REMOTE_CONFIG:-/etc/bluenode/remote-access.conf}"
SITE_NAME=bluenode-remote.conf
APACHE_AVAILABLE="${BLUENODE_APACHE_AVAILABLE:-/etc/apache2/sites-available}"
APACHE_ENABLED="${BLUENODE_APACHE_ENABLED:-/etc/apache2/sites-enabled}"
TEMPLATE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/remote-access/apache-vhost.conf.template"
APACHECTL="${BLUENODE_APACHECTL:-/usr/sbin/apache2ctl}"
A2ENSITE="${BLUENODE_A2ENSITE:-/usr/sbin/a2ensite}"
A2DISSITE="${BLUENODE_A2DISSITE:-/usr/sbin/a2dissite}"
SYSTEMCTL="${BLUENODE_SYSTEMCTL:-/usr/bin/systemctl}"

fail() { printf 'FAIL remote-access: %s\n' "$1" >&2; exit 1; }
info() { printf 'INFO remote-access: %s\n' "$1"; }
require_root() { [[ ${EUID} -eq 0 ]] || fail "run with sudo"; }
require_file() { [[ -f "$1" ]] || fail "required file not found: $1"; }

load_config() {
    require_file "$CONFIG_FILE"
    # The operator-owned file is deliberately outside Git and must be root-only.
    [[ "$(stat -c %u "$CONFIG_FILE")" == 0 ]] || fail "configuration must be owned by root"
    mode="$(stat -c %a "$CONFIG_FILE")"
    (( (8#$mode & 8#077) == 0 )) || fail "configuration must not be accessible by group or others"
    # shellcheck disable=SC1090
    source "$CONFIG_FILE"
    : "${BLUENODE_REMOTE_MODE:?set BLUENODE_REMOTE_MODE to direct or tunnel}"
}

validate_backend() {
    : "${BLUENODE_BACKEND_URL:=http://127.0.0.1:8080}"
    [[ "$BLUENODE_BACKEND_URL" =~ ^http://127\.0\.0\.1:[0-9]{1,5}$ ]] ||
        fail "backend must use loopback IPv4; raw port 8080 must never be a public upstream"
    port="${BLUENODE_BACKEND_URL##*:}"
    (( port >= 1 && port <= 65535 )) || fail "backend port is invalid"
}

validate_direct() {
    validate_backend
    : "${BLUENODE_REMOTE_HOST:?set BLUENODE_REMOTE_HOST}"
    : "${BLUENODE_CERTIFICATE_FILE:?set BLUENODE_CERTIFICATE_FILE}"
    : "${BLUENODE_CERTIFICATE_KEY_FILE:?set BLUENODE_CERTIFICATE_KEY_FILE}"
    : "${BLUENODE_AUTH_USER_FILE:?set BLUENODE_AUTH_USER_FILE}"
    [[ "$BLUENODE_REMOTE_HOST" =~ ^[A-Za-z0-9]([A-Za-z0-9.-]*[A-Za-z0-9])?$ && "$BLUENODE_REMOTE_HOST" == *.* ]] ||
        fail "remote host must be a fully qualified DNS name"
    for path in "$BLUENODE_CERTIFICATE_FILE" "$BLUENODE_CERTIFICATE_KEY_FILE" "$BLUENODE_AUTH_USER_FILE"; do
        [[ "$path" == /* ]] || fail "credential paths must be absolute"
        [[ "$path" =~ ^/[A-Za-z0-9._/-]+$ ]] || fail "credential path contains unsupported characters"
        require_file "$path"
    done
    [[ "$BLUENODE_CERTIFICATE_FILE" != "$BLUENODE_CERTIFICATE_KEY_FILE" ]] ||
        fail "certificate and private key must be separate files"
    auth_mode="$(stat -c %a "$BLUENODE_AUTH_USER_FILE")"
    (( (8#$auth_mode & 8#007) == 0 )) || fail "password file must not be accessible by others"
    modules="$($APACHECTL -M 2>&1)" || fail "unable to inspect Apache modules"
    for module in ssl_module proxy_module proxy_http_module headers_module auth_basic_module authn_file_module authz_user_module reqtimeout_module evasive20_module; do
        grep -q "$module" <<<"$modules" || fail "required Apache module is not enabled: $module"
    done
}

render_direct() {
    validate_direct
    sed -e "s|@REMOTE_HOST@|$BLUENODE_REMOTE_HOST|g" \
        -e "s|@CERTIFICATE_FILE@|$BLUENODE_CERTIFICATE_FILE|g" \
        -e "s|@CERTIFICATE_KEY_FILE@|$BLUENODE_CERTIFICATE_KEY_FILE|g" \
        -e "s|@AUTH_USER_FILE@|$BLUENODE_AUTH_USER_FILE|g" \
        -e "s|@BACKEND_URL@|$BLUENODE_BACKEND_URL|g" "$TEMPLATE"
}

enable_direct() {
    require_root
    destination="$APACHE_AVAILABLE/$SITE_NAME"
    enabled="$APACHE_ENABLED/$SITE_NAME"
    backup="$(mktemp -d /tmp/bluenode-remote.XXXXXX)"
    had_destination=0
    had_enabled=0
    [[ -e "$destination" ]] && { cp -a "$destination" "$backup/site"; had_destination=1; }
    [[ -e "$enabled" ]] && had_enabled=1
    rollback() {
        info "activation failed; restoring previous Apache state"
        $A2DISSITE "$SITE_NAME" >/dev/null 2>&1 || true
        rm -f "$destination"
        (( had_destination == 1 )) && cp -a "$backup/site" "$destination"
        (( had_enabled == 1 )) && $A2ENSITE "$SITE_NAME" >/dev/null 2>&1 || true
        $APACHECTL configtest >/dev/null 2>&1 && $SYSTEMCTL reload apache2 || true
        rm -rf "$backup"
    }
    trap rollback ERR
    rendered="$(mktemp)"
    render_direct >"$rendered"
    install -o root -g root -m 0644 "$rendered" "$destination"
    rm -f "$rendered"
    $A2ENSITE "$SITE_NAME" >/dev/null
    $APACHECTL configtest
    $SYSTEMCTL reload apache2
    $SYSTEMCTL is-active --quiet apache2
    trap - ERR
    rm -rf "$backup"
    printf 'PASS remote-access: direct HTTPS enabled for %s\n' "$BLUENODE_REMOTE_HOST"
}

disable_direct() {
    require_root
    destination="$APACHE_AVAILABLE/$SITE_NAME"
    [[ -e "$APACHE_ENABLED/$SITE_NAME" ]] || { info "direct mode is already disabled"; return; }
    $A2DISSITE "$SITE_NAME" >/dev/null
    if ! $APACHECTL configtest || ! $SYSTEMCTL reload apache2 || ! $SYSTEMCTL is-active --quiet apache2; then
        $A2ENSITE "$SITE_NAME" >/dev/null
        $APACHECTL configtest >/dev/null && $SYSTEMCTL reload apache2
        fail "disable validation failed; previous enabled state restored"
    fi
    rm -f "$destination"
    printf 'PASS remote-access: disabled; local dashboard unchanged\n'
}

validate_tunnel() {
    validate_backend
    [[ "${BLUENODE_TUNNEL_AUTHENTICATION_ACK:-}" == "required" ]] ||
        fail "tunnel configuration must acknowledge provider-side authentication for every route"
    info "tunnel mode validated: configure an operator-managed authenticated HTTPS tunnel to $BLUENODE_BACKEND_URL"
}

action="${1:-validate}"
load_config
case "$BLUENODE_REMOTE_MODE:$action" in
    direct:validate) validate_direct; $APACHECTL configtest; printf 'PASS remote-access: direct configuration valid (not enabled)\n' ;;
    direct:render) render_direct ;;
    direct:enable) enable_direct ;;
    direct:disable) disable_direct ;;
    tunnel:validate) validate_tunnel; printf 'PASS remote-access: tunnel prerequisites valid (not enabled)\n' ;;
    tunnel:enable|tunnel:disable) fail "tunnel lifecycle is provider-managed; follow docs/REMOTE_ACCESS.md" ;;
    *) fail "usage: $0 {validate|render|enable|disable}" ;;
esac
