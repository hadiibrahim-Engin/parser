#!/usr/bin/env bash
#
# Bumps the version, commits, tags and pushes - which starts a release build.
#
# version.py and pyproject.toml are updated together and a test asserts they
# match, so they cannot drift. Pushing the v* tag is what the Azure pipeline
# reacts to; nothing is built locally by this script.
#
# Usage:
#   ./scripts/release.sh 1.2.0
#   ./scripts/release.sh 1.2.0 --no-push    commit and tag only

set -euo pipefail

projectRoot="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$projectRoot"

if [[ $# -lt 1 ]]; then
    echo "usage: $0 <version> [--no-push]" >&2
    exit 2
fi

version="$1"
shift
noPush=0
for argument in "$@"; do
    case "$argument" in
        --no-push) noPush=1 ;;
        *) echo "Unknown argument: $argument" >&2; exit 2 ;;
    esac
done

if [[ -t 1 ]]; then
    cyan=$'\033[36m'; green=$'\033[32m'; yellow=$'\033[33m'; red=$'\033[31m'; reset=$'\033[0m'
else
    cyan=""; green=""; yellow=""; red=""; reset=""
fi

step()    { printf '%s==> %s%s\n' "$cyan" "$1" "$reset"; }
failure() {
    printf '\n%sRelease failed: %s%s\n' "$red" "$1" "$reset" >&2
    printf "%sCheck 'git status' - the version files may have been edited.%s\n" "$yellow" "$reset" >&2
    exit 1
}

[[ "$version" =~ ^[0-9]+\.[0-9]+\.[0-9]+$ ]] || failure "Version must look like 1.2.0, got '$version'."
[[ -z "$(git status --porcelain)" ]] || failure "The working tree is not clean. Commit or stash first."
[[ -z "$(git tag --list "v$version")" ]] || failure "Tag v$version already exists."

step "Updating src/cgmesparser/gui/version.py"
python3 - "$version" <<'PYTHON'
import re
import sys
from pathlib import Path

version = sys.argv[1]
path = Path("src/cgmesparser/gui/version.py")
path.write_text(
    re.sub(r'__version__ = "[^"]*"', f'__version__ = "{version}"', path.read_text(encoding="utf-8")),
    encoding="utf-8",
)
PYTHON

step "Updating pyproject.toml"
python3 - "$version" <<'PYTHON'
import re
import sys
from pathlib import Path

version = sys.argv[1]
path = Path("pyproject.toml")
# Only the first version key, which belongs to [project]; dependency pins
# further down the file must not be touched.
path.write_text(
    re.sub(r'(?m)^version = "[^"]*"$', f'version = "{version}"', path.read_text(encoding="utf-8"), count=1),
    encoding="utf-8",
)
PYTHON

step "Verifying the two agree"
uv run pytest tests/testCore.py -q -k testVersionMatchesPyproject \
    || failure "The version check failed. Nothing has been committed."

step "Committing and tagging"
git add src/cgmesparser/gui/version.py pyproject.toml
git commit -m "Release $version"
git tag -a "v$version" -m "Release $version"

if [[ $noPush -eq 1 ]]; then
    printf '\n%sCommitted and tagged v%s locally.%s\n' "$green" "$version" "$reset"
    printf 'Nothing is released until you run: git push && git push origin v%s\n' "$version"
    exit 0
fi

step "Pushing"
git push
git push origin "v$version"

printf '\n%sReleased %s%s\n' "$green" "$version" "$reset"
printf 'The Azure pipeline will build the executable and commit it to releases/.\n'
