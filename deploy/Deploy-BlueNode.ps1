[CmdletBinding()]
param(
    [string]$SshTarget = "60873",
    [string]$RepositoryPath = "",
    [switch]$PreflightOnly
)

$ErrorActionPreference = "Stop"
if (-not $RepositoryPath) {
    $RepositoryPath = Split-Path -Parent $PSScriptRoot
}
$ExpectedName = "BlueKF0OZX"
$ExpectedEmail = "bluedrummer1985@outlook.com"
$ExpectedRemote = "https://github.com/BlueKF0OZX/BlueNode.git"

function Invoke-Git {
    param([Parameter(ValueFromRemainingArguments = $true)][string[]]$Arguments)
    $oldErrorActionPreference = $ErrorActionPreference
    $ErrorActionPreference = "Continue"
    $output = & git -C $RepositoryPath @Arguments 2>&1
    $ErrorActionPreference = $oldErrorActionPreference
    if ($LASTEXITCODE -ne 0) {
        throw "git $($Arguments -join ' ') failed: $($output -join [Environment]::NewLine)"
    }
    return $output
}

function Assert-ExactIdentity {
    param([string]$Name, [string]$Email, [string]$Kind)
    if ($Name -cne $ExpectedName -or $Email -cne $ExpectedEmail) {
        throw "$Kind must be exactly $ExpectedName <$ExpectedEmail>; found $Name <$Email>."
    }
}

