#!/bin/bash
set -Eeuo pipefail

CONFIG_FILE="${BLUENODE_REMOTE_CONFIG:-/etc/bluenode/remote-access.conf}"
SITE_NAME=bluenode-funnel-gateway.conf
APACHE_AVAILABLE="${BLUENODE_APACHE_AVAILABLE:-/etc/apache2/sites-available}"
APACHE_ENABLED="${BLUENODE_APACHE_ENABLED:-/etc/apache2/sites-enabled}"
TEMPLATE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/remote-access/apache-funnel-gateway.conf.template"
APACHECTL="${BLUENODE_APACHECTL:-/usr/sbin/apache2ctl}"
A2ENSITE="${BLUENODE_A2ENSITE:-/usr/sbin/a2ensite}"
A2DISSITE="${BLUENODE_A2DISSITE:-/usr/sbin/a2dissite}"
SYSTEMCTL="${BLUENODE_SYSTEMCTL:-/usr/bin/systemctl}"
TAILSCALE="${BLUENODE_TAILSCALE:-/usr/bin/tailscale}"
CURL="${BLUENODE_CURL:-/usr/bin/curl}"

fail() { printf 'FAIL tailscale-funnel: %s\n' "$1" >&2; exit 1; }
info() { printf 'INFO tailscale-funnel: %s\n' "$1"; }
require_root() { [[ ${EUID} -eq 0 ]] || fail "run with sudo"; }

