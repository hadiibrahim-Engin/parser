<#
.SYNOPSIS
    Bumps the version, commits, tags and pushes - which starts a release build.

.DESCRIPTION
    version.py and pyproject.toml are updated together and a test asserts they
    match, so they cannot drift. Pushing the v* tag is what the Azure pipeline
    reacts to; nothing is built locally by this script.

.PARAMETER Version
    The new version, as MAJOR.MINOR.PATCH.

.PARAMETER NoPush
    Create the commit and tag but do not push. Nothing is released until the
    tag reaches the remote.

.EXAMPLE
    .\scripts\release.ps1 -Version 1.2.0
#>

[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)][string]$Version,
    [switch]$NoPush
)

$ErrorActionPreference = 'Stop'
$projectRoot = Split-Path -Parent $PSScriptRoot

function Write-Step {
    param([string]$Message)
    Write-Host "==> $Message" -ForegroundColor Cyan
}

Push-Location $projectRoot
try {
    if ($Version -notmatch '^\d+\.\d+\.\d+$') {
        throw "Version must look like 1.2.0, got '$Version'."
    }

    $status = git status --porcelain
    if ($status) {
        throw "The working tree is not clean. Commit or stash your changes first."
    }

    $existingTag = git tag --list "v$Version"
    if ($existingTag) {
        throw "Tag v$Version already exists."
    }

    Write-Step "Updating src/cgmesparser/gui/version.py"
    $versionFile = Join-Path $projectRoot 'src\cgmesparser\gui\version.py'
    $versionText = Get-Content $versionFile -Raw
    $versionText = [regex]::Replace($versionText, '__version__ = "[^"]*"', "__version__ = `"$Version`"")
    Set-Content -Path $versionFile -Value $versionText -NoNewline -Encoding utf8

    Write-Step "Updating pyproject.toml"
    $pyprojectFile = Join-Path $projectRoot 'pyproject.toml'
    $pyprojectText = Get-Content $pyprojectFile -Raw
    # Only the first version key, which belongs to [project]; dependency pins
    # further down the file must not be touched.
    $pyprojectText = [regex]::Replace($pyprojectText, '(?m)^version = "[^"]*"$', "version = `"$Version`"", 1)
    Set-Content -Path $pyprojectFile -Value $pyprojectText -NoNewline -Encoding utf8

    Write-Step "Verifying the two agree"
    uv run pytest tests/testCore.py -q -k testVersionMatchesPyproject
    if ($LASTEXITCODE -ne 0) {
        throw "The version check failed. Nothing has been committed."
    }

    Write-Step "Committing and tagging"
    git add src/cgmesparser/gui/version.py pyproject.toml
    git commit -m "Release $Version"
    git tag -a "v$Version" -m "Release $Version"

    if ($NoPush) {
        Write-Host ""
        Write-Host "Committed and tagged v$Version locally." -ForegroundColor Green
        Write-Host "Nothing is released until you run: git push && git push origin v$Version"
        exit 0
    }

    Write-Step "Pushing"
    git push
    git push origin "v$Version"

    Write-Host ""
    Write-Host "Released $Version" -ForegroundColor Green
    Write-Host "The Azure pipeline will build the executable and commit it to releases/."
    exit 0
}
catch {
    Write-Host ""
    Write-Host "Release failed: $($_.Exception.Message)" -ForegroundColor Red
    Write-Host "Check 'git status' - the version files may have been edited." -ForegroundColor Yellow
    exit 1
}
finally {
    Pop-Location
}
