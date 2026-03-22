# MB Paygate 결제 통합 계획서

## 개요

MB Paygate(베트남 MB Bank PG사)를 ChargePlus CSMS의 `apps/payment/` 앱으로 통합한다.
현재 `D:/projects/Payment/MBBank/server/`에 독립 Django 프로젝트로 구현된 내용을 참조하되,
OCPP 충전기 제어(RemoteStart/Stop) 연동 및 MAC 서명 버그 수정을 포함하여 완전 통합한다.

### 통합 후 결제 플로우

```
앱 → POST /api/payment/create  → PaymentTransaction 생성(PENDING) → MB create-order 호출
                                                                          ↓ QR URL 반환
앱 → 사용자가 QR/웹뷰에서 결제 완료
                                                                          ↓
MB 서버 → POST /api/payment/ipn  → MAC 검증 → PAID 저장
                                              → Celery task → GatewayClient.RemoteStartTransaction
앱 → GET /api/payment/status    → CHARGING 감지 → 충전 화면 전환

(충전 중) → OCPP MeterValues → AppSession.kwh_current 갱신

앱 → POST /api/charge/stop → RemoteStopTransaction
                                  ↓ StopTransaction 수신
                              PaymentService.process_stop() → actual_amount 계산
                                                            → MB refund API 호출
                                                            → PaymentTransaction REFUNDED
```

---

## 참조 파일

| 파일 | 용도 |
|------|------|
| `Payment/MBBank/server/payment/views.py` | API 뼈대, Mock UI 로직 |
| `Payment/MBBank/server/payment/models.py` | PaymentTransaction 기초 모델 |
| `Payment/MBBank/doc/references/mynetwork.cpp` | 실제 MAC 서명 방식, API URL, 인증정보 |
| `Payment/MBBank/doc/MB_Paygate_Server_Plan.md` | 기능 명세 |
| `Payment/MBBank/server/test_e2e.py` | E2E 테스트 참조 |

### MB Paygate 인증 정보 (sandbox)

| 항목 | 값 |
|------|-----|
| `hashkey` (secret) | `6ca6af4578753e1afae2eb864f8aa288` |
| `access_code` | `DNHXPHRNMZ` |
| `merchant_id` | `114743` |
| `invoice_taxcode` | `0101243150-572` |

### MB Paygate API 엔드포인트 (sandbox)

| 기능 | URL |
|------|-----|
| 주문 생성 | `https://BE.mbbank.com.vn/pg-paygate/ite-pg-paygate/paygate/v2/create-order` |
| 환불 | `https://BE.mbbank.com.vn/pg-paygate/ite-pg-paygate/paygate/refund/single` |
| 거래 조회 | `https://BE.mbbank.com.vn/pg-paygate/ite-pg-paygate/paygate/detail` |

---

## MAC 서명 방식 (C++ 원본 기준)

기존 Payment 서버의 MAC 구현은 실제 C++ 로직과 다르다. 올바른 방식으로 구현한다.

### C++ 원본 로직 (mynetwork.cpp)

```
1. JSON 객체를 Compact 직렬화
2. `":` → `=` 치환
3. `,` → `&` 치환
4. 공백, `{`, `}`, `"` 제거
5. 결과 앞에 hashkey prefix 추가
6. MD5 해시 → 대문자 hex
```

### create-order MAC 대상 필드 (JSON 직렬화 순서)

```
amount, currency, customerID, customerName, access_code, merchant_id,
order_info, order_reference, return_url, cancel_url, pay_type,
ip_address, payment_method
```

특이사항: `order_info`에 공백이 포함된 경우 C++ 코드에서 `MATTEC` → `MA TT EC` 복원 처리가
있으므로, Python에서는 처음부터 공백 있는 원문을 그대로 사용한다.

### refund MAC 대상 필드

```
txn_amount, desc, access_code, merchant_id, transaction_reference_id, trans_date
```

### inquiry MAC 대상 필드

```
merchant_id, order_reference, pg_transaction_reference, pay_date
```

---

## Phase 1: `apps/payment/` 앱 생성 및 모델

### 1.1 앱 생성 및 등록

- `backend/apps/payment/` 디렉터리 생성 (Django app 구조)
- `chargeplus/settings/base.py`의 `INSTALLED_APPS`에 `'apps.payment'` 추가
- `chargeplus/urls.py`에 `path('api/payment/', include('apps.payment.urls'))` 추가

### 1.2 PaymentTransaction 모델

```python
# apps/payment/models.py
class PaymentTransaction(models.Model):
    class Status(TextChoices):
        PENDING   = 'PENDING'    # 주문 생성, 결제 대기
        PAID      = 'PAID'       # IPN 수신 완료, 충전 명령 전 단계
        CHARGING  = 'CHARGING'   # RemoteStart 성공, 충전 중
        COMPLETED = 'COMPLETED'  # StopTransaction 처리 완료
        REFUNDED  = 'REFUNDED'   # 차액 환불 완료
        FAILED    = 'FAILED'     # 결제 실패 또는 에러
        CANCELED  = 'CANCELED'   # 사용자 취소

    order_reference       # CharField unique — "CP{timestamp}{random}" prefix
    app_session           # OneToOneField → AppSession (null=True, 결제 후 연결)
    user                  # ForeignKey → users.User
    station_id            # CharField — 충전기 식별자
    prepaid_amount        # DecimalField — 선결제액 (VND)
    actual_amount         # DecimalField null — 실충전액 (StopTransaction 후 계산)
    refund_amount         # DecimalField null — 환불액
    status                # CharField choices=Status
    mb_transaction_id     # CharField null — IPN으로 수신한 MB 거래번호
    trans_date            # CharField null — 결제일 "ddMMyyyy" (환불 API 필요)
    payment_url           # URLField null — QR URL 또는 결제 웹뷰 URL
    created_at            # DateTimeField auto_now_add
    updated_at            # DateTimeField auto_now
