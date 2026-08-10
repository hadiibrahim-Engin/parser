#!/usr/bin/env bash
#
# Builds the CGMES MJAP Interface for the host platform.
#
# Runs the same sequence as scripts/build.ps1 and as the Azure pipeline, so a
# local build and a pipeline build are the same build.
#
# NOTE: PyInstaller does not cross-compile. On Linux or macOS this produces a
# native binary for THIS platform. A Windows .exe requires a Windows host.
#
# Usage:
#   ./scripts/build.sh              full build
#   ./scripts/build.sh --skip-tests packaging only; never ship the result

set -euo pipefail

projectRoot="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$projectRoot"

skipTests=0
for argument in "$@"; do
    case "$argument" in
        --skip-tests) skipTests=1 ;;
        -h|--help) sed -n '2,16p' "$0"; exit 0 ;;
        *) echo "Unknown argument: $argument" >&2; exit 2 ;;
    esac
done

if [[ -t 1 ]]; then
    cyan=$'\033[36m'; green=$'\033[32m'; yellow=$'\033[33m'; red=$'\033[31m'; reset=$'\033[0m'
else
    cyan=""; green=""; yellow=""; red=""; reset=""
fi

step()    { printf '\n%s==> %s%s\n' "$cyan" "$1" "$reset"; }
failure() { printf '\n%sBuild failed: %s%s\n' "$red" "$1" "$reset" >&2; exit 1; }

trap 'failure "interrupted"' INT TERM

command -v uv >/dev/null 2>&1 || failure "uv is not on PATH. See https://docs.astral.sh/uv/"

step "Syncing dependencies"
uv sync --extra gui --group dev

if [[ $skipTests -eq 1 ]]; then
    printf '\n%s[!] Tests skipped. Do not ship this build.%s\n' "$yellow" "$reset"
else
    step "Linting"
    uv run ruff check .

    step "Running tests"
    QT_QPA_PLATFORM=offscreen uv run pytest -q
fi

version="$(uv run python -c 'from cgmesparser.gui.version import __version__; print(__version__)')"
printf '%sBuilding version %s%s\n' "$cyan" "$version" "$reset"

step "Generating application icon"
uv run python packaging/makeIcon.py build/appIcon.ico

step "Removing previous build output"
rm -rf dist build/cgmesparser

step "Packaging with PyInstaller"
uv run pyinstaller --noconfirm --clean --distpath dist --workpath build packaging/cgmesparser.spec

# PyInstaller appends .exe only on Windows; elsewhere the binary is bare.
artifact="dist/CGMES-MJAP-Interface-${version}"
[[ -f "${artifact}.exe" ]] && artifact="${artifact}.exe"
[[ -f "$artifact" ]] || failure "PyInstaller reported success but $artifact does not exist."

step "Writing checksum"
if command -v sha256sum >/dev/null 2>&1; then
    (cd dist && sha256sum "$(basename "$artifact")" > "$(basename "$artifact").sha256")
else
    (cd dist && shasum -a 256 "$(basename "$artifact")" > "$(basename "$artifact").sha256")
fi

sizeMb="$(du -m "$artifact" | cut -f1)"
printf '\n%sBuild succeeded%s\n' "$green" "$reset"
printf '  %s  (%s MB)\n' "$artifact" "$sizeMb"
printf '  %s\n' "$(cat "${artifact}.sha256")"

if [[ "$(uname -s)" != MINGW* && "$(uname -s)" != MSYS* ]]; then
    printf '\n%sNote: this is a native %s binary, not a Windows .exe.%s\n' \
        "$yellow" "$(uname -s)" "$reset"
fi
