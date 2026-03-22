# ChargePlus 프로젝트 컨텍스트

## 프로젝트 개요

전기차 충전 서비스 CSMS (Charge Station Management System).
OCPP 1.6 기반 충전기 관제 서버 + 모바일 앱 충전 API + 사용자 포털.

**GitHub**: https://github.com/jeongsooh/chargeplus (master)
**Live**: https://chargeplus.kr (GCP, chargeplus-vm, asia-northeast3-a)

## 아키텍처

```
[충전기] --WebSocket(OCPP 1.6)--> [Gateway: FastAPI] --Redis Pub/Sub--> [Backend: Django]
[모바일 앱] --REST/JWT-----------> [Backend: Django] --Celery---------> [Worker]
[웹 포털]  --HTTP Session--------> [Backend: Django]
```

| 서비스 | 위치 | 역할 |
|--------|------|------|
| `gateway/` | FastAPI + uvicorn | OCPP WebSocket 엔드포인트, 메시지 라우팅 |
| `backend/` | Django 5.2 + DRF | REST API, DB, Celery tasks, Admin, 포털 |
| `worker-*` | Celery | OCPP 메시지 처리 (core/telemetry/management/commands 큐) |
| `redis` | Redis | 메시지 브로커, 연결 레지스트리 |
| `db` | PostgreSQL | 주 데이터베이스 |
| `nginx` | Nginx | 리버스 프록시, SSL 종단 |

## 주요 Django 앱 목록 (`backend/apps/`)

| 앱 | 역할 |
|----|------|
| `config` | CsmsVariable (시스템 설정값) |
| `users` | User (role: cs/partner/customer), PartnerProfile, PaymentCard |
| `stations` | ChargingStation, EVSE, Connector, ChargingSite |
| `authorization` | IdToken, AuthorizationRecord |
| `transactions` | Transaction (충전 거래) |
| `mobile_api` | AppSession, REST API (login/charge start·status·stop) |
| `ocpp16` | OCPP 메시지 핸들러, GatewayClient |
| `reservations` | Reservation |
| `smart_charging` | ChargingProfile |
| `portal` | 웹 포털 (cs/partner/customer 역할별 뷰) |
| `payment` | **[미구현]** MB Paygate 결제 연동 (다음 작업 대상) |

## 다음 작업: MB Paygate 결제 통합

**계획서 위치**: `docs/payment_integration_plan.md`

"payment_integration_plan.md를 시작해 달라" 는 요청을 받으면 계획서를 읽고 Phase 1부터 구현을 시작한다.

### 작업 범위 요약

- 신규: `backend/apps/payment/` 앱 전체 (모델, 서비스, API, Celery task, Admin, 테스트)
- 수정: `settings/base.py`, `chargeplus/urls.py`, `docker-compose.yml`, `docker-compose.dev.yml`, `apps/ocpp16/tasks/core.py`

### 핵심 주의사항 (작업 시작 전 반드시 확인)

1. **MAC 서명**: `Payment/MBBank/doc/references/mynetwork.cpp` 의 C++ 로직을 정확히 Python으로 포팅한다.
   기존 `Payment/MBBank/server/payment/views.py`의 `generate_mb_mac()`은 잘못 구현되어 있으므로 사용하지 않는다.

2. **MB Paygate 인증 정보** (sandbox):
   - `hashkey` = `6ca6af4578753e1afae2eb864f8aa288`
   - `access_code` = `DNHXPHRNMZ`
   - `merchant_id` = `114743`
   - 이 값들은 환경변수(`MB_SECRET_KEY`, `MB_ACCESS_CODE`, `MB_MERCHANT_ID`)로 관리한다.
   - 코드에 하드코딩하지 않는다.

3. **IPN 멱등성**: `status == PENDING`인 경우에만 처리. 동일 IPN 중복 수신 방어 필수.

4. **ChargeStartView 유지**: `apps/mobile_api/views.py`의 ChargeStartView는 RFID 방식 그대로 유지.
   앱 결제 충전은 payment 앱이 전담.

5. **Celery 큐**: `trigger_remote_start` task는 `ocpp.q.commands` 큐 사용.
   `docker-compose.yml`에 `worker-commands` 서비스가 있는지 확인 후 없으면 추가.

### MB Paygate API 엔드포인트 (sandbox)

```
create-order : https://BE.mbbank.com.vn/pg-paygate/ite-pg-paygate/paygate/v2/create-order
refund       : https://BE.mbbank.com.vn/pg-paygate/ite-pg-paygate/paygate/refund/single
inquiry      : https://BE.mbbank.com.vn/pg-paygate/ite-pg-paygate/paygate/detail
```

### 참조 파일

```
Payment/MBBank/doc/references/mynetwork.cpp     ← MAC 서명 로직 원본 (C++)
Payment/MBBank/doc/MB_Paygate_Server_Plan.md    ← 기능 명세
Payment/MBBank/server/payment/views.py          ← API 뼈대, Mock UI (참조용)
Payment/MBBank/server/test_e2e.py               ← E2E 테스트 패턴 참조
```

## 개발 환경

### 로컬 실행

```bash
# 개발 서버 (로컬)
cd D:/projects/ChargePlus
docker compose -f docker-compose.yml -f docker-compose.dev.yml up -d

# 마이그레이션
docker compose exec backend python manage.py migrate

# 새 앱 마이그레이션 생성
docker compose exec backend python manage.py makemigrations <app_name>
```

### GCP 배포

```bash
# GCP VM 접속
gcloud compute ssh chargeplus-vm --project chargeplus-490312 --zone asia-northeast3-a

# 서버에서
cd ~/chargeplus
git pull origin master
sudo docker compose pull
sudo docker compose up -d --build
sudo docker compose exec backend python manage.py migrate
```

### 환경변수 구조 (docker-compose.yml)

backend, worker-* 서비스 모두 동일한 환경변수 블록을 공유한다.
새 환경변수 추가 시 backend + 모든 worker 서비스에 동시 추가 필요.

## 코드 규칙

- Django 앱은 모두 `backend/apps/<name>/` 경로에 위치
- Celery task는 각 앱의 `tasks.py` 또는 `tasks/` 디렉터리에 위치
- 서비스 레이어는 `services/` 서브디렉터리로 분리
- API는 DRF `APIView` 기반 (ViewSet 사용 안 함)
- 인증: JWT (`djangorestframework-simplejwt`)
- 설정값은 `CsmsVariable.get(key, default=...)` 으로 조회 (DB 기반, 캐시 TTL 60초)
