[CmdletBinding()]
param(
    [string]$RepositoryPath = "",
    [switch]$IdentityOnly
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
        throw "Verification requires the checked-out main branch."
    }
    Assert-ExactIdentity (Invoke-Git config user.name) (Invoke-Git config user.email) "Git identity"

    $expectedRemoteForRun = $ExpectedRemote
    if ($env:BLUENODE_GIT_VERIFY_TEST_REMOTE) {
        $tempRoot = [IO.Path]::GetFullPath([IO.Path]::GetTempPath())
        if (-not $requestedRoot.StartsWith($tempRoot, [StringComparison]::OrdinalIgnoreCase)) {
            throw "The test remote override is allowed only for a temporary fixture repository."
        }
        $expectedRemoteForRun = $env:BLUENODE_GIT_VERIFY_TEST_REMOTE
    }
    $localRemote = Invoke-Git remote get-url origin
    if ($localRemote -cne $expectedRemoteForRun) {
        throw "Local origin must be exactly $expectedRemoteForRun; found $localRemote."
    }

    $privacyGuard = Join-Path $PSScriptRoot "Test-PublicTree.ps1"
    & powershell -NoProfile -ExecutionPolicy Bypass -File $privacyGuard `
        -RepositoryPath $RepositoryPath
    if ($LASTEXITCODE -ne 0) {
        throw "Public-tree privacy guard failed."
    }

    if ($IdentityOnly) {
        Write-Host "IDENTITY PASS identity=$ExpectedName<$ExpectedEmail> branch=main origin=$localRemote"
        exit 0
    }

    if (Invoke-Git status --porcelain) {
        throw "Remote verification requires a clean local working tree."
    }
    Invoke-Git fetch origin main | Out-Null
    $localCommit = Invoke-Git rev-parse main
    $remoteCommit = Invoke-Git rev-parse origin/main
    if ($localCommit -cne $remoteCommit) {
        throw "Local main ($localCommit) must exactly equal origin/main ($remoteCommit)."
    }
    Assert-ExactIdentity (Invoke-Git show -s --format=%an $localCommit) `
        (Invoke-Git show -s --format=%ae $localCommit) "Target commit author"
    Assert-ExactIdentity (Invoke-Git show -s --format=%cn $localCommit) `
        (Invoke-Git show -s --format=%ce $localCommit) "Target commit committer"

    Write-Host "GIT VERIFICATION PASS commit=$localCommit identity=$ExpectedName<$ExpectedEmail>"
}
catch {
    Write-Error "FAIL Git verification: $($_.Exception.Message)"
    exit 1
}
