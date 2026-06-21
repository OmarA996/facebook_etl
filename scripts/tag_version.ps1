param(
    [Parameter(Mandatory = $true, Position = 0)]
    [string]$Version,

    [Parameter(Mandatory = $false, Position = 1)]
    [string]$Date
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

function Write-Info([string]$Message) {
    Write-Host $Message
}

if (-not $Date -or $Date.Trim().Length -eq 0) {
    $Date = Get-Date -Format "yyyy-MM-dd"
}

if ($Date -notmatch "^\d{4}-\d{2}-\d{2}$") {
    throw "Date must be in YYYY-MM-DD format."
}

$status = git status -sb 2>$null
if (-not $status) {
    throw "Not a git repository or git not available."
}

if ($status -notmatch "^##\s+\S+(\s+\[ahead.*\])?\s*$") {
    throw "Working tree is not clean. Commit your changes before tagging."
}

$tag = "v$Version-$Date"

$existing = git tag -l $tag
if ($existing) {
    throw "Tag already exists: $tag"
}

git tag -a $tag -m "Version $Version ($Date)"
Write-Info "Created tag: $tag"
