# ChargePlus 다국어(i18n) 지원 구현 계획서

## 1. 개요

ChargePlus 포털 및 모바일 API의 모든 사용자 노출 텍스트를 3개 언어로 지원한다.

| 코드 | 언어 | 표기 |
|------|------|------|
| `ko` | 한국어 | 한국어 |
| `en` | 영어 | English |
| `vi` | 베트남어 | Tiếng Việt |

---

## 2. 기술 방식

Django 내장 i18n 프레임워크(`gettext`)를 사용한다.

| 구분 | 방식 |
|------|------|
| 템플릿 텍스트 | `{% load i18n %}` + `{% trans "..." %}` |
| Python 메시지 | `from django.utils.translation import gettext_lazy as _` |
| 번역 저장소 | `backend/locale/{ko,en,vi}/LC_MESSAGES/django.po` |
| 언어 감지 순서 | Session → Cookie → Accept-Language 헤더 |
| 언어 전환 UI | 로그인 화면 + 모든 포털 사이드바 하단 |
| 언어 전환 API | Django 내장 `set_language` 뷰 (`/i18n/set_language/`) |

---

## 3. 수정 파일 목록

### 3.1 인프라 (5개 파일)

| 파일 | 변경 내용 |
|------|-----------|
| `backend/Dockerfile` | `gettext` 패키지 추가 (compilemessages 필요) |
| `backend/chargeplus/settings/base.py` | LANGUAGES, LOCALE_PATHS, LocaleMiddleware 추가 |
| `backend/chargeplus/urls.py` | `i18n_patterns` 또는 `set_language` URL 추가 |
| `backend/locale/ko/LC_MESSAGES/django.po` | 한국어 번역 (원본, 대부분 공백) |
| `backend/locale/en/LC_MESSAGES/django.po` | 영어 번역 |
| `backend/locale/vi/LC_MESSAGES/django.po` | 베트남어 번역 |

### 3.2 기본 템플릿 (5개 파일)

| 파일 | 변경 내용 |
|------|-----------|
| `portal/templates/portal/base_auth.html` | html lang 동적화, 언어 선택기 추가 |
| `portal/templates/portal/base.html` | html lang 동적화, 사이드바 로그아웃 번역, 언어 선택기 추가 |
| `portal/templates/portal/cs/base_cs.html` | 사이드바 메뉴 전체 번역 태그 적용 |
| `portal/templates/portal/partner/base_partner.html` | 사이드바 메뉴 전체 번역 태그 적용 |
| `portal/templates/portal/customer/base_customer.html` | 사이드바 메뉴 전체 번역 태그 적용 |

### 3.3 인증 템플릿 (5개 파일)

| 파일 | 변경 내용 |
|------|-----------|
| `auth/login.html` | 폼 레이블, 버튼, 안내 문구 번역 |
| `auth/register_select.html` | 가입 유형 선택 텍스트 번역 |
| `auth/register_customer.html` | 가입 폼 전체 번역 |
| `auth/register_partner.html` | 가입 폼 전체 번역 |
| `auth/register_cs.html` | 가입 폼 전체 번역 |

### 3.4 콘텐츠 페이지 템플릿 (33개 파일)

CS 포털 19개, 파트너 포털 5개, 고객 포털 5개, 기타 4개의 한글 텍스트 전체 번역 태그 적용.

### 3.5 뷰 파일 (5개 파일)

| 파일 | 변경 내용 |
|------|-----------|
| `portal/views/auth.py` | messages.error/success 텍스트 `_()` 래핑 |
| `portal/views/cs.py` | messages.error/success 텍스트 `_()` 래핑 |
| `portal/views/partner.py` | messages.error/success 텍스트 `_()` 래핑 |
| `portal/views/customer.py` | messages.error/success 텍스트 `_()` 래핑 |
| `mobile_api/views.py` | JSON 에러 메시지 `_()` 래핑 |

---

## 4. 번역 사전

### 4.1 내비게이션 메뉴

| 한국어 (msgid) | English | Tiếng Việt |
|---------------|---------|------------|
| 대시보드 | Dashboard | Bảng điều khiển |
| 사용자 관리 | User Management | Quản lý người dùng |
| 파트너 관리 | Partner Management | Quản lý đối tác |
| 충전기 관리 | Charger Management | Quản lý trạm sạc |
| 충전소 관리 | Site Management | Quản lý địa điểm sạc |
| 충전이력 | Charging History | Lịch sử sạc |
| 정산내역 | Payments | Lịch sử thanh toán |
| 충전카드 관리 | Charge Card Management | Quản lý thẻ sạc |
| 시스템 운영 | System Operations | Vận hành hệ thống |
| 운영변수 설정 | System Config | Cấu hình vận hành |
| Active 충전기 설정 | Active Chargers | Trạm đang hoạt động |
| 메세지 로그 | Message Log | Nhật ký tin nhắn |
| 로그아웃 | Logout | Đăng xuất |
| 내 충전소 | My Sites | Địa điểm của tôi |
| 충전기 현황 | Charger Status | Tình trạng trạm sạc |
| 통계 | Statistics | Thống kê |
| 카드 관리 | Card Management | Quản lý thẻ |
| 프로필 | Profile | Hồ sơ |

