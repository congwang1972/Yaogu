#!/usr/bin/env bash
# 生产/本地启动：先构建前端，再由后端托管 dist 与 API。
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

PYTHON="${PYTHON:-$ROOT/venv/bin/python}"
if [[ ! -x "$PYTHON" ]]; then
  echo "[ERROR] 未找到 $PYTHON，请先创建 venv：python -m venv venv && pip install -r requirements.txt" >&2
  exit 1
fi

exec "$PYTHON" -m uvicorn src.main:app \
  --host "${HOST:-0.0.0.0}" \
  --port "${PORT:-8000}" \
  --env-file "${ENV_FILE:-$ROOT/.env}"
