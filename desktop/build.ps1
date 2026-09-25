[CmdletBinding()]
param([string]$Dotnet = 'dotnet')
$ErrorActionPreference = 'Stop'
$root = Split-Path $PSScriptRoot -Parent
Add-Type -AssemblyName System.IO.Compression.FileSystem
$payload = Join-Path $PSScriptRoot 'payload.zip'
# Build only from tracked release files, never local settings/history or .git.
$names = & git -C $root ls-files core web install config systemd
if ($LASTEXITCODE -ne 0) { throw 'Cannot read release file list' }
$stream = [IO.File]::Open($payload, [IO.FileMode]::Create)
try {
    $archive = [IO.Compression.ZipArchive]::new($stream, [IO.Compression.ZipArchiveMode]::Create)
    try {
        foreach ($name in $names) {
            if ($name -match '(^|/)(__pycache__|state|history|logs)/|^config/nodesmart.json$') { throw 'Private path in release' }
            [IO.Compression.ZipFileExtensions]::CreateEntryFromFile($archive, (Join-Path $root $name), $name) | Out-Null
        }
    } finally { $archive.Dispose() }
} finally { $stream.Dispose() }
& $Dotnet restore "$PSScriptRoot/BlueNode.Setup.csproj" --configfile "$PSScriptRoot/NuGet.Config" --locked-mode -r win-x64
if ($LASTEXITCODE -ne 0) { throw 'Dependency restore failed' }
& $Dotnet publish "$PSScriptRoot/BlueNode.Setup.csproj" --no-restore -c Release -r win-x64 --self-contained true -p:PublishSingleFile=true -p:IncludeNativeLibrariesForSelfExtract=true -p:DebugType=None -o "$PSScriptRoot/dist"
if ($LASTEXITCODE -ne 0) { throw 'Windows build failed' }
$check = Start-Process -FilePath "$PSScriptRoot/dist/BlueNode-Setup.exe" -ArgumentList '--check-package' -WindowStyle Hidden -Wait -PassThru
if ($check.ExitCode -ne 0) { throw 'Packaged runtime/payload check failed' }
Get-FileHash "$PSScriptRoot/dist/BlueNode-Setup.exe" -Algorithm SHA256