```

### 1.3 환경 변수 추가

`docker-compose.yml` 및 `docker-compose.dev.yml`의 backend 환경변수에 추가:
```
MB_SECRET_KEY=6ca6af4578753e1afae2eb864f8aa288
MB_ACCESS_CODE=DNHXPHRNMZ
MB_MERCHANT_ID=114743
MB_SANDBOX=true            # true: sandbox URL 사용, false: 운영 URL
MB_IPN_URL=https://chargeplus.kr/api/payment/ipn/
MB_RETURN_URL=https://chargeplus.kr/api/payment/return/
MB_CANCEL_URL=https://chargeplus.kr/api/payment/cancel/
MB_PREPAID_AMOUNT=100000   # 기본 선결제 금액 (VND)
```

`chargeplus/settings/base.py`에서 로드:
```python
MB_SECRET_KEY   = os.environ.get('MB_SECRET_KEY', '')
MB_ACCESS_CODE  = os.environ.get('MB_ACCESS_CODE', '')
MB_MERCHANT_ID  = os.environ.get('MB_MERCHANT_ID', '')
MB_SANDBOX      = os.environ.get('MB_SANDBOX', 'true') == 'true'
```

### 1.4 마이그레이션 생성

```bash
python manage.py makemigrations payment
python manage.py migrate
```

---

## Phase 2: MB Paygate 서비스 레이어

### 2.1 MAC 서명 유틸리티 (`apps/payment/services/mac.py`)

```python
def generate_mac(fields: dict, secret_key: str) -> str:
    """
    C++ mynetwork.cpp의 MAC 생성 로직을 Python으로 포팅.
    1. JSON compact 직렬화
    2. '":' → '=' 치환, ',' → '&' 치환
    3. 공백, '{', '}', '"' 제거
    4. secret_key prefix 추가
    5. MD5 → 대문자 hex
    """
```

단위 테스트: C++ 코드로 생성한 MAC 값과 동일한지 검증.

### 2.2 MB Paygate API 클라이언트 (`apps/payment/services/mb_client.py`)

```python
class MBPaygateClient:
    def create_order(self, order_reference, amount, station_id) -> dict:
        """create-order API 호출 → {qr_url, payment_url, error_code}"""

    def refund(self, txn_amount, transaction_reference_id, trans_date) -> dict:
        """refund API 호출 → {error_code}"""

    def inquiry(self, order_reference, pay_date) -> dict:
        """거래 조회 API → {error_code, status}"""
```

각 메서드에서 MAC 자동 생성 및 requests.post 호출.
MB_SANDBOX=true이면 sandbox URL 사용.

### 2.3 결제 서비스 (`apps/payment/services/payment_service.py`)

```python
class PaymentService:
    @classmethod
    def create_payment(cls, user, station_id, amount=None) -> PaymentTransaction:
        """PaymentTransaction 생성 + MB create-order 호출"""

    @classmethod
    def handle_ipn(cls, data: dict) -> bool:
        """IPN 처리: MAC 검증 → PAID 저장 → Celery task 트리거"""

    @classmethod
    def process_stop(cls, app_session) -> None:
        """충전 종료 후 actual_amount 계산 → MB refund 호출"""

    @classmethod
    def query_status(cls, order_reference) -> str:
        """PENDING 상태 시 MB inquiry API 재조회하여 실제 결제 여부 확인"""
