[CmdletBinding()]
param(
    [string]$OutputRoot
)

$ErrorActionPreference = "Stop"

$scriptDirectory = Split-Path -Parent $MyInvocation.MyCommand.Path
$workspaceRoot = (Resolve-Path (Join-Path $scriptDirectory "..")).Path

if ([string]::IsNullOrWhiteSpace($OutputRoot)) {
    $OutputRoot = Join-Path $workspaceRoot "output\DaySync_Windows_Portable"
}

$resolvedWorkspace = [System.IO.Path]::GetFullPath($workspaceRoot)
$resolvedOutput = [System.IO.Path]::GetFullPath($OutputRoot)

if (-not $resolvedOutput.StartsWith($resolvedWorkspace, [System.StringComparison]::OrdinalIgnoreCase)) {
    throw "OutputRoot must stay within workspace: $resolvedWorkspace"
}

$venvPython = Join-Path $resolvedWorkspace ".venv\Scripts\python.exe"
if (-not (Test-Path $venvPython)) {
    throw "Bundled runtime requires local virtualenv: $venvPython"
}

$desktopExe = Join-Path $resolvedWorkspace "apps\desktop\src-tauri\target\release\daysync_desktop.exe"
$releaseRuntime = Join-Path $resolvedOutput "daysync_runtime"
$releaseExe = Join-Path $resolvedOutput "DaySync.exe"
$releasePython = Join-Path $releaseRuntime ".venv\Scripts\python.exe"
$ffmpegRuntimeRoot = Join-Path $resolvedWorkspace "tools\ffmpeg\windows-x64"

Write-Host "Building desktop release..."
pnpm --dir $resolvedWorkspace --filter desktop tauri build
if ($LASTEXITCODE -ne 0) {
    throw "Failed to build desktop release."
}

if (-not (Test-Path $desktopExe)) {
    throw "Desktop executable was not generated: $desktopExe"
}

if (Test-Path $resolvedOutput) {
    Remove-Item -LiteralPath $resolvedOutput -Recurse -Force
}

New-Item -ItemType Directory -Path $resolvedOutput | Out-Null
New-Item -ItemType Directory -Path $releaseRuntime | Out-Null

Copy-Item -LiteralPath $desktopExe -Destination $releaseExe
Copy-Item -LiteralPath (Join-Path $resolvedWorkspace "services") -Destination (Join-Path $releaseRuntime "services") -Recurse
Copy-Item -LiteralPath (Join-Path $resolvedWorkspace "packages") -Destination (Join-Path $releaseRuntime "packages") -Recurse
Copy-Item -LiteralPath (Join-Path $resolvedWorkspace ".venv") -Destination (Join-Path $releaseRuntime ".venv") -Recurse
Copy-Item -LiteralPath (Join-Path $resolvedWorkspace "pyproject.toml") -Destination (Join-Path $releaseRuntime "pyproject.toml")
Copy-Item -LiteralPath (Join-Path $resolvedWorkspace "README.md") -Destination (Join-Path $releaseRuntime "README.md")

if (Test-Path (Join-Path $ffmpegRuntimeRoot "current")) {
    New-Item -ItemType Directory -Path (Join-Path $releaseRuntime "tools\ffmpeg\windows-x64") -Force | Out-Null
    Copy-Item -LiteralPath (Join-Path $ffmpegRuntimeRoot "current") -Destination (Join-Path $releaseRuntime "tools\ffmpeg\windows-x64\current") -Recurse
    if (Test-Path (Join-Path $ffmpegRuntimeRoot "manifest.json")) {
        Copy-Item -LiteralPath (Join-Path $ffmpegRuntimeRoot "manifest.json") -Destination (Join-Path $releaseRuntime "tools\ffmpeg\windows-x64\manifest.json")
    }
}

$releaseManifest = @{
    built_at = (Get-Date).ToString("s")
    workspace_root = $resolvedWorkspace
    release_exe = $releaseExe
    runtime_root = $releaseRuntime
} | ConvertTo-Json -Depth 3

$manifestPath = Join-Path $resolvedOutput "release-manifest.json"
$releaseManifest | Set-Content -LiteralPath $manifestPath -Encoding UTF8

$env:PYTHONPATH = "$releaseRuntime;$($releaseRuntime)\packages\daysync_core\src"
& $releasePython -c "from services.api.main import app; print(app.title)"
if ($LASTEXITCODE -ne 0) {
    throw "Release runtime smoke import failed."
}

Write-Host "Release ready."
Write-Host "release_root=$resolvedOutput"
Write-Host "release_exe=$releaseExe"
Write-Host "runtime_root=$releaseRuntime"
