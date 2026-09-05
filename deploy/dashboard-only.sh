#!/bin/bash
# Scoped static-dashboard deployment. Does not migrate or restart the backend.
set -Eeuo pipefail
umask 077
target_commit="${1:?target commit required}"
expected_remote="${2:?canonical remote required}"
app_root=/opt/nodesmart
backup_root=/opt/nodesmart-backups
[[ "$target_commit" =~ ^[0-9a-f]{40}$ ]] || exit 1
[[ $EUID -eq 0 ]] || { echo 'Run through the guarded PowerShell deployment with sudo'; exit 1; }
[[ -f "$app_root/web/index.html" && ! -L "$app_root/web/index.html" ]]
git_live() { git -c safe.directory="$app_root" -C "$app_root" "$@"; }
[[ "$(git_live remote get-url origin)" == "$expected_remote" ]]
backend_commit="$(git_live rev-parse HEAD)"
dirty="$(git_live status --porcelain --untracked-files=no)"
if [[ -n "$dirty" ]]; then
  # A previous dashboard-only overlay is expected; unknown changes are refused.
  [[ "$dirty" == ' M web/index.html' && -f "$backup_root/dashboard-current.sha256" ]]
  sha256sum -c "$backup_root/dashboard-current.sha256" >/dev/null
fi
for service in asterisk nodesmart nodesmart-web; do
  systemctl is-active --quiet "$service"
done
asterisk_before="$(systemctl show asterisk -p MainPID -p ActiveEnterTimestampMonotonic)"
[[ "$asterisk_before" != *'MainPID=0'* ]]
git_live fetch --quiet origin main
[[ "$(git_live rev-parse origin/main)" == "$target_commit" ]]
[[ "$(git_live cat-file -t "$target_commit:web/index.html")" == blob ]]

mkdir -p "$backup_root"
stamp="$(date -u +%Y%m%dT%H%M%SZ)-$$"
backup="$backup_root/dashboard-$stamp.html"
cp -p "$app_root/web/index.html" "$backup"
backup_hash="$(sha256sum "$backup" | cut -d' ' -f1)"
candidate="$(mktemp "$app_root/web/.dashboard.XXXXXXXX")"
protected="$(mktemp)"
changed=0
cleanup() { rm -f -- "$candidate" "$protected"; }
rollback() {
  result=$?
  trap - ERR
  if (( changed )); then
    [[ "$(sha256sum "$backup" | cut -d' ' -f1)" == "$backup_hash" ]] || exit 1
    cp -p "$backup" "$candidate"
    mv -f "$candidate" "$app_root/web/index.html"
    echo "ROLLBACK PASS dashboard restored from $backup"
  fi
  echo 'FAIL dashboard-only deployment; backend and services were not restarted'
  exit "$result"
}
trap cleanup EXIT
trap rollback ERR

# Hash tracked non-dashboard application files and live configuration. Do not
# inspect or copy changing runtime history/state into the deployment payload.
protected_hashes() {
  /usr/bin/python3 - "$app_root" <<'PY'
import hashlib, pathlib, subprocess, sys
root = pathlib.Path(sys.argv[1])
names = subprocess.check_output(['git', '-c', 'safe.directory=' + str(root),
    '-C', str(root), 'ls-files', '-z']).decode().split('\0')
names.append('config/nodesmart.json')
for name in sorted(set(names)):
    if not name or name == 'web/index.html':
        continue
    path = root / name
    if path.is_file():
        print(hashlib.sha256(path.read_bytes()).hexdigest(), name)
PY
}
protected_hashes > "$protected"
git_live show "$target_commit:web/index.html" > "$candidate"
[[ -s "$candidate" ]]
# Keep the existing static file's ownership and mode; no privilege migration.
chmod --reference="$app_root/web/index.html" "$candidate"
chown --reference="$app_root/web/index.html" "$candidate"
expected_hash="$(sha256sum "$candidate" | cut -d' ' -f1)"
changed=1
mv -f "$candidate" "$app_root/web/index.html"
[[ "$(sha256sum "$app_root/web/index.html" | cut -d' ' -f1)" == "$expected_hash" ]]
[[ "$(git_live rev-parse HEAD)" == "$backend_commit" ]]
[[ "$(protected_hashes)" == "$(cat "$protected")" ]]
for service in asterisk nodesmart nodesmart-web; do
  systemctl is-active --quiet "$service"
done
[[ "$(systemctl show asterisk -p MainPID -p ActiveEnterTimestampMonotonic)" == "$asterisk_before" ]]
/usr/bin/python3 - "$app_root/config/nodesmart.json" "$expected_hash" <<'PY'
import hashlib, json, sys, urllib.request, urllib.error
config = json.load(open(sys.argv[1]))
host = config.get('web', {}).get('host', '127.0.0.1')
if host == '0.0.0.0': host = '127.0.0.1'
base = 'http://' + host + ':' + str(config.get('web', {}).get('port', 8080))
def read(path):
    with urllib.request.urlopen(base + path, timeout=5) as response:
        assert response.status == 200
        return response.read()
assert hashlib.sha256(read('/web/')).hexdigest() == sys.argv[2]
for path in ('/state/system.json', '/state/intelligence.json', '/api/emergency-mode', '/api/admin/session'):
    assert isinstance(json.loads(read(path)), dict), path
try:
    read('/api/admin/status')
except urllib.error.HTTPError as error:
    assert error.code == 401, error.code
else:
    raise AssertionError('Remote Admin permitted an unauthenticated request')
print('HTTP PASS dashboard hash, primary state APIs, and Remote Admin authentication')
PY
sha256sum "$app_root/web/index.html" > "$backup_root/dashboard-current.sha256"
printf 'ui_commit=%s\nbackend_commit=%s\nbackup=%s\n' "$target_commit" "$backend_commit" "$backup" \
  > "$backup_root/dashboard-current.txt"
trap - ERR
printf 'DASHBOARD-ONLY PASS ui_commit=%s backend_commit=%s backup=%s\n' "$target_commit" "$backend_commit" "$backup"
printf 'SAFETY PASS no service restarts; Asterisk PID/start unchanged; non-dashboard application files unchanged\n'
