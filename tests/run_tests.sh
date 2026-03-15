#!/bin/bash
# ChargePlus 전체 테스트 실행 스크립트
# 사용법: bash tests/run_tests.sh

set -e
cd "$(dirname "$0")/.."

GREEN='\033[0;32m'
RED='\033[0;31m'
YELLOW='\033[1;33m'
NC='\033[0m'

ok()   { echo -e "${GREEN}✓${NC} $1"; }
fail() { echo -e "${RED}✗${NC} $1"; exit 1; }
info() { echo -e "${YELLOW}→${NC} $1"; }

echo ""
echo "============================================================"
echo "  ChargePlus OCPP 1.6 CSMS - Integration Test Runner"
echo "============================================================"
echo ""

# ── 1. 스택 기동 ────────────────────────────────────────────────
info "Starting Docker stack (dev mode)..."
docker compose -f docker-compose.yml -f docker-compose.dev.yml up -d --build
ok "Docker stack started"

# ── 2. 서비스 준비 대기 ─────────────────────────────────────────
info "Waiting for services to be ready..."
MAX_WAIT=90
ELAPSED=0
until docker compose exec -T backend python manage.py check --deploy 2>/dev/null || \
      curl -s http://localhost:8000/api/v1/stations/ > /dev/null 2>&1; do
    if [ $ELAPSED -ge $MAX_WAIT ]; then
        fail "Services did not start within ${MAX_WAIT}s"
    fi
    sleep 3
    ELAPSED=$((ELAPSED + 3))
    echo -n "."
done
echo ""
ok "Backend is ready (${ELAPSED}s)"

# Gateway 준비 확인
until curl -s http://localhost:9000/health > /dev/null 2>&1; do
    sleep 2
    echo -n "."
done
ok "Gateway is ready"

# Dispatcher 준비 확인 (3초 대기)
sleep 3
ok "Dispatcher started"

# ── 3. 테스트 데이터 세팅 ────────────────────────────────────────
info "Setting up test data..."
docker compose exec -T backend python /app/tests/setup_testdata.py
ok "Test data ready"

# ── 4. 테스트 패키지 설치 ────────────────────────────────────────
info "Installing test dependencies..."
pip install -q -r tests/requirements.txt
ok "Test dependencies installed"

# ── 5. CP 시뮬레이터 실행 (백그라운드) ─────────────────────────
info "Starting CP simulator in background..."
python tests/cp_simulator.py --station-id CP-TEST-001 --host localhost --port 9000 --listen &
SIMULATOR_PID=$!
ok "Simulator started (PID=$SIMULATOR_PID)"

# 시뮬레이터가 BootNotification을 보낼 시간
sleep 4

# ── 6. API 테스트 실행 ──────────────────────────────────────────
info "Running Mobile API tests..."
python tests/test_api.py \
    --base-url http://localhost:8000 \
    --station-id CP-TEST-001 \
    --username testuser \
    --password 'testpass1234'

# ── 7. 시뮬레이터 종료 ──────────────────────────────────────────
kill $SIMULATOR_PID 2>/dev/null || true
ok "Simulator stopped"

# ── 8. 서비스 로그 요약 ─────────────────────────────────────────
echo ""
echo "============================================================"
echo "  Service Logs (last 20 lines each)"
echo "============================================================"
echo ""
echo "--- Backend ---"
docker compose logs --tail=20 backend 2>&1 | grep -E "INFO|WARNING|ERROR" | tail -15

echo ""
echo "--- Dispatcher ---"
docker compose logs --tail=20 dispatcher 2>&1 | tail -15

echo ""
echo "--- Worker-Core ---"
docker compose logs --tail=20 worker-core 2>&1 | tail -10

echo ""
echo "============================================================"
echo -e "  ${GREEN}ALL TESTS COMPLETED SUCCESSFULLY ✓${NC}"
echo "============================================================"
echo ""
echo "  Django Admin: http://localhost:8000/admin/"
echo "  Gateway:      ws://localhost:9000/ocpp/1.6/{station_id}"
echo ""
echo "스택을 중지하려면: docker compose down"
echo ""