```

---

## Phase 3: API 엔드포인트

### 3.1 URL 설계

```
POST   /api/payment/create/        결제 세션 생성 (JWT 인증)
POST   /api/payment/ipn/           MB IPN 웹훅 (인증 없음, CSRF 제외)
GET    /api/payment/status/<ref>/  결제 상태 조회 (JWT 인증)
POST   /api/payment/refund/        환불 처리 (내부 또는 JWT 인증)
GET    /api/payment/return/        결제 완료 리턴 URL (redirect)
GET    /api/payment/cancel/        결제 취소 리턴 URL (redirect)
GET    /api/payment/mock/          Mock MB Paygate UI (sandbox only)
POST   /api/payment/mock/submit/   Mock 결제 제출 (sandbox only)
```

### 3.2 `POST /api/payment/create/`

**Request:**
```json
{ "station_id": "CP001", "amount": 100000 }
```

**Logic:**
1. `station_id`로 ChargingStation 조회 (없으면 404)
2. GatewayClient.is_station_connected() 확인 (오프라인이면 503)
3. 해당 사용자의 PENDING/PAID/CHARGING 상태 결제가 있으면 409
4. `PaymentService.create_payment()` 호출
5. MB 응답 성공: `payment_url`, `order_reference` 반환
6. MB 응답 실패 또는 sandbox 연결 불가: Mock URL 반환

**Response:**
```json
{
  "order_reference": "CP17432...",
  "payment_url": "https://...",
  "is_mock": false
}
```

### 3.3 `POST /api/payment/ipn/`

**Logic:**
1. `@csrf_exempt` 적용
2. MAC 재계산으로 위변조 검증 (불일치 시 errorCode 99 반환)
3. `error_code == "00"` 이고 상태가 `PENDING`인 경우만 처리 (멱등성)
4. `PaymentTransaction.status = PAID`, `mb_transaction_id` 저장
5. Celery task `trigger_remote_start` 비동기 실행
6. MB에 `{"errorCode": "00"}` 응답

**Celery task `trigger_remote_start`:**
```python
@shared_task(queue='ocpp.q.commands')
def trigger_remote_start(order_reference):
    # PaymentTransaction 조회
    # AppSession 생성 (status=PENDING)
    # GatewayClient.send_command("RemoteStartTransaction", ...)
    # 성공: PaymentTransaction.status = CHARGING, app_session 연결
    # 실패: PaymentTransaction.status = FAILED
```

### 3.4 `GET /api/payment/status/<order_ref>/`

**Logic:**
1. PaymentTransaction 조회 (없으면 404)
2. 소유자 검증
3. DB status가 `PENDING`이면 → MB inquiry API 재조회 후 보정
4. 현재 status 반환

**Response:**
```json
{ "status": "CHARGING", "order_reference": "CP..." }
```

### 3.5 `POST /api/payment/refund/`

충전 종료 시 내부적으로 호출 (외부 API 아님).
`PaymentService.process_stop()`에서 직접 호출하는 방식으로 구현.
- `actual_amount` = 충전 kWh × 단가 (PricingService 연동)
- `refund_amount` = prepaid_amount - actual_amount
- refund_amount > 0 이면 MB refund API 호출
- status = REFUNDED

---

## Phase 4: ChargeStartView 수정

현재 `POST /api/charge/start`는 즉시 RemoteStart를 보내는 구조.
결제 연동 후에는 결제가 선행되어야 하므로 플로우 변경.

### 변경 전 (현재)
```
앱 → /api/charge/start → RemoteStartTransaction → session_id 반환
```

### 변경 후
```
앱 → /api/payment/create → order_reference + QR URL 반환
     (사용자 결제)
MB → /api/payment/ipn → trigger_remote_start Celery task
     앱 → /api/payment/status 폴링 → CHARGING 감지
     앱 → /api/charge/status 폴링 (session_id 사용)
```

**구체적 수정 내용:**

`ChargeStartView.post()`에서 결제 필요 여부를 확인하는 옵션 추가:
- `require_payment=true` (기본값): 결제 없으면 차단, `/api/payment/create` 안내
- `require_payment=false`: RFID 방식 등 결제 없는 충전 (기존 동작 유지)

또는 `ChargeStartView`는 RFID용으로 유지하고, 앱 결제 충전은 payment 앱이 전담.

→ **결정: 앱 결제 충전은 payment 앱이 전담한다. ChargeStartView는 RFID 방식 그대로 유지.**

---

## Phase 5: StopTransaction 핸들러 연동

`apps/ocpp16/tasks/core.py`의 `handle_stop_transaction` 태스크 끝부분에 추가:

```python
# Payment 연동: 충전 종료 후 환불 처리
if app_session:
    from apps.payment.services.payment_service import PaymentService
    PaymentService.process_stop(app_session)