load_config() {
    [[ -f "$CONFIG_FILE" ]] || fail "configuration not found: $CONFIG_FILE"
    [[ "$(stat -c %u "$CONFIG_FILE")" == 0 ]] || fail "configuration must be owned by root"
    mode="$(stat -c %a "$CONFIG_FILE")"
    (( (8#$mode & 8#077) == 0 )) || fail "configuration must have mode 0600 or stricter"
    # shellcheck disable=SC1090
    source "$CONFIG_FILE"
    [[ "${BLUENODE_REMOTE_MODE:-}" == tailscale-funnel ]] ||
        fail "BLUENODE_REMOTE_MODE must be tailscale-funnel"
    : "${BLUENODE_FUNNEL_GATEWAY_PORT:=8090}"
    : "${BLUENODE_BACKEND_PORT:=8080}"
    : "${BLUENODE_AUTH_USER_FILE:?set BLUENODE_AUTH_USER_FILE}"
}

validate_config() {
    [[ "$BLUENODE_FUNNEL_GATEWAY_PORT" =~ ^[0-9]+$ ]] || fail "gateway port is invalid"
    [[ "$BLUENODE_BACKEND_PORT" =~ ^[0-9]+$ ]] || fail "backend port is invalid"
    (( BLUENODE_FUNNEL_GATEWAY_PORT >= 1024 && BLUENODE_FUNNEL_GATEWAY_PORT <= 65535 )) || fail "gateway port is invalid"
    (( BLUENODE_BACKEND_PORT >= 1 && BLUENODE_BACKEND_PORT <= 65535 )) || fail "backend port is invalid"
    (( BLUENODE_FUNNEL_GATEWAY_PORT != BLUENODE_BACKEND_PORT )) || fail "gateway must not be the raw BlueNode port"
    (( BLUENODE_FUNNEL_GATEWAY_PORT != 8080 )) || fail "Funnel must never target raw port 8080"
    [[ "$BLUENODE_AUTH_USER_FILE" =~ ^/[A-Za-z0-9._/-]+$ ]] || fail "password-file path is invalid"
    [[ -f "$BLUENODE_AUTH_USER_FILE" ]] || fail "password file not found"
    auth_mode="$(stat -c %a "$BLUENODE_AUTH_USER_FILE")"
    (( (8#$auth_mode & 8#007) == 0 )) || fail "password file must not be accessible by others"
    modules="$($APACHECTL -M 2>&1)" || fail "unable to inspect Apache modules"
    for module in proxy_module proxy_http_module headers_module auth_basic_module authn_file_module authz_user_module reqtimeout_module evasive20_module; do
        grep -q "$module" <<<"$modules" || fail "required Apache module is not enabled: $module"
    done
}

render_gateway() {
    validate_config
    sed -e "s|@GATEWAY_PORT@|$BLUENODE_FUNNEL_GATEWAY_PORT|g" \
        -e "s|@BACKEND_PORT@|$BLUENODE_BACKEND_PORT|g" \
        -e "s|@AUTH_USER_FILE@|$BLUENODE_AUTH_USER_FILE|g" "$TEMPLATE"
}

enable_gateway() {
    require_root
    destination="$APACHE_AVAILABLE/$SITE_NAME"
    backup="$(mktemp -d /tmp/bluenode-funnel.XXXXXX)"
    had_destination=0; had_enabled=0
    [[ -e "$destination" ]] && { cp -a "$destination" "$backup/site"; had_destination=1; }
    [[ -e "$APACHE_ENABLED/$SITE_NAME" ]] && had_enabled=1
    rollback() {
        info "gateway activation failed; restoring previous Apache state"
        $A2DISSITE "$SITE_NAME" >/dev/null 2>&1 || true
        rm -f "$destination"
        (( had_destination == 1 )) && cp -a "$backup/site" "$destination"
        (( had_enabled == 1 )) && $A2ENSITE "$SITE_NAME" >/dev/null 2>&1 || true
        $APACHECTL configtest >/dev/null 2>&1 && $SYSTEMCTL reload apache2 || true
        rm -rf "$backup"
    }
    trap rollback ERR
    rendered="$(mktemp)"
    render_gateway >"$rendered"
    install -o root -g root -m 0644 "$rendered" "$destination"
    rm -f "$rendered"
    $A2ENSITE "$SITE_NAME" >/dev/null
    $APACHECTL configtest
    $SYSTEMCTL reload apache2
    $SYSTEMCTL is-active --quiet apache2
    response="$($CURL --silent --output /dev/null --write-out '%{http_code}' --max-time 5 "http://127.0.0.1:$BLUENODE_FUNNEL_GATEWAY_PORT/web/")"
    [[ "$response" == 401 ]] || fail "gateway did not reject an unauthenticated request with HTTP 401"
    trap - ERR
    rm -rf "$backup"
    printf 'PASS tailscale-funnel: authenticated loopback gateway enabled; Funnel remains off\n'
}

verify_credentials() {
    read -r -p "BlueNode remote username: " auth_user
    [[ "$auth_user" =~ ^[A-Za-z0-9._@-]+$ ]] || fail "username contains unsupported characters"
    code="$($CURL --silent --output /dev/null --write-out '%{http_code}' --max-time 10 \
        --user "$auth_user" "http://127.0.0.1:$BLUENODE_FUNNEL_GATEWAY_PORT/web/")"
    [[ "$code" == 200 ]] || fail "authenticated gateway check returned HTTP $code"
}

validate_tailscale() {
    [[ -x "$TAILSCALE" ]] || fail "tailscale CLI is not installed"
    version="$($TAILSCALE version | head -n1)"
    [[ "$version" =~ ^([0-9]+)\.([0-9]+)\. ]] || fail "unable to determine Tailscale version"
    (( BASH_REMATCH[1] > 1 || (BASH_REMATCH[1] == 1 && BASH_REMATCH[2] >= 38) )) || fail "Tailscale 1.38.3 or newer is required"
    $SYSTEMCTL is-active --quiet tailscaled || fail "tailscaled is not active"
    $TAILSCALE status >/dev/null || fail "node is not connected to a tailnet"
}

publish_funnel() {
    require_root
    validate_config
    validate_tailscale
    [[ -e "$APACHE_ENABLED/$SITE_NAME" ]] || fail "authenticated gateway is not enabled"
    unauth="$($CURL --silent --output /dev/null --write-out '%{http_code}' --max-time 5 "http://127.0.0.1:$BLUENODE_FUNNEL_GATEWAY_PORT/web/")"
    [[ "$unauth" == 401 ]] || fail "refusing publication: unauthenticated gateway request was not rejected"
    verify_credentials
    $TAILSCALE funnel --bg --https=443 "http://127.0.0.1:$BLUENODE_FUNNEL_GATEWAY_PORT"
    $TAILSCALE funnel status
    printf 'PASS tailscale-funnel: Funnel published through authenticated gateway\n'
}

unpublish_funnel() {
    require_root
    [[ -x "$TAILSCALE" ]] || { info "Tailscale is not installed; Funnel is off"; return; }
    $TAILSCALE funnel --https=443 off
    printf 'PASS tailscale-funnel: Funnel disabled\n'
}

disable_gateway() {
    require_root
    [[ -e "$APACHE_ENABLED/$SITE_NAME" ]] || { info "gateway is already disabled"; return; }
    $A2DISSITE "$SITE_NAME" >/dev/null
    if ! $APACHECTL configtest || ! $SYSTEMCTL reload apache2 || ! $SYSTEMCTL is-active --quiet apache2; then
        $A2ENSITE "$SITE_NAME" >/dev/null
        $APACHECTL configtest >/dev/null && $SYSTEMCTL reload apache2
        fail "gateway disable failed; previous enabled state restored"
    fi
    rm -f "$APACHE_AVAILABLE/$SITE_NAME"
    printf 'PASS tailscale-funnel: authenticated gateway disabled\n'
}

action="${1:-validate}"
load_config
case "$action" in
    validate) validate_config; $APACHECTL configtest; printf 'PASS tailscale-funnel: configuration valid; Funnel remains off\n' ;;
    render) render_gateway ;;
    enable-gateway) enable_gateway ;;
    verify-auth) validate_config; verify_credentials; printf 'PASS tailscale-funnel: credentials accepted\n' ;;
    publish) publish_funnel ;;
    unpublish) unpublish_funnel ;;
    disable-gateway) disable_gateway ;;
    status) [[ -x "$TAILSCALE" ]] && $TAILSCALE funnel status || info "Tailscale is not installed" ;;
    *) fail "usage: $0 {validate|render|enable-gateway|verify-auth|publish|unpublish|disable-gateway|status}" ;;
esac
