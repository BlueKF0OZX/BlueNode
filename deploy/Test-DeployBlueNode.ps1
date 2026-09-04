$ErrorActionPreference = "Stop"
$DeployScript = Join-Path $PSScriptRoot "Deploy-BlueNode.ps1"
$GitVerifyScript = Join-Path $PSScriptRoot "Verify-BlueNodeGit.ps1"
$ExpectedName = "BlueKF0OZX"
$ExpectedEmail = "bluedrummer1985@outlook.com"
$tempRoot = Join-Path ([IO.Path]::GetTempPath()) ("bluenode-deploy-test-" + [guid]::NewGuid())
$remote = Join-Path $tempRoot "remote.git"
$repo = Join-Path $tempRoot "repo"

function Run-Git([string]$Path, [string[]]$Arguments) {
    $oldErrorActionPreference = $ErrorActionPreference
    $ErrorActionPreference = "Continue"
    & git -C $Path @Arguments 2>&1 | Out-Null
    $ErrorActionPreference = $oldErrorActionPreference
    if ($LASTEXITCODE -ne 0) { throw "git $($Arguments -join ' ') failed" }
}

function Run-Preflight([string]$ExpectedText, [int]$ExpectedExit = 0) {
    $oldErrorActionPreference = $ErrorActionPreference
    $ErrorActionPreference = "Continue"
    $output = & powershell -NoProfile -ExecutionPolicy Bypass -File $DeployScript -RepositoryPath $repo -PreflightOnly 2>&1
    $ErrorActionPreference = $oldErrorActionPreference
    $normalizedOutput = (($output -join " ") -replace '\s+', ' ')
    if ($LASTEXITCODE -ne $ExpectedExit -or $normalizedOutput -notlike "*$ExpectedText*") {
        throw "Expected exit $ExpectedExit containing '$ExpectedText'; got exit $LASTEXITCODE`: $output"
    }
}

function Run-GitVerification([string]$ExpectedText, [int]$ExpectedExit = 0, [switch]$IdentityOnly) {
    $arguments = @("-NoProfile", "-ExecutionPolicy", "Bypass", "-File", $GitVerifyScript,
        "-RepositoryPath", $repo)
    if ($IdentityOnly) { $arguments += "-IdentityOnly" }
    $oldErrorActionPreference = $ErrorActionPreference
    $ErrorActionPreference = "Continue"
    $output = & powershell @arguments 2>&1
    $ErrorActionPreference = $oldErrorActionPreference
    $normalizedOutput = (($output -join " ") -replace '\s+', ' ')
    if ($LASTEXITCODE -ne $ExpectedExit -or $normalizedOutput -notlike "*$ExpectedText*") {
        throw "Expected Git verification exit $ExpectedExit containing '$ExpectedText'; got exit $LASTEXITCODE`: $output"
    }
}

try {
    New-Item -ItemType Directory -Path $tempRoot | Out-Null
    & git init --bare $remote 2>&1 | Out-Null
    & git init -b main $repo 2>&1 | Out-Null
    Run-Git $repo @("config", "user.name", $ExpectedName)
    Run-Git $repo @("config", "user.email", $ExpectedEmail)
    Set-Content -LiteralPath (Join-Path $repo "fixture.txt") -Value "initial"
    Run-Git $repo @("add", "fixture.txt")
    Run-Git $repo @("commit", "-m", "Initial fixture")
    Run-Git $repo @("remote", "add", "origin", $remote)
    Run-Git $repo @("push", "-u", "origin", "main")
    $env:BLUENODE_DEPLOY_TEST_REMOTE = $remote
    $env:BLUENODE_GIT_VERIFY_TEST_REMOTE = $remote

    Run-Preflight "ssh_target=nodesmart60873"
    Run-GitVerification "GIT VERIFICATION PASS"
    Run-GitVerification "IDENTITY PASS" -IdentityOnly

    New-Item -ItemType Directory -Path (Join-Path $repo "state") | Out-Null
    Set-Content -LiteralPath (Join-Path $repo "state/system.json") -Value "{}"
    Run-Git $repo @("add", "state/system.json")
    Run-GitVerification "privacy guard failed" 1 -IdentityOnly
    Run-Git $repo @("rm", "--cached", "state/system.json")
    Remove-Item -LiteralPath (Join-Path $repo "state") -Recurse -Force

    Run-Git $repo @("remote", "set-url", "origin", "https://example.invalid/wrong.git")
    Run-Preflight "Local origin must be exactly" 1
    Run-Git $repo @("remote", "set-url", "origin", $remote)

    Set-Content -LiteralPath (Join-Path $repo "dirty.txt") -Value "dirty"
    Run-Preflight "clean local working tree" 1
    Run-GitVerification "clean local working tree" 1
    Run-GitVerification "IDENTITY PASS" -IdentityOnly
    Remove-Item -LiteralPath (Join-Path $repo "dirty.txt")

    Run-Git $repo @("config", "user.email", "wrong@example.com")
    Run-Preflight "Git identity must be exactly" 1
    Run-GitVerification "Git identity must be exactly" 1 -IdentityOnly
    Run-Git $repo @("config", "user.email", $ExpectedEmail)

    Set-Content -LiteralPath (Join-Path $repo "fixture.txt") -Value "ahead"
    Run-Git $repo @("add", "fixture.txt")
    Run-Git $repo @("commit", "-m", "Local ahead")
    Run-Preflight "must exactly equal origin/main" 1
    Run-GitVerification "must exactly equal origin/main" 1

    Run-Git $repo @("push", "origin", "main")
    Run-Git $repo @("config", "user.name", "Wrong Author")
    Set-Content -LiteralPath (Join-Path $repo "fixture.txt") -Value "wrong author"
    Run-Git $repo @("add", "fixture.txt")
    Run-Git $repo @("commit", "-m", "Wrong author fixture")
    Run-Git $repo @("push", "origin", "main")
    Run-Git $repo @("config", "user.name", $ExpectedName)
    Run-Preflight "Target commit author must be exactly" 1

    Run-Git $repo @("config", "user.name", "Wrong Committer")
    Set-Content -LiteralPath (Join-Path $repo "fixture.txt") -Value "wrong committer"
    Run-Git $repo @("add", "fixture.txt")
    Run-Git $repo @("commit", "--author", "$ExpectedName <$ExpectedEmail>", "-m", "Wrong committer fixture")
    Run-Git $repo @("push", "origin", "main")
    Run-Git $repo @("config", "user.name", $ExpectedName)
    Run-Preflight "Target commit committer must be exactly" 1

    Write-Host "PASS deployment preflight tests"
}
finally {
    Remove-Item Env:BLUENODE_DEPLOY_TEST_REMOTE -ErrorAction SilentlyContinue
    Remove-Item Env:BLUENODE_GIT_VERIFY_TEST_REMOTE -ErrorAction SilentlyContinue
    if (Test-Path -LiteralPath $tempRoot) {
        Remove-Item -LiteralPath $tempRoot -Recurse -Force
    }
}
