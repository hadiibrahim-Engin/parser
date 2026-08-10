<#
.SYNOPSIS
    Prints (or saves) the project's current directory architecture as a tree.

.DESCRIPTION
    Walks the repository from its root and renders an ASCII tree of every
    directory and file, skipping the usual noise (.git, .venv, __pycache__,
    build output, editor folders, ...) so the result reflects the source tree,
    not incidental build state.

.PARAMETER Path
    Root to render from. Defaults to the repository root (the parent of this
    script's folder).

.PARAMETER OutFile
    If given, the tree is written to this file (UTF-8) instead of the console.

.PARAMETER MaxDepth
    How many levels deep to descend. Default: unlimited.

.PARAMETER IncludeFiles
    Include files as well as directories. Default: directories only, since
    that is usually what "the architecture" means; pass this switch for a
    full listing.

.EXAMPLE
    .\scripts\generate-tree.ps1
    Prints the directory structure to the console.

.EXAMPLE
    .\scripts\generate-tree.ps1 -IncludeFiles -OutFile docs\tree.txt
    Writes a full file-and-directory tree to docs\tree.txt.
#>

[CmdletBinding()]
param(
    [string]$Path = (Split-Path -Parent $PSScriptRoot),
    [string]$OutFile,
    [int]$MaxDepth = [int]::MaxValue,
    [switch]$IncludeFiles
)

$ErrorActionPreference = 'Stop'

# Directories that are noise for "the architecture as it is now": VCS internals,
# virtual environments, caches, build output and editor state.
$excludedDirectories = @(
    '.git', '.venv', 'venv', '__pycache__', '.pytest_cache', '.ruff_cache',
    '.mypy_cache', 'build', 'dist', '.idea', '.vscode', 'node_modules',
    '.egg-info'
)

function Test-ExcludedDirectory {
    param([System.IO.DirectoryInfo]$Directory)
    foreach ($pattern in $excludedDirectories) {
        if ($Directory.Name -eq $pattern -or $Directory.Name.EndsWith($pattern)) {
            return $true
        }
    }
    return $false
}

function Get-TreeLines {
    param(
        [string]$Directory,
        [string]$Prefix = '',
        [int]$Depth = 0
    )

    # A List[string] implements IEnumerable, so PowerShell unrolls it into
    # individual pipeline items on return - AddRange then receives $null for
    # zero items, or a single string for one. -NoEnumerate keeps it one object.
    $lines = [System.Collections.Generic.List[string]]::new()
    if ($Depth -ge $MaxDepth) {
        Write-Output -NoEnumerate $lines
        return
    }

    # @() forces an array even when Where-Object matches nothing or exactly
    # one item, so .Count and indexing always behave.
    $entries = @(
        Get-ChildItem -LiteralPath $Directory -Force |
            Where-Object {
                if ($_.PSIsContainer) { -not (Test-ExcludedDirectory $_) }
                else { $IncludeFiles }
            } |
            Sort-Object -Property @{ Expression = { -not $_.PSIsContainer } }, Name
    )

    $count = $entries.Count
    for ($index = 0; $index -lt $count; $index++) {
        $entry = $entries[$index]
        $isLast = ($index -eq $count - 1)
        $connector = if ($isLast) { '`-- ' } else { '|-- ' }
        $label = if ($entry.PSIsContainer) { "$($entry.Name)/" } else { $entry.Name }

        $lines.Add("$Prefix$connector$label")

        if ($entry.PSIsContainer) {
            $childPrefix = $Prefix + $(if ($isLast) { '    ' } else { '|   ' })
            $child = Get-TreeLines -Directory $entry.FullName -Prefix $childPrefix -Depth ($Depth + 1)
            $lines.AddRange($child)
        }
    }

    Write-Output -NoEnumerate $lines
}

$resolvedPath = (Resolve-Path -LiteralPath $Path).ProviderPath
$rootLabel = Split-Path -Leaf $resolvedPath
$output = [System.Collections.Generic.List[string]]::new()
$output.Add("$rootLabel/")
$output.AddRange((Get-TreeLines -Directory $resolvedPath))

$rendered = $output -join "`n"

if ($OutFile) {
    $outDirectory = Split-Path -Parent $OutFile
    if ($outDirectory -and -not (Test-Path $outDirectory)) {
        New-Item -ItemType Directory -Force -Path $outDirectory | Out-Null
    }
    Set-Content -Path $OutFile -Value $rendered -Encoding utf8
    Write-Host "Wrote tree to $OutFile ($($output.Count - 1) entries)" -ForegroundColor Green
}
else {
    $rendered
}