```

`process_stop()` 내부:
1. `app_session.payment_transaction` 조회 (없으면 스킵)
2. status가 CHARGING 인 경우만 처리
3. actual_amount = `PricingService`로 계산
4. MB refund API 호출
5. PaymentTransaction status = REFUNDED (또는 COMPLETED if no refund)

---

## Phase 6: Admin 및 테스트

### 6.1 Django Admin 등록 (`apps/payment/admin.py`)

```
PaymentTransactionAdmin:
  list_display: order_reference, user, station_id, prepaid_amount, actual_amount,
                refund_amount, status, mb_transaction_id, created_at
  list_filter: status, created_at
  search_fields: order_reference, mb_transaction_id, user__username
  readonly_fields: order_reference, mb_transaction_id, trans_date
  actions: [수동 환불 처리, 상태 재조회]
```

### 6.2 테스트

**단위 테스트 (`apps/payment/tests/test_mac.py`)**
- MAC 생성 로직이 C++ 원본과 동일한 값을 생성하는지 검증
- create-order, refund, inquiry 각각 테스트

**통합 테스트 (`tests/test_payment_flow.py`)**
Mock MB 서버를 활용한 전체 플로우 검증:
1. `POST /api/payment/create/` → Mock URL 수신
2. Mock MB Paygate UI → 결제 클릭
3. `POST /api/payment/mock/submit/` → IPN 내부 발송
4. `GET /api/payment/status/` 폴링 → CHARGING 확인
5. CP 시뮬레이터로 MeterValues 전송
6. `POST /api/charge/stop` → StopTransaction 처리
7. `GET /api/payment/status/` → REFUNDED 확인

---

## 파일 목록 (생성/수정 대상)

### 신규 생성

```
backend/apps/payment/
├── __init__.py
├── apps.py
├── admin.py
├── models.py
├── urls.py
├── views.py
├── migrations/
│   └── __init__.py
├── services/
│   ├── __init__.py
│   ├── mac.py              MAC 서명 유틸리티
│   ├── mb_client.py        MB Paygate API 클라이언트
│   └── payment_service.py  결제 비즈니스 로직
└── tasks.py                Celery tasks (trigger_remote_start 등)
tests/
└── test_payment_flow.py    E2E 통합 테스트
```

### 수정 파일

| 파일 | 수정 내용 |
|------|----------|
| `chargeplus/settings/base.py` | MB_ 환경변수 추가, INSTALLED_APPS에 `apps.payment` 추가 |
| `chargeplus/urls.py` | `path('api/payment/', include('apps.payment.urls'))` 추가 |
| `docker-compose.yml` | backend 환경변수에 MB_ 항목 추가 |
| `docker-compose.dev.yml` | 동일 |
| `apps/ocpp16/tasks/core.py` | `handle_stop_transaction` 끝에 `PaymentService.process_stop()` 호출 추가 |
| `backend/requirements.txt` | `requests` (이미 있으면 생략) |

---

## 구현 순서 요약

```
Phase 1  앱 생성 + PaymentTransaction 모델 + 환경변수 + 마이그레이션
    ↓
Phase 2  MAC 서명 유틸리티 (단위 테스트 병행)
    ↓       MBPaygateClient 서비스
    ↓       PaymentService (create, handle_ipn, process_stop, query_status)
    ↓
Phase 3  API 엔드포인트 + Mock UI 이식
    ↓
Phase 4  Celery task (trigger_remote_start)
    ↓
Phase 5  handle_stop_transaction 연동
    ↓
Phase 6  Admin 등록 + E2E 테스트
```

---

## 주의사항

1. **MAC 서명 정확성이 1순위** — 필드 순서 또는 문자 하나 차이로 MB 서버에서 거절됨. 단위 테스트 먼저.
2. **IPN 멱등성 필수** — `status == PENDING`인 경우만 처리. 중복 IPN으로 이중 충전 방지.
3. **Celery 큐** — `trigger_remote_start`는 `ocpp.q.commands` 큐 사용.
4. **환경변수 비밀 관리** — `MB_SECRET_KEY`는 GCP VM의 docker-compose.yml 환경변수에만 저장. `.gitignore`에서 제외 확인.
5. **sandbox IPN_URL** — 샌드박스 테스트 시 MB 서버가 우리 IPN URL에 접근할 수 있어야 함. GCP 배포 후 테스트하거나 ngrok 사용.
6. **order_reference prefix** — `"CP"` prefix 사용 (C++ 코드의 `"6VQR"`은 다른 채널용).
