#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "${ROOT_DIR}"

echo "[info] ContactIQ nightly alternative-solution check"
echo "[info] repo: ${ROOT_DIR}"

echo "[step] Python syntax compile"
python3 -m py_compile server.py enrichment_router.py provider_adapters.py enrichment_telemetry.py

echo "[step] Core adapter/router/telemetry tests"
python3 -m unittest -q test_provider_adapters.py test_enrichment_router.py test_enrichment_telemetry.py

echo "[step] Sanity check telemetry route presence"
if ! grep -q "@app.route('/api/v1/enrichment/telemetry'" server.py; then
  echo "[error] telemetry route not found in server.py"
  exit 1
fi

echo "[done] ContactIQ nightly alternative-solution check passed"