try {
    $gitRoot = [IO.Path]::GetFullPath([string](Invoke-Git rev-parse --show-toplevel))
    $requestedRoot = [IO.Path]::GetFullPath((Resolve-Path $RepositoryPath).Path)
    if ($gitRoot -ine $requestedRoot) {
        throw "RepositoryPath must be the BlueNode repository root."
    }
    if ((Invoke-Git branch --show-current) -cne "main") {
        throw "Deployment requires the checked-out main branch."
    }
    if (Invoke-Git status --porcelain) {
        throw "Deployment requires a clean local working tree."
    }

    Assert-ExactIdentity (Invoke-Git config user.name) (Invoke-Git config user.email) "Git identity"

    $localExpectedRemote = $ExpectedRemote
    if ($PreflightOnly -and $env:BLUENODE_DEPLOY_TEST_REMOTE) {
        $localExpectedRemote = $env:BLUENODE_DEPLOY_TEST_REMOTE
    }
    $localRemote = Invoke-Git remote get-url origin
    if ($localRemote -cne $localExpectedRemote) {
        throw "Local origin must be exactly $localExpectedRemote; found $localRemote."
    }

    Invoke-Git fetch origin main | Out-Null
    $targetCommit = Invoke-Git rev-parse main
    $originCommit = Invoke-Git rev-parse origin/main
    if ($targetCommit -cne $originCommit) {
        throw "Local main ($targetCommit) must exactly equal origin/main ($originCommit)."
    }

    Assert-ExactIdentity `
        (Invoke-Git show -s --format=%an $targetCommit) `
        (Invoke-Git show -s --format=%ae $targetCommit) `
        "Target commit author"
    Assert-ExactIdentity `
        (Invoke-Git show -s --format=%cn $targetCommit) `
        (Invoke-Git show -s --format=%ce $targetCommit) `
        "Target commit committer"

    if ($PreflightOnly) {
        Write-Host "PASS preflight target=$targetCommit identity=$ExpectedName<$ExpectedEmail>"
        exit 0
    }

    if ($SshTarget -cnotmatch '^[A-Za-z0-9_.@:-]+$') {
        throw "SshTarget contains unsupported characters."
    }

    $remoteScript = @'
set -Eeuo pipefail

target_commit="$1"
expected_remote="$2"
app_root=/opt/nodesmart
backup_root=/opt/nodesmart-backups
stamp="$(date -u +%Y%m%dT%H%M%SZ)-$$"
backup="$backup_root/nodesmart-$stamp-${target_commit:0:12}.tar.gz"
failed_copy="$backup_root/failed-$stamp-${target_commit:0:12}"
deploy_epoch="$(date +%s)"
backup_ready=0
deployment_started=0
rolling_back=0

report() { printf '%s %s\n' "$1" "$2"; }
git_live() { git -c safe.directory="$app_root" -C "$app_root" "$@"; }

rollback() {
    rolling_back=1
    report INFO "validation failed; restoring $backup"
    [[ "$(sha256sum "$backup" | awk '{print $1}')" == "$backup_sha256" ]] || return 1
    tar -tzf "$backup" >/dev/null || return 1
    systemctl stop nodesmart.service nodesmart-web.service || true
    if [[ -e "$app_root" ]]; then
        mv "$app_root" "$failed_copy" || return 1
    fi
    mkdir -p "$app_root" || return 1
    tar -xzf "$backup" -C "$app_root" || return 1
    systemctl restart nodesmart.service nodesmart-web.service || return 1
    systemctl is-active --quiet nodesmart.service || return 1
    systemctl is-active --quiet nodesmart-web.service || return 1
    report ROLLBACK "PASS backup=$backup failed_copy=$failed_copy"
}

on_error() {
    status=$?
    line=$1
    if (( backup_ready == 1 && deployment_started == 1 && rolling_back == 0 )); then
        if rollback; then
            report FAIL "deployment validation failed at line $line; rollback verified"
        else
            report FAIL "deployment validation failed at line $line; ROLLBACK FAILED"
        fi
    else
        report FAIL "deployment failed at line $line before rollback was applicable"
    fi
    exit "$status"
}
trap 'on_error $LINENO' ERR

[[ -d "$app_root/.git" ]]
mkdir -p "$backup_root"
tar -czf "$backup" -C "$app_root" .
tar -tzf "$backup" >/dev/null
backup_sha256="$(sha256sum "$backup" | awk '{print $1}')"
[[ -n "$backup_sha256" ]]
backup_ready=1
report BACKUP "PASS path=$backup sha256=$backup_sha256"

service_user="$(systemctl show nodesmart.service -p User --value)"
[[ -n "$service_user" && "$service_user" != root ]]
service_group="$(id -gn "$service_user")"

deployment_started=1
git_live remote set-url origin "$expected_remote"
[[ "$(git_live remote get-url origin)" == "$expected_remote" ]]
git_live fetch --quiet --prune origin main
git_live cat-file -e "$target_commit^{commit}"
[[ "$(git_live rev-parse origin/main)" == "$target_commit" ]]
if git_live ls-tree -r --name-only "$target_commit" -- \
        config/nodesmart.json events history logs state | grep -q .; then
    report FAIL "target commit tracks machine-specific runtime data"
    false
fi
git_live reset --hard --quiet "$target_commit"
[[ "$(git_live rev-parse HEAD)" == "$target_commit" ]]

# Git never cleans these ignored machine-specific paths. Restore their service
# ownership explicitly so a prior root operation cannot block runtime writes.
for path in config/nodesmart.json events history logs state; do
    if [[ -e "$app_root/$path" ]]; then
        chown -R "$service_user:$service_group" "$app_root/$path"
    fi
done

python3 -m compileall -q "$app_root/core"
systemctl restart nodesmart.service nodesmart-web.service
systemctl is-active --quiet nodesmart.service
systemctl is-active --quiet nodesmart-web.service
validation_epoch="$(date +%s)"

deadline=$((SECONDS + 20))
while (( SECONDS < deadline )); do
    system_mtime="$(stat -c %Y "$app_root/state/system.json" 2>/dev/null || echo 0)"
    intelligence_mtime="$(stat -c %Y "$app_root/state/intelligence.json" 2>/dev/null || echo 0)"
    if (( system_mtime > validation_epoch && intelligence_mtime > validation_epoch )); then
        break
    fi
    sleep 2
done
(( system_mtime > validation_epoch ))
(( intelligence_mtime > validation_epoch ))

asterisk -rx 'core show version' >/dev/null
web_port="$(python3 -c 'import json,sys; print(int(json.load(open(sys.argv[1]))["web"]["port"]))' "$app_root/config/nodesmart.json")"
curl --fail --silent --show-error --max-time 5 "http://127.0.0.1:$web_port/web/" >/dev/null

journal_output="$(journalctl -u nodesmart.service -u nodesmart-web.service --since "@$deploy_epoch" --no-pager 2>&1)"
if grep -Eiq 'Traceback|NodeSmart .* error|unhandled exception|segmentation fault|Failed with result' <<<"$journal_output"; then
    printf '%s\n' "$journal_output" >&2
    false
fi

trap - ERR
report TARGET "PASS commit=$target_commit"
report SERVICE "PASS nodesmart.service=active nodesmart-web.service=active"
report STATE "PASS system.json=$system_mtime intelligence.json=$intelligence_mtime"
report ASTERISK "PASS reachable"
report DASHBOARD "PASS http://127.0.0.1:$web_port/web/"
report JOURNAL "PASS no-obvious-new-errors"
report DEPLOYMENT "PASS commit=$target_commit backup=$backup"
'@

    $startInfo = [Diagnostics.ProcessStartInfo]::new()
    $startInfo.FileName = "ssh"
    $startInfo.UseShellExecute = $false
    $startInfo.RedirectStandardInput = $true
    $startInfo.Arguments = "$SshTarget sudo -n bash -s -- $targetCommit $ExpectedRemote"

    $process = [Diagnostics.Process]::Start($startInfo)
    $process.StandardInput.Write($remoteScript.Replace("`r`n", "`n"))
    $process.StandardInput.Close()
    $process.WaitForExit()
    if ($process.ExitCode -ne 0) {
        throw "Remote deployment failed with exit code $($process.ExitCode)."
    }
}
catch {
    Write-Error "FAIL deployment: $($_.Exception.Message)"
    exit 1
}
