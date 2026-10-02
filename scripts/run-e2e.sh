#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
API_PORT="${E2E_API_PORT:-8010}"
WEB_PORT="${E2E_WEB_PORT:-3010}"
API_URL="http://127.0.0.1:${API_PORT}"
WEB_URL="http://127.0.0.1:${WEB_PORT}"
LOG_DIR="${E2E_LOG_DIR:-${ROOT}/.e2e-logs}"
mkdir -p "${LOG_DIR}"

if ! curl -sf "${API_URL}/health/ready" >/dev/null 2>&1; then
  if command -v docker >/dev/null 2>&1; then
    docker compose -f "${ROOT}/docker-compose.yml" up -d postgres redis
  fi
fi

export OPSPILOT_DATABASE_URL="${OPSPILOT_DATABASE_URL:-postgresql+asyncpg://opspilot:opspilot@localhost:5432/opspilot}"
export OPSPILOT_REDIS_URL="${OPSPILOT_REDIS_URL:-redis://localhost:6379/0}"
export OPSPILOT_STEP_DELAY_MS="${OPSPILOT_STEP_DELAY_MS:-0}"
export OPSPILOT_VAULT_MASTER_KEY="${OPSPILOT_VAULT_MASTER_KEY:-ci-vault-master-key-must-be-32-chars}"
export OPSPILOT_CORS_ORIGINS="http://127.0.0.1:${WEB_PORT},http://localhost:${WEB_PORT}"
export OPSPILOT_RATE_LIMIT_PER_MINUTE="${OPSPILOT_RATE_LIMIT_PER_MINUTE:-1000}"
export OPSPILOT_REGISTER_RATE_PER_MINUTE="${OPSPILOT_REGISTER_RATE_PER_MINUTE:-1000}"
export OPSPILOT_LOGIN_RATE_PER_MINUTE="${OPSPILOT_LOGIN_RATE_PER_MINUTE:-1000}"
export OPSPILOT_INGEST_RATE_PER_MINUTE="${OPSPILOT_INGEST_RATE_PER_MINUTE:-1000}"
export OPSPILOT_APPROVAL_RATE_PER_MINUTE="${OPSPILOT_APPROVAL_RATE_PER_MINUTE:-1000}"
export OPSPILOT_TICKET_RATE_PER_MINUTE="${OPSPILOT_TICKET_RATE_PER_MINUTE:-1000}"
export OPSPILOT_DEMO_SEED_ENABLED="${OPSPILOT_DEMO_SEED_ENABLED:-true}"
export OPSPILOT_DEMO_PASSWORD="${OPSPILOT_DEMO_PASSWORD:-AcmeFlow-operator-12}"

(
  cd "${ROOT}/backend"
  if [[ -x .venv/bin/alembic ]]; then
    .venv/bin/alembic upgrade head
  else
    alembic upgrade head
  fi
)
(
  cd "${ROOT}"
  if [[ -x "${ROOT}/backend/.venv/bin/python" ]]; then
    "${ROOT}/backend/.venv/bin/python" scripts/seed_demo.py
    "${ROOT}/backend/.venv/bin/python" scripts/reset_demo.py
  else
    python scripts/seed_demo.py
    python scripts/reset_demo.py
  fi
)

BACKEND_PID=""
FRONTEND_PID=""
cleanup() {
  if [[ -n "${BACKEND_PID}" ]]; then kill "${BACKEND_PID}" 2>/dev/null || true; fi
  if [[ -n "${FRONTEND_PID}" ]]; then kill "${FRONTEND_PID}" 2>/dev/null || true; fi
}
trap cleanup EXIT

(
  cd "${ROOT}/backend"
  if [[ -x .venv/bin/uvicorn ]]; then
    .venv/bin/uvicorn app.main:app --host 127.0.0.1 --port "${API_PORT}"
  else
    uvicorn app.main:app --host 127.0.0.1 --port "${API_PORT}"
  fi
) >"${LOG_DIR}/backend.log" 2>&1 &
BACKEND_PID=$!

for _ in $(seq 1 90); do
  if curl -sf "${API_URL}/health/ready" >/dev/null; then
    break
  fi
  if ! kill -0 "${BACKEND_PID}" 2>/dev/null; then
    echo "backend exited before ready" >&2
    cat "${LOG_DIR}/backend.log" >&2 || true
    exit 1
  fi
  sleep 1
done
curl -sf "${API_URL}/health/ready" >/dev/null

(
  cd "${ROOT}/frontend"
  NEXT_PUBLIC_API_URL="${API_URL}" npx next dev --hostname 127.0.0.1 --port "${WEB_PORT}"
) >"${LOG_DIR}/frontend.log" 2>&1 &
FRONTEND_PID=$!

for _ in $(seq 1 90); do
  if curl -sf "${WEB_URL}" >/dev/null; then
    break
  fi
  if ! kill -0 "${FRONTEND_PID}" 2>/dev/null; then
    echo "frontend exited before ready" >&2
    cat "${LOG_DIR}/frontend.log" >&2 || true
    exit 1
  fi
  sleep 1
done
curl -sf "${WEB_URL}" >/dev/null

cd "${ROOT}/frontend"
PLAYWRIGHT_BASE_URL="${WEB_URL}" E2E_API_URL="${API_URL}" npx playwright test "$@"
