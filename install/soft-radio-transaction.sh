#!/bin/bash
set -Eeuo pipefail

ACTION="${1:-}"
TRANSACTION="${2:-}"
MANAGED_ROOT="${BLUENODE_TRANSACTION_ROOT:-}"
BACKUP_ROOT="${BLUENODE_TRANSACTION_BACKUP_ROOT:-/opt/nodesmart-backups}"

fail() { printf 'FAIL soft-radio-transaction: %s\n' "$1" >&2; exit 1; }
logical_paths=(
  /etc/asterisk/rpt.conf
  /etc/asterisk/simpleusb.conf
  /etc/asterisk/websocket_client.conf
  /etc/bluenode/remote-admin.json
  /etc/bluenode/soft-radio.json
  /etc/bluenode/soft-radio-websocket-client.conf
  /etc/sudoers.d/bluenode-soft-radio-rx
  /usr/local/bin/bluenode-soft-radio-rx-start
)

actual_path() { printf '%s%s\n' "$MANAGED_ROOT" "$1"; }
make_private_dir() {
  if [[ -z "$MANAGED_ROOT" ]]; then
    install -d -m 0700 "$1"
  else
    mkdir -p "$1"
  fi
}
is_managed() {
  local candidate=$1 item
  for item in "${logical_paths[@]}"; do
    [[ "$candidate" != "$item" ]] || return 0
  done
  return 1
}
verify_transaction() {
  local transaction=$1 count
  [[ -d "$transaction" && -f "$transaction/VERIFIED" ]] \
    || fail "transaction is incomplete or unverified"
  (cd "$transaction" && sha256sum -c manifest.sha256 >/dev/null) \
    || fail "transaction manifest verification failed"
  count=$(wc -l < "$transaction/inventory")
  [[ "$count" -eq "${#logical_paths[@]}" ]] \
    || fail "transaction inventory is incomplete"
  [[ "$(cut -f2 "$transaction/inventory" | sort -u | wc -l)" -eq "${#logical_paths[@]}" ]] \
    || fail "transaction inventory contains duplicate paths"
  if [[ -s "$transaction/sha256" ]]; then
    (cd "$transaction/files" && sha256sum -c ../sha256 >/dev/null) \
      || fail "backed-up file checksum verification failed"
  fi
}

case "$ACTION" in
  snapshot)
    [[ -z "$TRANSACTION" ]] || fail "snapshot takes no transaction argument"
    make_private_dir "$BACKUP_ROOT"
    staging=$(mktemp -d "$BACKUP_ROOT/.soft-radio-transaction.XXXXXXXX")
    cleanup=1
    trap '[[ ${cleanup:-0} == 0 ]] || rm -rf -- "$staging"' EXIT
    make_private_dir "$staging/files"
    : > "$staging/inventory"
    : > "$staging/sha256"
    for logical in "${logical_paths[@]}"; do
      actual=$(actual_path "$logical")
      if [[ -e "$actual" ]]; then
        destination="$staging/files$logical"
        make_private_dir "$(dirname "$destination")"
        cp -a -- "$actual" "$destination"
        printf 'present\t%s\n' "$logical" >> "$staging/inventory"
      else
        printf 'absent\t%s\n' "$logical" >> "$staging/inventory"
      fi
    done
    (cd "$staging/files" && find . -type f -print0 | sort -z | xargs -0 -r sha256sum) \
      > "$staging/sha256"
    [[ "$(wc -l < "$staging/inventory")" -eq "${#logical_paths[@]}" ]] \
      || fail "inventory creation did not complete"
    if [[ -s "$staging/sha256" ]]; then
      (cd "$staging/files" && sha256sum -c ../sha256 >/dev/null) \
        || fail "initial backup checksum verification failed"
    fi
    : > "$staging/created"
    (cd "$staging" && sha256sum inventory sha256 created > manifest.sha256)
    : > "$staging/VERIFIED"
    final="$BACKUP_ROOT/soft-radio-rx-$(date -u +%Y%m%dT%H%M%SZ)-$$"
    mv -- "$staging" "$final"
    cleanup=0
    printf 'BACKUP PASS transaction=%s\n' "$final"
    ;;
  mark-created)
    [[ $# -eq 3 ]] || fail "usage: $0 mark-created TRANSACTION MANAGED_PATH"
    logical=$3
    verify_transaction "$TRANSACTION"
    is_managed "$logical" || fail "path is not managed by Soft Radio"
    [[ "$logical" != /etc/bluenode/remote-admin.json ]] \
      || fail "Soft Radio may not mark Remote Admin configuration as created"
    grep -Fqx $'absent\t'"$logical" "$TRANSACTION/inventory" \
      || fail "path existed before this transaction"
    [[ -e "$(actual_path "$logical")" ]] || fail "created path does not exist"
    update_created() {
      if ! grep -Fqx "$logical" "$TRANSACTION/created"; then
        printf '%s\n' "$logical" >> "$TRANSACTION/created"
        (cd "$TRANSACTION" && sha256sum inventory sha256 created > manifest.sha256)
      fi
    }
    if command -v flock >/dev/null 2>&1; then
      (flock -x 9; update_created) 9>"$TRANSACTION/lock"
    elif [[ -n "$MANAGED_ROOT" ]]; then
      update_created
    else
      fail "flock is required to update a production transaction"
    fi
    printf 'CREATED PASS path=%s\n' "$logical"
    ;;
  rollback)
    [[ $# -eq 2 ]] || fail "usage: $0 rollback TRANSACTION"
    verify_transaction "$TRANSACTION"
    while IFS=$'\t' read -r original logical; do
      is_managed "$logical" || fail "inventory contains unmanaged path"
      actual=$(actual_path "$logical")
      if [[ "$original" == present ]]; then
        saved="$TRANSACTION/files$logical"
        [[ -f "$saved" ]] || fail "backed-up file is missing"
        install -d "$(dirname "$actual")"
        temporary="$actual.rollback.$$"
        cp -a -- "$saved" "$temporary"
        mv -f -- "$temporary" "$actual"
      elif [[ "$original" == absent ]]; then
        if [[ "$logical" != /etc/bluenode/remote-admin.json ]] \
            && grep -Fqx "$logical" "$TRANSACTION/created"; then
          rm -f -- "$actual"
        fi
      else
        fail "inventory contains an invalid existence state"
      fi
    done < "$TRANSACTION/inventory"
    printf 'ROLLBACK PASS transaction=%s\n' "$TRANSACTION"
    ;;
  verify)
    [[ $# -eq 2 ]] || fail "usage: $0 verify TRANSACTION"
    verify_transaction "$TRANSACTION"
    printf 'VERIFY PASS transaction=%s\n' "$TRANSACTION"
    ;;
  *) fail "usage: $0 {snapshot|mark-created|rollback|verify}" ;;
esac
