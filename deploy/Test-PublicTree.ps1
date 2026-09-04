[CmdletBinding()]
param([string]$RepositoryPath = "")

$ErrorActionPreference = "Stop"
if (-not $RepositoryPath) {
    $RepositoryPath = Split-Path -Parent $PSScriptRoot
}
$RepositoryPath = (Resolve-Path $RepositoryPath).Path

function Invoke-Git {
    param([Parameter(ValueFromRemainingArguments = $true)][string[]]$Arguments)
    $output = & git -C $RepositoryPath @Arguments 2>&1
    if ($LASTEXITCODE -ne 0) {
        throw "git $($Arguments -join ' ') failed: $($output -join [Environment]::NewLine)"
    }
    return $output
}

try {
    $violations = [Collections.Generic.List[string]]::new()
    $files = @(Invoke-Git ls-files)
    $prohibitedPaths = @(
        '^(state|events|history|logs)/',
        '^config/nodesmart\.json$',
        '(^|/)(id_rsa|id_ed25519)$',
        '\.(key|pem|p12|pfx)$'
    )
    $secretPatterns = @(
        '-----BEGIN (RSA |OPENSSH |EC |DSA )?PRIVATE KEY-----',
        '(?i)\btskey-[a-z]+-[a-z0-9_-]{12,}',
        '\bgh[pousr]_[A-Za-z0-9_]{20,}',
        '\bAKIA[0-9A-Z]{16}\b',
        '(?i)\b(password|passwd|api[_-]?key|access[_-]?token|client[_-]?secret|auth[_-]?token)\s*[:=]\s*["'']?[^\s"''@<>{}]{8,}'
    )
    $textExtensions = @('.md', '.py', '.js', '.html', '.json', '.ps1', '.sh',
        '.service', '.example', '.conf', '.template', '.txt', '')

    foreach ($relativePath in $files) {
        $normalized = $relativePath.Replace('\', '/')
        foreach ($pattern in $prohibitedPaths) {
            if ($normalized -match $pattern) {
                $violations.Add("prohibited tracked path: $normalized")
            }
        }
        $extension = [IO.Path]::GetExtension($normalized).ToLowerInvariant()
        if ($textExtensions -notcontains $extension) { continue }
        $fullPath = Join-Path $RepositoryPath $relativePath
        if (-not (Test-Path -LiteralPath $fullPath -PathType Leaf)) { continue }
        $content = Get-Content -LiteralPath $fullPath -Raw
        foreach ($pattern in $secretPatterns) {
            if ($content -match $pattern) {
                $violations.Add("possible secret material: $normalized")
                break
            }
        }
    }

    if ($violations.Count) {
        throw ($violations -join [Environment]::NewLine)
    }
    Write-Host "PUBLIC TREE PASS tracked_files=$($files.Count)"
}
catch {
    Write-Error "FAIL public-tree privacy guard: $($_.Exception.Message)"
    exit 1
}
