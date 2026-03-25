# GCP 배포 가이드 (상세)

ChargePlus OCPP 1.6 CSMS를 Google Cloud Platform(GCE VM)에 배포하는 전체 과정을 명령어 단위로 기록합니다.

---

## 목차

1. [사전 준비 (gcloud CLI 설정)](#1-사전-준비-gcloud-cli-설정)
2. [GCE VM 생성](#2-gce-vm-생성)
3. [방화벽 규칙 설정](#3-방화벽-규칙-설정)
4. [VM 초기 설정](#4-vm-초기-설정)
5. [애플리케이션 배포](#5-애플리케이션-배포)
6. [테스트 데이터 설정](#6-테스트-데이터-설정)
7. [도메인 연결](#7-도메인-연결)
8. [HTTPS 설정 (Let's Encrypt)](#8-https-설정-lets-encrypt)
9. [IP 고정](#9-ip-고정)
10. [배포 업데이트 방법](#10-배포-업데이트-방법)
11. [VM 스펙 변경](#11-vm-스펙-변경)

---

## 1. 사전 준비 (gcloud CLI 설정)

### gcloud CLI 설치

Windows: https://cloud.google.com/sdk/docs/install 에서 설치

설치 경로 (기본값):
```
C:\Users\{사용자명}\AppData\Local\Google\Cloud SDK\google-cloud-sdk\bin\gcloud
```

### 인증 및 프로젝트 설정

```bash
# Google 계정 인증 (브라우저 열림)
gcloud auth login

# 프로젝트 설정
gcloud config set project chargeplus-490312

# 설정 확인
gcloud config list
# 출력 예시:
# [core]
# account = gresystem2023@gmail.com
# project = chargeplus-490312

# 필요한 GCP API 활성화
gcloud services enable compute.googleapis.com
gcloud services enable dns.googleapis.com
```

---

## 2. GCE VM 생성

```bash
# VM 인스턴스 생성
gcloud compute instances create chargeplus-vm \
  --zone=asia-northeast3-a \
  --machine-type=e2-medium \
  --image-family=ubuntu-2204-lts \
  --image-project=ubuntu-os-cloud \
  --boot-disk-size=30GB \
  --boot-disk-type=pd-standard \
  --tags=http-server,https-server,ocpp-server \
  --project=chargeplus-490312
```

> **참고:** 처음에 e2-small로 생성했으나 RAM 2GB로 컨테이너 10개 이상 실행 시 OOM 발생.
> 이후 e2-medium(RAM 4GB)으로 변경. 처음부터 e2-medium으로 생성 권장.

생성 확인:
```bash
gcloud compute instances list --project=chargeplus-490312
# NAME             ZONE               MACHINE_TYPE  INTERNAL_IP  EXTERNAL_IP   STATUS
# chargeplus-vm    asia-northeast3-a  e2-medium     10.178.0.2   34.50.12.65   RUNNING
```

---

## 3. 방화벽 규칙 설정

```bash
# HTTP (포트 80) 허용
gcloud compute firewall-rules create allow-http \
  --project=chargeplus-490312 \
  --direction=INGRESS \
  --priority=1000 \
  --network=default \
  --action=ALLOW \
  --rules=tcp:80 \
  --source-ranges=0.0.0.0/0

# HTTPS (포트 443) 허용
gcloud compute firewall-rules create allow-https \
  --project=chargeplus-490312 \
  --direction=INGRESS \
  --priority=1000 \
  --network=default \
  --action=ALLOW \
  --rules=tcp:443 \
  --source-ranges=0.0.0.0/0

# OCPP 게이트웨이 (포트 9000) 허용 - ocpp-server 태그가 있는 VM만
gcloud compute firewall-rules create allow-ocpp-gateway \
  --project=chargeplus-490312 \
  --direction=INGRESS \
  --priority=1000 \
  --network=default \
  --action=ALLOW \
  --rules=tcp:9000 \
  --source-ranges=0.0.0.0/0 \
  --target-tags=ocpp-server

# 방화벽 규칙 목록 확인
gcloud compute firewall-rules list --project=chargeplus-490312
```

---

## 4. VM 초기 설정

VM에 SSH 접속 후 Docker와 Git을 설치합니다.

```bash
# VM SSH 접속
gcloud compute ssh chargeplus-vm \
  --zone=asia-northeast3-a \
  --project=chargeplus-490312
```

VM 내부에서:

```bash
# 패키지 목록 업데이트
sudo apt-get update

# Docker 설치
sudo apt-get install -y docker.io

# Docker Compose 플러그인 설치 (docker compose 명령어)
sudo apt-get install -y docker-compose-plugin

# Docker 서비스 자동 시작 설정
sudo systemctl enable docker
sudo systemctl start docker

# 현재 사용자를 docker 그룹에 추가 (sudo 없이 docker 사용 가능)
sudo usermod -aG docker $USER

# Git 설치
sudo apt-get install -y git

# 설치 확인
docker --version
# Docker version 24.x.x

docker compose version
# Docker Compose version v2.x.x

git --version
# git version 2.x.x
```

---

## 5. 애플리케이션 배포

### 코드 클론

```bash
# VM에서
cd ~
git clone https://github.com/jeongsooh/chargeplus.git
cd chargeplus
```

### .env 파일 생성

```bash
cat > .env << 'EOF'
# Django
SECRET_KEY=1QpuOB7K1Ey54If6J68fa6MPwtU_6M1FoC9_1ONCtrSLFFYeye
DJANGO_SETTINGS_MODULE=chargeplus.settings.development
ALLOWED_HOSTS=*
CSRF_TRUSTED_ORIGINS=https://chargeplus.kr,https://www.chargeplus.kr

# Database
POSTGRES_DB=chargeplus
POSTGRES_USER=chargeplus
POSTGRES_PASSWORD=ChargePlus2026Secure
DATABASE_URL=postgresql://chargeplus:ChargePlus2026Secure@db:5432/chargeplus

# Redis
REDIS_URL=redis://redis:6379/0
CELERY_BROKER_URL=redis://redis:6379/1
CELERY_RESULT_BACKEND=redis://redis:6379/2

# Gateway
GATEWAY_HOST=0.0.0.0
GATEWAY_PORT=9000
OCPP_SECURITY_PROFILE=0
RESPONSE_TIMEOUT=10.0
EOF
```

### Docker 이미지 빌드 및 컨테이너 시작

```bash
# 전체 스택 빌드 및 시작
sudo docker compose up -d --build

# 컨테이너 상태 확인
sudo docker compose ps
# 아래와 같이 모두 Up 상태여야 함:
# chargeplus-nginx-1              Up
# chargeplus-gateway-1            Up
# chargeplus-gateway-2            Up
# chargeplus-backend-1            Up
# chargeplus-worker-core-1        Up
# chargeplus-worker-core-2        Up
# chargeplus-worker-telemetry-1   Up
# chargeplus-worker-telemetry-2   Up
# chargeplus-worker-telemetry-3   Up
# chargeplus-worker-telemetry-4   Up
# chargeplus-worker-management-1  Up
# chargeplus-worker-commands-1    Up
# chargeplus-dispatcher-1         Up
# chargeplus-db-1                 Up
# chargeplus-redis-1              Up
```

### 빌드 후 발생한 이슈: DB 비밀번호 불일치

기존 postgres_data 볼륨에 저장된 비밀번호와 .env의 비밀번호가 다를 경우 backend가 재시작을 반복합니다.

```bash
# 증상: backend 컨테이너가 Restarting 상태
sudo docker compose logs backend --tail=20
# django.db.utils.OperationalError: FATAL: password authentication failed for user "chargeplus"

# 해결: DB에 접속해 비밀번호 재설정
sudo docker compose exec db psql -U chargeplus -c \
  "ALTER USER chargeplus WITH PASSWORD 'ChargePlus2026Secure';"

# backend 재시작
sudo docker compose restart backend

# 정상 확인
sudo docker compose ps backend
# chargeplus-backend-1   Up
```

### 배포 확인

```bash
# VM 내부에서
curl -s http://localhost/health
# OK

curl -s http://localhost/api/v1/stations/
# {"detail":"자격 인증데이터(authentication credentials)가 제공되지 않았습니다."}
# → 401 응답 = 백엔드 정상 동작

# 외부에서 (로컬 PC)
curl http://34.50.12.65/health
# OK

curl http://34.50.12.65/api/v1/stations/
# {"detail":"..."}
```

---

## 6. 테스트 데이터 설정

tests/ 폴더가 컨테이너 내부에 없으므로 docker cp로 복사합니다.

```bash
# VM에서
sudo docker cp ~/chargeplus/tests/setup_testdata.py chargeplus-backend-1:/app/setup_testdata.py
sudo docker compose exec backend python /app/setup_testdata.py
```

출력 예시:
```
=== Setting up test data ===
✓ Admin user created: admin / admin1234!
✓ Test user created: testuser / testpass1234
✓ Operator created: Test Operator
✓ Station created: CP-TEST-001
✓ EVSE + Connector created: connector_id=1, Type2, 7.4kW
✓ RFID token created: RFID-TEST-001 (Accepted)
✓ App token created: APP-2 (Accepted)
=== Test data setup complete ===
```

---

## 7. 도메인 연결

### DNS A 레코드 설정

도메인 등록 업체 DNS 관리 페이지에서:

| 타입 | 호스트 | 값 | TTL |
|------|--------|----|-----|
| A | `@` | `34.50.12.65` | 300 |
| A | `www` | `34.50.12.65` | 300 |

### DNS 전파 확인

```bash
# Windows 로컬에서
nslookup chargeplus.kr
# 이름: chargeplus.kr
# Address: 34.50.12.65

ping chargeplus.kr
# 34.50.12.65의 응답: 바이트=32 시간=5ms TTL=57
```

---

## 8. HTTPS 설정 (Let's Encrypt)

### certbot 설치 및 인증서 발급

```bash
# VM에서
# certbot 설치 (Ubuntu 22.04)
sudo apt-get install -y certbot

# nginx 컨테이너를 잠시 중단 (포트 80이 필요)
cd ~/chargeplus
sudo docker compose stop nginx

# 인증서 발급 (standalone 모드)
sudo certbot certonly \
  --standalone \
  -d chargeplus.kr \
  -d www.chargeplus.kr \
  --non-interactive \
  --agree-tos \
  --email admin@chargeplus.kr
```

발급 결과:
```
Successfully received certificate.
Certificate is saved at: /etc/letsencrypt/live/chargeplus.kr/fullchain.pem
Key is saved at:         /etc/letsencrypt/live/chargeplus.kr/privkey.pem
This certificate expires on 2026-06-13.
Certbot has set up a scheduled task to automatically renew this certificate in the background.
```

### nginx 설정 업데이트

`nginx/nginx.conf`를 HTTPS 지원으로 수정 (GitHub에서 pull):

```bash
# VM에서
cd ~/chargeplus
git pull

# nginx 재시작 (인증서 볼륨 마운트 포함)
sudo docker compose up -d nginx
```

`docker-compose.yml`의 nginx 서비스에 추가된 볼륨:
```yaml
volumes:
  - ./nginx/nginx.conf:/etc/nginx/nginx.conf:ro
  - /etc/letsencrypt:/etc/letsencrypt:ro  # 인증서 마운트
```

### HTTPS 확인

```bash
curl -s -o /dev/null -w '%{http_code}' https://chargeplus.kr/health
# 200

curl -s https://chargeplus.kr/api/v1/stations/
# {"detail":"자격 인증데이터..."}
```

### 인증서 자동 갱신

certbot이 systemd timer 또는 cron으로 자동 갱신을 설정합니다.
단, nginx가 Docker 컨테이너로 실행 중이므로 갱신 시 컨테이너를 재시작해야 합니다.

```bash
# /etc/cron.d/certbot 또는 /etc/systemd/system/certbot.timer 확인
systemctl status certbot.timer

# 수동 갱신 테스트
sudo docker compose stop nginx
sudo certbot renew --dry-run
sudo docker compose up -d nginx
```

---

## 9. IP 고정

GCE VM의 외부 IP는 기본적으로 임시 할당입니다. VM 재시작 시 IP가 바뀌지 않도록 고정합니다.

```bash
# 현재 사용 중인 IP를 정적 IP로 예약
gcloud compute addresses create chargeplus-ip \
  --region=asia-northeast3 \
  --addresses=34.50.12.65 \
  --project=chargeplus-490312
```

출력:
```
Created [https://www.googleapis.com/compute/v1/projects/chargeplus-490312/regions/asia-northeast3/addresses/chargeplus-ip].
```

예약 확인:
```bash
gcloud compute addresses list --project=chargeplus-490312
# NAME           ADDRESS/RANGE  TYPE      PURPOSE  NETWORK  REGION            SUBNET  STATUS
# chargeplus-ip  34.50.12.65    EXTERNAL                    asia-northeast3           IN_USE
```

---

## 10. 배포 업데이트 방법

코드 변경 후 GCE VM에 반영하는 절차.

> **핵심 주의사항:** backend 코드는 Docker 이미지에 빌드되므로 반드시 `--build backend` 옵션을 붙여야 변경사항이 반영된다. `git pull`만 하거나 `docker compose up -d`만 하면 이전 이미지가 그대로 실행된다.

---

### Step 1 — 로컬: 커밋 및 push

```bash
cd D:/projects/ChargePlus

# 변경 파일 확인
git status

# 스테이징 (파일 지정 권장, git add . 는 .env 등 실수 위험)
git add backend/apps/... gateway/...

# 커밋
git commit -m "feat: 변경 내용 설명"

# GitHub push
git push origin master
```

---

### Step 2 — GCP VM: pull → 빌드 → 재시작

#### 방법 A: 로컬에서 원격 명령 한 번에 실행 (권장)

```bash
# backend만 재빌드 (코드 변경 시 가장 자주 사용)
gcloud compute ssh chargeplus-vm \
  --zone=asia-northeast3-a \
  --project=chargeplus-490312 \
  --command="cd ~/chargeplus && git pull origin master && sudo docker compose up -d --build backend 2>&1 | tail -30"
```

```bash
# 마이그레이션이 포함된 경우 (models.py 추가/변경, makemigrations 실행 후)
gcloud compute ssh chargeplus-vm \
  --zone=asia-northeast3-a \
  --project=chargeplus-490312 \
  --command="cd ~/chargeplus && git pull origin master && sudo docker compose up -d --build backend && sudo docker compose exec backend python manage.py migrate"
```

```bash
# gateway 코드도 변경된 경우 (gateway + backend 동시 재빌드)
gcloud compute ssh chargeplus-vm \
  --zone=asia-northeast3-a \
  --project=chargeplus-490312 \
  --command="cd ~/chargeplus && git pull origin master && sudo docker compose up -d --build backend gateway 2>&1 | tail -30"
```

```bash
# nginx 설정만 변경된 경우 (--build 불필요, 설정 파일은 볼륨 마운트)
gcloud compute ssh chargeplus-vm \
  --zone=asia-northeast3-a \
  --project=chargeplus-490312 \
  --command="cd ~/chargeplus && git pull origin master && sudo docker compose up -d nginx"
```

```bash
# 전체 스택 재빌드 (대규모 변경, requirements.txt 변경 등)
gcloud compute ssh chargeplus-vm \
  --zone=asia-northeast3-a \
  --project=chargeplus-490312 \
  --command="cd ~/chargeplus && git pull origin master && sudo docker compose up -d --build 2>&1 | tail -30"
```

#### 방법 B: VM에 직접 SSH 접속 후 실행

```bash
# VM 접속
gcloud compute ssh chargeplus-vm \
  --zone=asia-northeast3-a \
  --project=chargeplus-490312

# VM 내부에서 순서대로 실행
cd ~/chargeplus
git pull origin master
sudo docker compose up -d --build backend
sudo docker compose exec backend python manage.py migrate   # 마이그레이션 있을 때만
sudo docker compose ps                                      # 상태 확인
```

---

### Step 3 — 배포 확인

```bash
# 컨테이너 전체 상태 확인
gcloud compute ssh chargeplus-vm \
  --zone=asia-northeast3-a \
  --project=chargeplus-490312 \
  --command="cd ~/chargeplus && sudo docker compose ps"

# backend 로그 (최근 30줄)
gcloud compute ssh chargeplus-vm \
  --zone=asia-northeast3-a \
  --project=chargeplus-490312 \
  --command="cd ~/chargeplus && sudo docker compose logs backend --tail=30"

# 헬스체크 (외부에서)
curl -s https://chargeplus.kr/health
# OK

# API 응답 확인
curl -s https://chargeplus.kr/api/v1/stations/
# {"detail":"자격 인증데이터..."}  ← 401이면 정상 동작
```

---

### 서비스별 재빌드 필요 여부 정리

| 변경 내용 | 재빌드 대상 | 마이그레이션 |
|-----------|-------------|-------------|
| `backend/` Python 코드 | `backend` | 불필요 |
| `backend/apps/*/models.py` | `backend` | **필요** |
| `backend/requirements.txt` | `backend` | 불필요 |
| `gateway/` Python 코드 | `gateway` | 불필요 |
| `gateway/requirements.txt` | `gateway` | 불필요 |
| `nginx/nginx.conf` | (재빌드 불필요, 볼륨) | 불필요 |
| `docker-compose.yml` 환경변수 | 해당 서비스 전체 | 불필요 |

---

## 11. VM 스펙 변경

VM을 중지해야 스펙 변경이 가능합니다.

```bash
# VM 중지
gcloud compute instances stop chargeplus-vm \
  --zone=asia-northeast3-a \
  --project=chargeplus-490312

# 머신 타입 변경 (예: e2-medium → e2-standard-2)
gcloud compute instances set-machine-type chargeplus-vm \
  --zone=asia-northeast3-a \
  --project=chargeplus-490312 \
  --machine-type=e2-medium

# VM 재시작
gcloud compute instances start chargeplus-vm \
  --zone=asia-northeast3-a \
  --project=chargeplus-490312
```

> **주의:** VM 재시작 후 Docker 컨테이너는 `restart: unless-stopped` 정책에 따라 자동으로 재시작됩니다.
> 단, DB 비밀번호 불일치 문제가 재발할 수 있으므로 backend 로그를 확인하세요.

---

## 현재 운영 중인 서비스 정보

| 항목 | 값 |
|------|-----|
| GCP 프로젝트 | chargeplus-490312 |
| GCP 계정 | gresystem2023@gmail.com |
| VM | chargeplus-vm (e2-medium, asia-northeast3-a) |
| 외부 IP | 34.50.12.65 (정적) |
| 도메인 | chargeplus.kr |
| HTTPS 인증서 | Let's Encrypt (만료: 2026-06-13, 자동갱신) |
| GitHub | https://github.com/jeongsooh/chargeplus |
| Admin | https://chargeplus.kr/admin/ (admin / admin1234!) |
| API | https://chargeplus.kr/api/ |
| OCPP WebSocket | wss://chargeplus.kr/ocpp/1.6/{station_id} |
