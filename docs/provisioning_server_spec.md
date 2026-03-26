# 충전기 프로비저닝 서버 API 요청 명세서

**작성일:** 2026-03-26
**요청자:** 클라이언트 시뮬레이터 개발팀
**수신자:** chargeplus.kr 백엔드 서버 개발팀
**관련 URL:** `https://chargeplus.kr/config`

---

## 1. 배경 및 목적

OCPP 1.6J 충전기 클라이언트 시뮬레이터는 가상 충전기 최초 기동 시 **시리얼 번호(serial_number)** 를 이용하여 프로비저닝 서버에 접속, 해당 충전기의 **cp_id** 와 **CSMS WebSocket 접속 URL** 을 발급받습니다.

이 API가 없으면 가상 충전기가 CSMS에 접속할 수 없으므로, 아래 명세에 따른 엔드포인트 구현을 요청합니다.

---

## 2. 요청 API 명세

### 2.1 충전기 프로비저닝 (신규 할당)

| 항목 | 내용 |
|------|------|
| **Method** | `POST` |
| **URL** | `https://chargeplus.kr/config` |
| **Content-Type** | `application/json` |
| **인증** | 없음 (또는 협의 후 결정) |

#### Request Body

```json
{
  "serialNumber": "SIM-0001"
}
```

| 필드 | 타입 | 필수 | 설명 |
|------|------|------|------|
| `serialNumber` | string | ✅ | 충전기 고유 시리얼 번호 (최대 50자) |

#### Response Body (성공 — HTTP 200)

```json
{
  "cpId": "CP-SIM-0001",
  "wsUrl": "wss://chargeplus.kr/ws/CP-SIM-0001"
}
```

| 필드 | 타입 | 필수 | 설명 |
|------|------|------|------|
| `cpId` | string | ✅ | 서버가 할당한 충전기 ID (OCPP의 chargePointIdentity) |
| `wsUrl` | string | ✅ | CSMS WebSocket 접속 URL (`wss://` 또는 `ws://`) |

> **참고:** 응답 필드명은 아래 대안 표기도 허용합니다 (클라이언트가 모두 인식합니다).
> - `cpId` 또는 `cp_id` 또는 `chargePointId`
> - `wsUrl` 또는 `csms_url` 또는 `websocketUrl`

#### Response Body (실패 케이스)

**미등록 시리얼 (HTTP 404)**
```json
{
  "error": "NOT_FOUND",
  "message": "Serial number not registered: SIM-9999"
}
```

**이미 할당됨 (HTTP 200 또는 409)**
동일 시리얼로 재요청 시 기존에 할당된 `cpId` / `wsUrl` 을 그대로 반환해 주세요.
(멱등성 보장 — 재부팅 시 동일 결과를 받아야 합니다.)

```json
{
  "cpId": "CP-SIM-0001",
  "wsUrl": "wss://chargeplus.kr/ws/CP-SIM-0001",
  "alreadyProvisioned": true
}
```

**서버 오류 (HTTP 500)**
```json
{
  "error": "INTERNAL_ERROR",
  "message": "Database error"
}
```

---

## 3. 동작 시나리오

```
가상 충전기 최초 기동
        │
        ▼
POST https://chargeplus.kr/config
{ "serialNumber": "SIM-0001" }
        │
        ▼ 응답
{ "cpId": "CP-SIM-0001",
  "wsUrl": "wss://chargeplus.kr/ws/CP-SIM-0001" }
        │
        ▼
cp_id, wsUrl 을 DB(가상 EEPROM)에 저장
        │
        ▼
WebSocket 연결: wss://chargeplus.kr/ws/CP-SIM-0001
(OCPP Subprotocol: "ocpp1.6")
        │
        ▼
BootNotification 전송 → 정상 운영
```

### 재기동 시 (이미 프로비저닝된 경우)
- 가상 충전기는 DB에서 `cp_id`, `wsUrl`을 읽어 **프로비저닝 서버 호출 없이** 직접 CSMS 접속
- 단, DB에 정보가 없는 경우(초기화된 경우) 다시 프로비저닝 서버에 요청

---

## 4. 보안 고려사항

### 현재 단계 (Phase 1)
- HTTPS 사용 (TLS 1.2 이상)
- 별도 인증 없이 시리얼 번호만으로 조회

### 향후 단계 (Phase 2 — 선택)
서버 측에서 인증이 필요하다면 아래 방식을 협의합니다:

| 방식 | 설명 |
|------|------|
| API Key | 요청 헤더 `X-API-Key: {key}` |
| Client Cert | mTLS (TLS 클라이언트 인증서) |
| JWT | `Authorization: Bearer {token}` |

---

## 5. CSMS WebSocket 연결 요구사항

프로비저닝 서버에서 반환하는 `wsUrl`에 대한 요구사항입니다.

| 항목 | 요구사항 |
|------|---------|
| **URL 형식** | `wss://{host}/ws/{cpId}` |
| **SubProtocol** | `ocpp1.6` (WebSocket Upgrade 헤더에 포함) |
| **인증** | HTTP Basic Auth: `Authorization: Basic base64({cpId}:{authorizationKey})` |
| **TLS** | TLS 1.2 이상 (Security Profile 1 기준) |
| **Ping/Pong** | WebSocket ping-pong 지원 필요 (30초 간격) |

> OCPP 1.6J 표준에 따라 WebSocket 연결 시 `Sec-WebSocket-Protocol: ocpp1.6` 헤더가 포함됩니다.

---

## 6. 사전 등록 데이터 요청

테스트를 위해 아래 시리얼 번호들을 사전 등록해 주세요.

| 시리얼 번호 | 요청 cp_id (권고) | 비고 |
|------------|------------------|------|
| `SIM-0001` ~ `SIM-0100` | `CP-SIM-0001` ~ `CP-SIM-0100` | 시뮬레이터 부하 테스트용 |

> 실제 할당 cp_id는 서버 정책에 따라 자유롭게 정의하셔도 됩니다.

---

## 7. 테스트 검증 방법

서버 구현 후 아래 curl 명령으로 동작을 검증합니다:

```bash
# 정상 케이스
curl -s -X POST https://chargeplus.kr/config \
  -H "Content-Type: application/json" \
  -d '{"serialNumber": "SIM-0001"}' | jq .

# 예상 응답
{
  "cpId": "CP-SIM-0001",
  "wsUrl": "wss://chargeplus.kr/ws/CP-SIM-0001"
}

# 미등록 시리얼 케이스
curl -s -X POST https://chargeplus.kr/config \
  -H "Content-Type: application/json" \
  -d '{"serialNumber": "UNKNOWN-9999"}' | jq .
```

---

## 8. 문의사항

| 항목 | 내용 |
|------|------|
| 프로젝트 | OCPP 1.6 Virtual Charger Client Simulator |
| 소스 코드 | `workspaces/backend/app/services/provisioning.py` |
| 설정 파일 | `PROVISIONING_URL` 환경변수 (현재: `https://chargeplus.kr/config`) |
