#!/bin/bash
set -euo pipefail
cd "$(dirname "$0")/.."
qgis_environment="${QGIS_ENV:-$(cd ../mjap_plugin && pwd)/.local-env}"
if [ ! -d "$qgis_environment" ]; then
  echo 'QGIS-Umgebung fehlt. QGIS_ENV auf eine Umgebung mit PyQGIS setzen.' >&2
  exit 1
fi
exec micromamba run -p "$qgis_environment" python -m excelToCsv.mapProject "$@"
