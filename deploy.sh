#!/bin/bash
# =============================================================================
# deploy.sh — ChargePlus 운영 배포 스크립트
#
# 사용법:
#   ./deploy.sh           # 변경 감지 후 필요한 서비스만 재빌드
#   ./deploy.sh --force   # 변경 감지 없이 backend + nginx 강제 재빌드
# =============================================================================

set -e

# ── 색상 ──────────────────────────────────────────────────────────────────────
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
CYAN='\033[0;36m'
NC='\033[0m'

log()  { echo -e "${GREEN}[deploy]${NC} $1"; }
info() { echo -e "${CYAN}[deploy]${NC} $1"; }
warn() { echo -e "${YELLOW}[deploy]${NC} $1"; }
err()  { echo -e "${RED}[deploy]${NC} $1"; }

# ── 경로 설정 ─────────────────────────────────────────────────────────────────
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

# ── 옵션 파싱 ─────────────────────────────────────────────────────────────────
FORCE=false
if [ "${1:-}" = "--force" ]; then
    FORCE=true
fi

echo ""
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "  ChargePlus Deploy  $(date '+%Y-%m-%d %H:%M:%S')"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"

# ── Step 1. git pull ──────────────────────────────────────────────────────────
log "Git pull origin master..."
OLD_HEAD=$(git rev-parse HEAD)
git pull origin master
NEW_HEAD=$(git rev-parse HEAD)

if [ "$OLD_HEAD" = "$NEW_HEAD" ] && [ "$FORCE" = false ]; then
    warn "이미 최신 상태입니다. 배포 없음."
    warn "강제 재배포하려면: ./deploy.sh --force"
    exit 0
fi

# ── Step 2. 변경 파일 감지 ────────────────────────────────────────────────────
if [ "$FORCE" = true ]; then
    warn "--force 옵션: backend + nginx 강제 재빌드"
    REBUILD_BACKEND=true
    REBUILD_GATEWAY=false
    RELOAD_NGINX=true
    RUN_MIGRATE=false
else
    CHANGED=$(git diff --name-only "$OLD_HEAD" "$NEW_HEAD")

    info "변경된 파일:"
    echo "$CHANGED" | sed 's/^/    /'
    echo ""

    REBUILD_BACKEND=false
    REBUILD_GATEWAY=false
    RELOAD_NGINX=false
    RUN_MIGRATE=false

    # nginx 설정 변경
    if echo "$CHANGED" | grep -q "^nginx/"; then
        RELOAD_NGINX=true
    fi

    # backend 코드/설정 변경
    if echo "$CHANGED" | grep -qE "^backend/|^docker-compose\.yml"; then
        REBUILD_BACKEND=true
    fi

    # gateway 코드/설정 변경
    if echo "$CHANGED" | grep -qE "^gateway/|^docker-compose\.yml"; then
        REBUILD_GATEWAY=true
    fi

    # 마이그레이션 파일 추가
    if echo "$CHANGED" | grep -qE "^backend/apps/.*/migrations/[0-9]{4}_"; then
        RUN_MIGRATE=true
    fi
fi

# ── Step 3. 배포 실행 ─────────────────────────────────────────────────────────
DEPLOYED=false

if [ "$REBUILD_BACKEND" = true ]; then
    log "backend 재빌드 중..."
    sudo docker compose up -d --build backend
    DEPLOYED=true
fi

if [ "$REBUILD_GATEWAY" = true ]; then
    log "gateway 재빌드 중..."
    sudo docker compose up -d --build gateway
    DEPLOYED=true
fi

if [ "$RELOAD_NGINX" = true ]; then
    log "nginx 설정 반영 중..."
    # 컨테이너 재시작 없이 설정만 무중단 리로드
    sudo docker compose exec nginx nginx -s reload
    DEPLOYED=true
fi

if [ "$DEPLOYED" = false ]; then
    warn "서비스 변경 없음 (docs, tests 등만 변경된 경우)."
    exit 0
fi

# ── Step 4. 마이그레이션 ──────────────────────────────────────────────────────
if [ "$RUN_MIGRATE" = true ]; then
    log "DB 마이그레이션 실행 중..."
    # backend 재시작 후 잠시 대기
    sleep 3
    sudo docker compose exec backend python manage.py migrate
fi

# ── Step 5. 헬스체크 ──────────────────────────────────────────────────────────
log "헬스체크 대기 중..."
sleep 4

HTTP_STATUS=$(curl -s -o /dev/null -w "%{http_code}" http://localhost/health)

if [ "$HTTP_STATUS" = "200" ]; then
    log "✓ 배포 성공! (HTTP $HTTP_STATUS)"
else
    err "✗ 헬스체크 실패 (HTTP $HTTP_STATUS)"
    err "컨테이너 상태:"
    sudo docker compose ps
    err "backend 최근 로그:"
    sudo docker compose logs backend --tail=20
    exit 1
fi

# ── Step 6. 배포 요약 ─────────────────────────────────────────────────────────
echo ""
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
info "배포 완료 요약"
echo "  커밋: $(git log -1 --oneline)"
if [ "$REBUILD_BACKEND" = true ]; then echo "  ✓ backend 재빌드"; fi
if [ "$REBUILD_GATEWAY" = true ]; then echo "  ✓ gateway 재빌드"; fi
if [ "$RELOAD_NGINX"   = true ]; then echo "  ✓ nginx 리로드"; fi
if [ "$RUN_MIGRATE"    = true ]; then echo "  ✓ DB 마이그레이션"; fi
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo ""
