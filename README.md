# ChargePlus OCPP 1.6 CSMS

OCPP 1.6 기반 전기차 충전 관리 시스템 (Charge Point Management System)

- **백엔드:** Django 5.2 + Celery + PostgreSQL + Redis
- **게이트웨이:** FastAPI (OCPP WebSocket)
- **인프라:** GCP GCE (서울 리전) + Docker Compose
- **도메인:** https://chargeplus.kr

---

## 목차

1. [시스템 아키텍처](#1-시스템-아키텍처)
2. [프로젝트 구조](#2-프로젝트-구조)
3. [로컬 개발 환경 설정](#3-로컬-개발-환경-설정)
4. [GCP 배포](#4-gcp-배포)
5. [도메인 및 HTTPS 설정](#5-도메인-및-https-설정)
6. [API 명세](#6-api-명세)
7. [OCPP 1.6 메시지 처리](#7-ocpp-16-메시지-처리)
8. [테스트](#8-테스트)
9. [운영 관리](#9-운영-관리)
10. [트러블슈팅 히스토리](#10-트러블슈팅-히스토리)

---

## 1. 시스템 아키텍처

```
[충전기 CP]
    │  WebSocket (OCPP 1.6)
    ▼
[Nginx :80/:443]
    ├── /ocpp/  ──────────────► [FastAPI Gateway × 2]
    │                               │  Redis LPUSH ocpp:upstream
    │                               ▼
    └── /api/, /admin/ ──► [Django Backend]
                               │
                               ├── [Dispatcher] ◄── Redis BRPOP ocpp:upstream
                               │       │  Celery task dispatch
                               │       ▼
                               ├── [Worker: core × 2]        - BootNotification, Heartbeat
                               ├── [Worker: telemetry × 4]   - MeterValues, StatusNotification
                               ├── [Worker: management × 1]  - FirmwareUpdate, Diagnostics
                               └── [Worker: commands × 1]    - RemoteStart/Stop, ChangeConfig

[PostgreSQL]  ◄── Django ORM
[Redis]       ◄── Celery Broker / Cache / PubSub
```

### 메시지 흐름 (CP → CSMS)

```
CP → WebSocket → Gateway → Redis(ocpp:upstream) → Dispatcher → Celery Worker
                                                                      │
CP ← WebSocket ← Gateway ← Redis(ocpp:response:{msg_id}) ◄──────────┘
```

### 메시지 흐름 (CSMS → CP, 원격 명령)

```
Django API → GatewayClient → Redis(ocpp:cmd:{station_id}) → Gateway
                                                                │  WebSocket
                                                               CP
CP → WebSocket → Gateway → Redis(ocpp:cmdresult:{msg_id}) → Django API
```

---

## 2. 프로젝트 구조

```
ChargePlus/
├── backend/                        # Django 백엔드
│   ├── chargeplus/
│   │   ├── settings/
│   │   │   ├── base.py             # 공통 설정
│   │   │   ├── development.py      # 개발 환경 (DEBUG=True)
│   │   │   └── production.py       # 운영 환경 (DEBUG=False)
│   │   ├── celery.py               # Celery 앱 정의
│   │   └── urls.py
│   ├── apps/
│   │   ├── ocpp16/                 # OCPP 1.6 핵심 앱
│   │   │   ├── tasks/
│   │   │   │   ├── core.py         # BootNotification, Heartbeat, Authorize
│   │   │   │   ├── telemetry.py    # MeterValues, StatusNotification
│   │   │   │   ├── management.py   # FirmwareUpdate, Diagnostics, DataTransfer
│   │   │   │   └── commands.py     # RemoteStart/Stop, ChangeConfig, Reset 등
│   │   │   ├── services/
│   │   │   │   ├── authorization.py  # RFID/App 토큰 인증
│   │   │   │   ├── gateway_client.py # CSMS→CP 명령 전송 클라이언트
│   │   │   │   ├── pricing.py        # 충전 요금 계산
│   │   │   │   └── notification.py   # 알림 서비스
│   │   │   └── management/commands/
│   │   │       └── run_ocpp_dispatcher.py  # 디스패처 관리 명령
│   │   ├── stations/               # 충전소 모델
│   │   ├── transactions/           # 충전 거래 모델
│   │   ├── authorization/          # RFID/App 토큰 모델
│   │   ├── mobile_api/             # 모바일 앱 API
│   │   ├── config/                 # CSMS 설정 변수
│   │   ├── reservations/           # 예약 모델
│   │   └── smart_charging/         # 스마트 충전 모델
│   ├── requirements.txt
│   ├── Dockerfile
│   └── entrypoint.sh
├── gateway/                        # FastAPI 게이트웨이
│   ├── api/
│   │   └── websocket.py            # OCPP WebSocket 엔드포인트
│   ├── broker/
│   │   ├── publisher.py            # Redis 발행
│   │   ├── subscriber.py           # Redis 구독 (downstream)
│   │   └── redis_client.py
│   ├── core/
│   │   ├── connection_registry.py  # WebSocket 연결 관리
│   │   ├── message_parser.py       # OCPP 메시지 파싱
│   │   └── schema_validator.py     # OCPP JSON Schema 검증
│   ├── config.py
│   ├── Dockerfile
│   └── entrypoint.sh
├── nginx/
│   └── nginx.conf                  # Nginx 리버스 프록시 설정
├── tests/
│   ├── cp_simulator.py             # CP 시뮬레이터 (OCPP 테스트)
│   ├── test_api.py                 # 모바일 API 통합 테스트
│   ├── setup_testdata.py           # 테스트 데이터 생성
│   └── run_tests.sh                # 전체 테스트 실행 스크립트
├── docker-compose.yml              # 운영 Docker Compose
├── docker-compose.dev.yml          # 개발 추가 설정 (tests/ 볼륨 등)
└── .env                            # 환경변수 (git 제외)
```

---

## 3. 로컬 개발 환경 설정

### 사전 요구사항

- Docker Desktop
- Python 3.12 (테스트 스크립트 실행용)
- Git

### 환경 설정

```bash
git clone https://github.com/jeongsooh/chargeplus.git
cd chargeplus
```

`.env` 파일 생성:

```env
SECRET_KEY=your-secret-key-here
DJANGO_SETTINGS_MODULE=chargeplus.settings.development
ALLOWED_HOSTS=*
CSRF_TRUSTED_ORIGINS=http://localhost

POSTGRES_DB=chargeplus
POSTGRES_USER=chargeplus
POSTGRES_PASSWORD=chargeplus
DATABASE_URL=postgresql://chargeplus:chargeplus@db:5432/chargeplus

REDIS_URL=redis://redis:6379/0
CELERY_BROKER_URL=redis://redis:6379/1
CELERY_RESULT_BACKEND=redis://redis:6379/2

GATEWAY_HOST=0.0.0.0
GATEWAY_PORT=9000
OCPP_SECURITY_PROFILE=0
RESPONSE_TIMEOUT=10.0
```

### 실행

```bash
# 전체 스택 시작
docker compose -f docker-compose.yml -f docker-compose.dev.yml up -d

# 테스트 데이터 생성
docker compose exec backend python tests/setup_testdata.py

# 로그 확인
docker compose logs -f backend
docker compose logs -f gateway
```

### 접속

| 항목 | 주소 |
|------|------|
| Django Admin | http://localhost/admin/ (admin / admin1234!) |
| API | http://localhost/api/ |
| OCPP WebSocket | ws://localhost/ocpp/1.6/{station_id} |

---

## 4. GCP 배포

### 인프라 정보

| 항목 | 값 |
|------|-----|
| 프로젝트 ID | chargeplus-490312 |
| VM 이름 | chargeplus-vm |
| 머신 타입 | e2-medium (vCPU 2, RAM 4GB) |
| 리전/존 | asia-northeast3-a (서울) |
| 외부 IP | 34.50.12.65 (정적 예약) |
| OS | Ubuntu 22.04 LTS |

### 방화벽 규칙

| 규칙 이름 | 포트 | 용도 |
|-----------|------|------|
| allow-http | tcp:80 | HTTP |
| allow-https | tcp:443 | HTTPS |
| allow-ocpp-gateway | tcp:9000 | OCPP (직접 접속, 현재 nginx 통해 80/443 사용) |
| default-allow-ssh | tcp:22 | SSH |

### 최초 VM 설정 (참고용)

```bash
# GCP VM 생성
gcloud compute instances create chargeplus-vm \
  --zone=asia-northeast3-a \
  --machine-type=e2-medium \
  --image-family=ubuntu-2204-lts \
  --image-project=ubuntu-os-cloud \
  --boot-disk-size=30GB \
  --tags=http-server,https-server,ocpp-server \
  --project=chargeplus-490312

# VM SSH 접속 후
sudo apt-get update
sudo apt-get install -y docker.io docker-compose-plugin git
sudo systemctl enable docker
sudo usermod -aG docker $USER

# 코드 클론
git clone https://github.com/jeongsooh/chargeplus.git
cd chargeplus

# .env 설정 (운영용)
cat > .env << 'EOF'
SECRET_KEY=<강력한-랜덤-키>
DJANGO_SETTINGS_MODULE=chargeplus.settings.development
ALLOWED_HOSTS=*
CSRF_TRUSTED_ORIGINS=https://chargeplus.kr,https://www.chargeplus.kr

POSTGRES_DB=chargeplus
POSTGRES_USER=chargeplus
POSTGRES_PASSWORD=<강력한-DB-비밀번호>
DATABASE_URL=postgresql://chargeplus:<비밀번호>@db:5432/chargeplus

REDIS_URL=redis://redis:6379/0
CELERY_BROKER_URL=redis://redis:6379/1
CELERY_RESULT_BACKEND=redis://redis:6379/2

GATEWAY_HOST=0.0.0.0
GATEWAY_PORT=9000
OCPP_SECURITY_PROFILE=0
RESPONSE_TIMEOUT=10.0
EOF

# 스택 시작
sudo docker compose up -d --build
```

### 배포 업데이트 절차

```bash
# VM에서
cd ~/chargeplus
git pull
sudo docker compose up -d --build
```

### 테스트 데이터 초기화

```bash
# VM에서 (또는 docker cp 사용)
sudo docker cp tests/setup_testdata.py chargeplus-backend-1:/app/
sudo docker compose exec backend python /app/setup_testdata.py
```

생성되는 테스트 데이터:
- Admin 계정: `admin` / `admin1234!`
- 일반 사용자: `testuser` / `testpass1234`
- 충전소: `CP-TEST-001`
- RFID 토큰: `RFID-TEST-001`
- App 토큰: `APP-2`

---

## 5. 도메인 및 HTTPS 설정

### 도메인

- **도메인:** chargeplus.kr
- **DNS A 레코드:** `@` → `34.50.12.65`, `www` → `34.50.12.65`

### Let's Encrypt 인증서

```bash
# VM에서 인증서 발급 (최초 1회)
sudo docker compose stop nginx
sudo certbot certonly --standalone \
  -d chargeplus.kr -d www.chargeplus.kr \
  --non-interactive --agree-tos \
  --email admin@chargeplus.kr
sudo docker compose up -d nginx
```

- 인증서 경로: `/etc/letsencrypt/live/chargeplus.kr/`
- 만료일: 90일 (certbot이 자동 갱신)
- nginx 컨테이너에 `/etc/letsencrypt` 읽기 전용 마운트

### nginx 설정 요약

- HTTP(80) → HTTPS(443) 자동 리다이렉트
- `/ocpp/` → FastAPI 게이트웨이 (WebSocket 프록시)
- `/api/`, `/admin/`, `/static/` → Django 백엔드
- WebSocket read/send timeout: 3600초

---

## 6. API 명세

### 모바일 앱 API

#### 로그인

```http
POST /api/login
Content-Type: application/json

{
  "user_id": "testuser",
  "password": "testpass1234"
}
```

```json
{
  "success": true,
  "token": "<JWT access token>"
}
```

#### 충전 시작 (QR 코드 스캔)

```http
POST /api/charge/start?qr_code={station_id}
Authorization: Bearer <token>
```

```json
{
  "success": true,
  "session_id": "uuid",
  "station_id": "CP-TEST-001",
  "connector_id": 1
}
```

#### 충전 상태 조회

```http
GET /api/charge/status?session_id={session_id}
Authorization: Bearer <token>
```

```json
{
  "status": "active",
  "kwh": 5.0,
  "duration_seconds": 300,
  "cost": 1350
}
```

상태값: `pending` → `active` → `completed`

#### 충전 종료

```http
POST /api/charge/stop
Authorization: Bearer <token>
Content-Type: application/json

{
  "session_id": "uuid"
}
```

```json
{
  "success": true,
  "kwh": 5.0,
  "cost": 1350,
  "duration_seconds": 300
}
```

### 조회 API

```http
GET /api/v1/stations/        # 충전소 목록
GET /api/v1/transactions/    # 거래 내역
GET /api/v1/cards/           # 카드 목록
Authorization: Bearer <token>
```

### Django Admin

- URL: `https://chargeplus.kr/admin/`
- 계정: `admin` / `admin1234!`

---

## 7. OCPP 1.6 메시지 처리

### 지원 메시지 (CP → CSMS)

| 메시지 | 큐 | 처리 내용 |
|--------|-----|-----------|
| BootNotification | ocpp.q.management | 충전기 등록/업데이트, Accepted/Rejected 응답 |
| Heartbeat | ocpp.q.core | Redis TTL 갱신, 현재 시각 응답 |
| Authorize | ocpp.q.core | RFID/App 토큰 인증 |
| StartTransaction | ocpp.q.core | 거래 생성, transactionId 응답 |
| StopTransaction | ocpp.q.core | 거래 종료, 요금 계산 |
| MeterValues | ocpp.q.telemetry | 미터 값 저장 |
| StatusNotification | ocpp.q.telemetry | 커넥터 상태 업데이트 |
| DataTransfer | ocpp.q.management | 벤더 전용 데이터 처리 |
| FirmwareStatusNotification | ocpp.q.management | 펌웨어 업데이트 상태 |
| DiagnosticsStatusNotification | ocpp.q.management | 진단 업로드 상태 |

### 지원 명령 (CSMS → CP)

| 명령 | 설명 |
|------|------|
| RemoteStartTransaction | 원격 충전 시작 |
| RemoteStopTransaction | 원격 충전 종료 |
| ChangeConfiguration | 설정 변경 |
| GetConfiguration | 설정 조회 |
| Reset | 재시작 (Hard/Soft) |
| UnlockConnector | 커넥터 잠금 해제 |
| GetDiagnostics | 진단 파일 업로드 요청 |
| UpdateFirmware | 펌웨어 업데이트 요청 |
| ChangeAvailability | 가용성 변경 |
| ClearCache | 캐시 초기화 |

### WebSocket 접속

```
wss://chargeplus.kr/ocpp/1.6/{station_id}
Sec-WebSocket-Protocol: ocpp1.6
```

---

## 8. 테스트

### CP 시뮬레이터

```bash
# 로컬에서 실행
cd tests
pip install -r requirements.txt

# 전체 OCPP 테스트 (BootNotification → Heartbeat → Authorize → StartTransaction → MeterValues → StopTransaction)
python cp_simulator.py --url ws://localhost/ocpp/1.6 --station-id CP-TEST-001

# --listen 모드: 부팅 후 대기 (API 테스트와 함께 사용)
python cp_simulator.py --url ws://localhost/ocpp/1.6 --station-id CP-TEST-001 --listen

# GCE 서버 연결
python cp_simulator.py --url wss://chargeplus.kr/ocpp/1.6 --station-id CP-TEST-001
```

### 모바일 API 통합 테스트

```bash
# CP 시뮬레이터가 --listen 모드로 실행 중인 상태에서
python test_api.py \
  --base-url http://localhost \
  --station-id CP-TEST-001 \
  --username testuser \
  --password testpass1234
```

테스트 항목:
- 로그인 (성공 / 실패)
- QR 코드로 충전 시작
- 상태 폴링 (pending → active)
- 충전 종료 (요금 계산 확인)
- 종료 후 404 확인
- 충전소 목록, 거래 내역 조회

### 전체 테스트 한번에 실행

```bash
bash tests/run_tests.sh
```

---

## 9. 운영 관리

### 컨테이너 상태 확인

```bash
# VM SSH 접속 후
cd ~/chargeplus
sudo docker compose ps
sudo docker compose logs -f backend
sudo docker compose logs -f gateway
sudo docker compose logs -f dispatcher
```

### 개별 서비스 재시작

```bash
sudo docker compose restart backend
sudo docker compose restart nginx
sudo docker compose restart gateway
```

### 전체 재시작

```bash
sudo docker compose down
sudo docker compose up -d
```

### DB 접속

```bash
sudo docker compose exec db psql -U chargeplus -d chargeplus
```

### Redis 확인

```bash
sudo docker compose exec redis redis-cli
# 연결된 충전기 확인
KEYS ocpp:connected:*
# 업스트림 큐 확인
LLEN ocpp:upstream
```

### Let's Encrypt 인증서 수동 갱신

```bash
# 자동 갱신이 실패한 경우
sudo docker compose stop nginx
sudo certbot renew
sudo docker compose up -d nginx
```

### GCP gcloud 명령어

```bash
# VM SSH 접속
gcloud compute ssh chargeplus-vm --zone=asia-northeast3-a --project=chargeplus-490312

# VM 시작/중지
gcloud compute instances start chargeplus-vm --zone=asia-northeast3-a
gcloud compute instances stop chargeplus-vm --zone=asia-northeast3-a

# VM 스펙 변경 (중지 후)
gcloud compute instances set-machine-type chargeplus-vm --zone=asia-northeast3-a --machine-type=e2-medium
```

---

## 10. 트러블슈팅 히스토리

구현 및 배포 과정에서 발생한 이슈와 해결책입니다.

### 개발/로컬 이슈

#### 1. django-celery-beat 버전 호환성
- **증상:** `django-celery-beat==2.7.0`이 Django 5.2와 호환되지 않아 마이그레이션 오류
- **해결:** `django-celery-beat==2.8.0`으로 업그레이드

#### 2. entrypoint.sh CRLF 줄바꿈
- **증상:** Linux 컨테이너에서 `exec ./entrypoint.sh: no such file or directory`
- **원인:** Windows에서 작성한 쉘 스크립트의 CRLF 줄바꿈
- **해결:** `sed -i 's/\r//'` 으로 LF 변환

#### 3. Django 마이그레이션 디렉토리 없음
- **증상:** `makemigrations` 실행 시 "No changes detected"
- **원인:** 각 앱에 `migrations/` 폴더와 `__init__.py` 미생성
- **해결:** 9개 앱 전체에 `migrations/__init__.py` 생성

#### 4. Celery 태스크 자동 검색 실패
- **증상:** Celery 워커가 `debug_task`만 인식, OCPP 태스크 미등록
- **원인:** `autodiscover_tasks()` 기본 호출이 `tasks/` 서브패키지를 탐색하지 못함
- **해결:**
  - `tasks/__init__.py`에 `from . import core, telemetry, management, commands` 추가
  - `celery.py`에서 `autodiscover_tasks(lambda: settings.INSTALLED_APPS)` 방식으로 변경

#### 5. select_for_update() 트랜잭션 오류
- **증상:** `DatabaseError: cannot execute SELECT FOR UPDATE outside of a transaction block`
- **원인:** `AuthorizationService.authorize()`에서 atomic block 없이 `select_for_update()` 사용
- **해결:** `select_for_update()` 제거, 일반 `.get()` 사용

#### 6. 로그인 API 403 반환
- **증상:** 로그인 실패 시 401이 아닌 403 응답
- **원인:** `authentication_classes=[]` 설정에서 `AuthenticationFailed` 예외가 403으로 변환됨
- **해결:** `raise AuthenticationFailed()` → `return Response({...}, status=HTTP_401_UNAUTHORIZED)`

#### 7. 테스트 비밀번호의 `!` 문자
- **증상:** MINGW64 쉘에서 `testpass123!`이 `testpass123\!`로 이스케이프됨
- **해결:** 비밀번호를 `testpass1234`로 변경

#### 8. CP 시뮬레이터 조기 종료
- **증상:** 시뮬레이터가 RFID 테스트 완료 후 종료되어 API 테스트 불가
- **해결:** `--listen` 모드 추가 — BootNotification 후 대기하며 원격 명령 수신

#### 9. 테스트 폴더 컨테이너 미탑재
- **증상:** `python tests/setup_testdata.py: No such file or directory`
- **해결:** `docker-compose.dev.yml`에 `./tests:/app/tests` 볼륨 마운트 추가

#### 10. Redis 연결 키 TTL 만료
- **증상:** `--listen` 모드에서 3분 후 충전기가 오프라인으로 표시됨
- **원인:** TTL 180초, Heartbeat 없는 테스트 환경
- **해결:** gateway와 Celery 태스크 모두 TTL을 3600초로 증가

### 배포 이슈

#### 11. `.gitignore` 패턴으로 핵심 앱 제외
- **증상:** GCE VM에서 `ModuleNotFoundError: No module named 'apps.ocpp16'`
- **원인:** `.gitignore`의 `ocpp16/` 패턴이 루트뿐 아니라 `backend/apps/ocpp16/`도 제외
- **해결:** `ocpp16/` → `/ocpp16/` (루트 앵커 추가)

#### 12. e2-small VM OOM (메모리 부족)
- **증상:** 컨테이너가 반복 재시작 (exit code 137 = SIGKILL)
- **원인:** e2-small RAM 2GB로 10개 이상 컨테이너 실행 불가
- **해결:** e2-small → e2-medium (RAM 4GB) 업그레이드

#### 13. 포트 80 방화벽 미설정
- **증상:** nginx가 포트 80에 바인딩됐지만 외부에서 접근 불가
- **해결:** GCP 방화벽 규칙 `allow-http` (tcp:80) 추가

#### 14. PostgreSQL 비밀번호 불일치
- **증상:** 재배포 후 백엔드에서 `FATAL: password authentication failed for user "chargeplus"`
- **원인:** postgres_data 볼륨에 저장된 이전 비밀번호와 .env의 비밀번호 불일치
- **해결:** `ALTER USER chargeplus WITH PASSWORD '새비밀번호';` 실행

#### 15. Admin 정적 파일 미서빙
- **증상:** Django Admin 페이지 CSS/JS 로드 실패, 화면 깨짐
- **원인:** `DEBUG=False` 환경에서 Django가 정적 파일을 자동으로 서빙하지 않음
- **해결:** `whitenoise` 미들웨어 추가 + `collectstatic` 실행

#### 16. CSRF 검증 실패 (Admin 로그인 불가)
- **증상:** `Origin checking failed - https://chargeplus.kr does not match any trusted origins`
- **원인 1:** Django 4.0+에서 HTTPS 사용 시 `CSRF_TRUSTED_ORIGINS` 필수
- **원인 2:** `docker-compose.yml`에 해당 환경변수가 backend 서비스에 미전달
- **해결:**
  - `settings/base.py`에 `CSRF_TRUSTED_ORIGINS` 환경변수 읽기 추가
  - `docker-compose.yml` backend 서비스 환경변수에 `CSRF_TRUSTED_ORIGINS` 추가
  - VM `.env`에 `CSRF_TRUSTED_ORIGINS=https://chargeplus.kr,https://www.chargeplus.kr` 설정

---

## 관련 링크

- **GitHub:** https://github.com/jeongsooh/chargeplus
- **운영 서버:** https://chargeplus.kr
- **Django Admin:** https://chargeplus.kr/admin/
- **OCPP 1.6 스펙:** https://www.openchargealliance.org/protocols/ocpp-16/
