<#
.SYNOPSIS
    Builds the CGMES MJAP Interface Windows executable.

.DESCRIPTION
    Runs the same sequence the Azure pipeline runs, so a local build and a
    pipeline build are the same build: dependency sync, lint, tests, then
    PyInstaller and a checksum.

    The executable is written to dist\CGMES-MJAP-Interface-<version>.exe with a
    matching .sha256 file beside it.

.PARAMETER SkipTests
    Skip ruff and pytest. Intended for iterating on packaging only; never use
    it for a release build.

.EXAMPLE
    .\scripts\build.ps1

.EXAMPLE
    .\scripts\build.ps1 -SkipTests
#>

[CmdletBinding()]
param(
    [switch]$SkipTests
)

$ErrorActionPreference = 'Stop'
$projectRoot = Split-Path -Parent $PSScriptRoot

function Write-Step {
    param([string]$Message)
    Write-Host ""
    Write-Host "==> $Message" -ForegroundColor Cyan
}

function Invoke-Step {
    param([string]$Message, [scriptblock]$Action)
    Write-Step $Message
    & $Action
    if ($LASTEXITCODE -ne 0) {
        throw "$Message failed with exit code $LASTEXITCODE"
    }
}

Push-Location $projectRoot
try {
    if (-not (Get-Command uv -ErrorAction SilentlyContinue)) {
        throw "uv is not on PATH. Install it from https://docs.astral.sh/uv/ and try again."
    }

    Invoke-Step "Syncing dependencies" { uv sync --extra gui --group dev }

    if ($SkipTests) {
        Write-Host "`n[!] Tests skipped. Do not ship this build." -ForegroundColor Yellow
    }
    else {
        Invoke-Step "Linting" { uv run ruff check . }
        Invoke-Step "Running tests" {
            $env:QT_QPA_PLATFORM = 'offscreen'
            uv run pytest -q
        }
    }

    $version = (uv run python -c "from cgmesparser.gui.version import __version__; print(__version__)").Trim()
    Write-Host "Building version $version" -ForegroundColor Cyan

    Invoke-Step "Generating application icon" {
        uv run python packaging/makeIcon.py build/appIcon.ico
    }

    Write-Step "Removing previous build output"
    Remove-Item -Recurse -Force (Join-Path $projectRoot 'dist') -ErrorAction SilentlyContinue
    Remove-Item -Recurse -Force (Join-Path $projectRoot 'build\cgmesparser') -ErrorAction SilentlyContinue

    Invoke-Step "Packaging with PyInstaller" {
        uv run pyinstaller --noconfirm --clean --distpath dist --workpath build packaging/cgmesparser.spec
    }

    $executable = Join-Path $projectRoot "dist\CGMES-MJAP-Interface-$version.exe"
    if (-not (Test-Path $executable)) {
        throw "PyInstaller reported success but $executable does not exist."
    }

    Write-Step "Writing checksum"
    $hash = (Get-FileHash -Algorithm SHA256 -Path $executable).Hash.ToLower()
    "$hash  $(Split-Path $executable -Leaf)" | Set-Content -Path "$executable.sha256" -Encoding ascii

    $sizeMb = [math]::Round((Get-Item $executable).Length / 1MB, 1)
    Write-Host ""
    Write-Host "Build succeeded" -ForegroundColor Green
    Write-Host "  $executable  ($sizeMb MB)"
    Write-Host "  SHA256 $hash"
    exit 0
}
catch {
    Write-Host ""
    Write-Host "Build failed: $($_.Exception.Message)" -ForegroundColor Red
    exit 1
}
finally {
    Pop-Location
}
