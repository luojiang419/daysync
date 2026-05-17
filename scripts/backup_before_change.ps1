[CmdletBinding()]
param(
    [string]$RepositoryRoot
)

$ErrorActionPreference = "Stop"

if ([string]::IsNullOrWhiteSpace($RepositoryRoot)) {
    $scriptDirectory = Split-Path -Parent $MyInvocation.MyCommand.Path
    $RepositoryRoot = (Resolve-Path (Join-Path $scriptDirectory "..")).Path
}

function Invoke-Git {
    param(
        [Parameter(Mandatory = $true)]
        [string[]]$Arguments
    )

    & git -C $RepositoryRoot @Arguments
    if ($LASTEXITCODE -ne 0) {
        throw "git $($Arguments -join ' ') failed."
    }
}

$resolvedRoot = [System.IO.Path]::GetFullPath((Resolve-Path $RepositoryRoot).Path)
$repoTopLevel = [System.IO.Path]::GetFullPath((& git -C $resolvedRoot rev-parse --show-toplevel).Trim())
if ($LASTEXITCODE -ne 0) {
    throw "Current directory is not a git repository: $resolvedRoot"
}

if ($repoTopLevel -ne $resolvedRoot) {
    throw "Script must run from repository root. Actual root: $repoTopLevel"
}

$currentBranch = (& git -C $resolvedRoot branch --show-current).Trim()
if ($LASTEXITCODE -ne 0) {
    throw "Unable to determine current branch."
}

if ($currentBranch -ne "main") {
    throw "Current branch is '$currentBranch'. DaySync backup requires branch main."
}

$remoteUrl = (& git -C $resolvedRoot remote get-url origin).Trim()
if ($LASTEXITCODE -ne 0 -or [string]::IsNullOrWhiteSpace($remoteUrl)) {
    throw "Remote origin is not configured."
}

Invoke-Git -Arguments @("fetch", "origin", "main", "--tags")

$timestamp = Get-Date
$tagStamp = $timestamp.ToString("yyyyMMdd-HHmmss")
$commitStamp = $timestamp.ToString("yyyy-MM-dd HH:mm:ss")
$statusOutput = (& git -C $resolvedRoot status --porcelain)
if ($LASTEXITCODE -ne 0) {
    throw "Unable to read working tree status."
}

if (-not [string]::IsNullOrWhiteSpace(($statusOutput -join ""))) {
    Invoke-Git -Arguments @("add", "-A")
    Invoke-Git -Arguments @("commit", "-m", "backup: pre-change snapshot $commitStamp")
}

Invoke-Git -Arguments @("push", "origin", "main")

$tagName = "backup/$tagStamp"
$existingTag = (& git -C $resolvedRoot tag --list $tagName).Trim()
if ($LASTEXITCODE -ne 0) {
    throw "Unable to inspect local tag state."
}
if (-not [string]::IsNullOrWhiteSpace($existingTag)) {
    throw "Backup tag already exists: $tagName"
}

Invoke-Git -Arguments @("tag", "-a", $tagName, "-m", "Backup snapshot $commitStamp")
Invoke-Git -Arguments @("push", "origin", $tagName)

$commitSha = (& git -C $resolvedRoot rev-parse HEAD).Trim()
if ($LASTEXITCODE -ne 0) {
    throw "Unable to read current commit SHA."
}

Write-Host "Backup completed."
Write-Host "repository_root=$resolvedRoot"
Write-Host "remote_url=$remoteUrl"
Write-Host "commit_sha=$commitSha"
Write-Host "tag_name=$tagName"
