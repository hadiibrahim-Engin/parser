<#
.SYNOPSIS
    Runs the cgmes2excel converter directly from the project's venv.

.DESCRIPTION
    uv is used ONLY to create the venv and install dependencies
    (`uv sync` from the project root). This script never calls `uv run` —
    it invokes the venv's own installed console script
    (.venv\Scripts\cgmes2excel.exe) directly, exactly like ./run does on
    macOS/Linux.

    The primary input is the $InputDir configured below: edit that one
    value and run the script. Everything else has a sensible default.
    All settings can also be overridden with command-line parameters
    without touching the file, e.g.:

        .\run.ps1 -InputDir 'C:\exports\2024-06' -Verbose

.EXAMPLE
    .\run.ps1
    Uses the $InputDir configured in the CONFIGURATION block below.

.EXAMPLE
    .\run.ps1 -InputDir 'C:\CGMES\Netz2024' -OutputFile 'C:\out\netz.xlsx' -Verbose

.NOTES
    Run once before first use, from the project root:
        uv sync
    That creates .venv and installs cgmes2excel into it. This script does
    not create or modify the venv.
#>

[CmdletBinding()]
param(
    # ---- CONFIGURATION -----------------------------------------------------
    # Edit this to point at your CGMES export: a directory, a single file,
    # or a .zip archive. This is the only value you strictly need to change.
    [string]$InputDir = 'C:\path\to\your\cgmes-export',

    # Workbook to write. Defaults to cgmes-export.xlsx next to this script.
    [string]$OutputFile = (Join-Path $PSScriptRoot 'cgmes-export.xlsx'),

    # Extra CIM classes to export as NETZELEMENTE rows in addition to the
    # defaults (ACLineSegment, PowerTransformer, ...), e.g. @('Breaker').
    [string[]]$IncludeClasses = @(),

    # If set, export exactly these CIM classes instead of the defaults.
    [string[]]$OnlyClasses = @(),

    # Write an uncoloured log file here in addition to the console. Leave
    # $null to skip.
    [string]$LogFile = $null,

    # Write the full per-cell derivation trace here. Leave $null to skip.
    [string]$TraceFile = $null,

    # Include DEBUG-level detail (per-class object counts, etc.).
    [switch]$VerboseLogging,

    # Disable ANSI colours even in a real terminal.
    [switch]$NoColor
    # -------------------------------------------------------------------------
)

$ErrorActionPreference = 'Stop'

function Write-Status {
    param([string]$Message, [ValidateSet('Info', 'Ok', 'Warn', 'Err')][string]$Level = 'Info')
    $colors = @{ Info = 'Cyan'; Ok = 'Green'; Warn = 'Yellow'; Err = 'Red' }
    $tags = @{ Info = '[wrapper]'; Ok = '[wrapper OK]'; Warn = '[wrapper WARN]'; Err = '[wrapper ERROR]' }
    Write-Host "$($tags[$Level]) $Message" -ForegroundColor $colors[$Level]
}

function Resolve-VenvExecutable {
    <# Locates the venv's own cgmes2excel entry point; never falls back to uv. #>
    $venvDir = Join-Path $PSScriptRoot '.venv'
    if (-not (Test-Path $venvDir)) {
        throw "No virtual environment found at '$venvDir'. Create it once with:`n    uv sync"
    }

    $candidates = @(
        (Join-Path $venvDir 'Scripts\cgmes2excel.exe'),  # Windows venv layout
        (Join-Path $venvDir 'bin\cgmes2excel')            # in case of a POSIX-style venv
    )
    $executable = $candidates | Where-Object { Test-Path $_ } | Select-Object -First 1

    if (-not $executable) {
        throw "cgmes2excel is not installed in '$venvDir'. Run this once from the project root:`n    uv sync"
    }
    return $executable
}

function Test-InputPath {
    param([string]$Path)
    if ($Path -eq 'C:\path\to\your\cgmes-export') {
        throw "InputDir still has its placeholder value. Edit `$InputDir at the top of run.ps1, " +
              "or pass -InputDir 'C:\your\export' on the command line."
    }
    if (-not (Test-Path $Path)) {
        throw "Input path does not exist: $Path"
    }
}

function Build-Arguments {
    $arguments = @($InputDir, '--output', $OutputFile)

    foreach ($cimClass in $IncludeClasses) { $arguments += @('--include-class', $cimClass) }
    foreach ($cimClass in $OnlyClasses) { $arguments += @('--only-class', $cimClass) }
    if ($LogFile) { $arguments += @('--log-file', $LogFile) }
    if ($TraceFile) { $arguments += @('--trace-file', $TraceFile) }
    if ($VerboseLogging) { $arguments += '--verbose' }
    if ($NoColor) { $arguments += '--no-color' }

    return $arguments
}

# --- main --------------------------------------------------------------------

try {
    Write-Status "Resolving venv executable..."
    $executable = Resolve-VenvExecutable
    Write-Status "Using $executable" -Level Ok

    Test-InputPath -Path $InputDir

    $arguments = Build-Arguments
    Write-Status "Running: $(Split-Path $executable -Leaf) $($arguments -join ' ')"
    Write-Host ""

    $stopwatch = [System.Diagnostics.Stopwatch]::StartNew()
    & $executable @arguments
    $exitCode = $LASTEXITCODE
    $stopwatch.Stop()

    Write-Host ""
    switch ($exitCode) {
        0 { Write-Status "Conversion succeeded in $([math]::Round($stopwatch.Elapsed.TotalSeconds, 1))s -> $OutputFile" -Level Ok }
        1 { Write-Status "Conversion ran but the written workbook failed schema validation. Check the log above." -Level Err }
        2 { Write-Status "Input error: no usable CGMES documents were found. Check `$InputDir." -Level Err }
        default { Write-Status "cgmes2excel exited with unexpected code $exitCode" -Level Err }
    }
    exit $exitCode
}
catch {
    Write-Status $_.Exception.Message -Level Err
    exit 2
}