### 4.2 인증 화면

| 한국어 | English | Tiếng Việt |
|--------|---------|------------|
| 포털 로그인 | Portal Login | Đăng nhập cổng thông tin |
| 아이디 | Username | Tên đăng nhập |
| 비밀번호 | Password | Mật khẩu |
| 로그인 | Login | Đăng nhập |
| 계정이 없으신가요? | Don't have an account? | Chưa có tài khoản? |
| 가입하기 | Sign Up | Đăng ký |
| 회원가입 유형을 선택해 주세요 | Select Account Type | Chọn loại tài khoản |
| 고객 | Customer | Khách hàng |
| 파트너 | Partner | Đối tác |
| 고객센터 직원 | CS Staff | Nhân viên CSKH |
| 이름 | Name | Họ tên |
| 이메일 | Email | Email |
| 전화번호 | Phone | Số điện thoại |
| 비밀번호 확인 | Confirm Password | Xác nhận mật khẩu |
| 사업체명 | Business Name | Tên doanh nghiệp |
| 사업자번호 | Business Number | Mã số doanh nghiệp |
| 담당자 연락처 | Contact Phone | Số điện thoại liên hệ |

### 4.3 에러/성공 메시지 (views)

| 한국어 | English | Tiếng Việt |
|--------|---------|------------|
| 아이디 또는 비밀번호가 올바르지 않습니다. | Invalid username or password. | Tên đăng nhập hoặc mật khẩu không đúng. |
| 계정이 활성화되어 있지 않습니다. 관리자 승인을 기다려 주세요. | Account is not active. Please wait for admin approval. | Tài khoản chưa được kích hoạt. Vui lòng chờ quản trị viên phê duyệt. |
| 가입을 환영합니다! | Welcome! | Chào mừng bạn! |
| 아이디를 입력해 주세요. | Please enter username. | Vui lòng nhập tên đăng nhập. |
| 이미 사용 중인 아이디입니다. | Username already taken. | Tên đăng nhập đã được sử dụng. |
| 비밀번호는 8자 이상이어야 합니다. | Password must be at least 8 characters. | Mật khẩu phải có ít nhất 8 ký tự. |
| 비밀번호가 일치하지 않습니다. | Passwords do not match. | Mật khẩu không khớp. |
| 아이디와 비밀번호를 입력해주세요. | Please enter username and password. | Vui lòng nhập tên đăng nhập và mật khẩu. |
| 아이디 또는 비밀번호가 틀렸습니다. | Invalid username or password. | Tên đăng nhập hoặc mật khẩu không đúng. |
| 비활성화된 계정입니다. | Account is deactivated. | Tài khoản bị vô hiệu hóa. |

---

## 5. 구현 순서

```
Phase 1: 인프라 설정
  ├── Dockerfile에 gettext 추가
  ├── settings/base.py 수정
  ├── urls.py 수정
  └── locale/ .po 파일 생성 (ko / en / vi)

Phase 2: 기본 템플릿
  ├── base_auth.html (언어 선택기 추가)
  ├── base.html (언어 선택기 추가)
  ├── base_cs.html (사이드바 번역)
  ├── base_partner.html (사이드바 번역)
  └── base_customer.html (사이드바 번역)

Phase 3: 인증 템플릿 (5개)
Phase 4: 콘텐츠 템플릿 (33개)
Phase 5: Views 메시지 번역

Phase 6: 빌드 & 배포
  ├── docker compose exec backend python manage.py compilemessages
  └── GCP 배포
```

---

## 6. 언어 선택기 UI 설계

```html
<!-- 로그인 페이지 / 사이드바 하단 공통 -->
<form action="/i18n/set_language/" method="post">
  {% csrf_token %}
  <input name="next" type="hidden" value="{{ request.get_full_path }}">
  <select name="language" onchange="this.form.submit()" class="form-select form-select-sm">
    <option value="ko" {% if LANGUAGE_CODE == 'ko' %}selected{% endif %}>🇰🇷 한국어</option>
    <option value="en" {% if LANGUAGE_CODE == 'en' %}selected{% endif %}>🇺🇸 English</option>
    <option value="vi" {% if LANGUAGE_CODE == 'vi' %}selected{% endif %}>🇻🇳 Tiếng Việt</option>
  </select>
</form>
```

---

## 7. 배포 시 주의사항

1. `gettext` 패키지가 Docker 이미지에 포함되어야 `compilemessages` 실행 가능
2. `python manage.py compilemessages`로 `.po` → `.mo` 컴파일 필요
3. `entrypoint.sh`에 compilemessages 자동 실행 추가 권장
4. `LocaleMiddleware`는 반드시 `SessionMiddleware` 뒤, `CommonMiddleware` 앞에 위치
