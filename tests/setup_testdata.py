"""
테스트용 초기 데이터 생성 스크립트.
docker exec로 backend 컨테이너 내부에서 실행한다.

사용법 (호스트에서):
    docker compose exec backend python tests/setup_testdata.py

또는 직접 실행:
    docker compose exec backend python manage.py shell < tests/setup_testdata_shell.py
"""
import os
import sys
import django

# Django 설정
sys.path.insert(0, '/app')
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'chargeplus.settings.development')
django.setup()

from django.contrib.auth import get_user_model
from apps.stations.models import Operator, ChargingStation, EVSE, Connector
from apps.authorization.models import IdToken

User = get_user_model()

print("=== Setting up test data ===\n")

# 1. 관리자 계정 생성
admin, created = User.objects.get_or_create(
    username='admin',
    defaults={
        'email': 'admin@example.com',
        'is_staff': True,
        'is_superuser': True,
    }
)
if created:
    admin.set_password('admin1234!')
    admin.save()
    print("✓ Admin user created: admin / admin1234!")
else:
    print("✓ Admin user already exists")

# 2. 테스트 일반 사용자 생성
testuser, created = User.objects.get_or_create(
    username='testuser',
    defaults={
        'email': 'testuser@example.com',
        'is_staff': False,
        'is_superuser': False,
        'phone': '010-1234-5678',
    }
)
if created:
    testuser.set_password('testpass1234')
    testuser.save()
    print("✓ Test user created: testuser / testpass1234")
else:
    print("✓ Test user already exists")

# 3. Operator 생성
operator, created = Operator.objects.get_or_create(
    code='TEST',
    defaults={'name': 'Test Operator'},
)
print(f"{'✓ Operator created' if created else '✓ Operator exists'}: {operator.name}")

# 4. 테스트 충전기 생성
station, created = ChargingStation.objects.get_or_create(
    station_id='CP-TEST-001',
    defaults={
        'operator': operator,
        'vendor_name': 'TestVendor',
        'model': 'Simulator-1',
        'firmware_version': '1.0.0-test',
        'address': '서울특별시 테스트구 테스트로 1',
        'is_active': True,
        'status': ChargingStation.Status.OFFLINE,
    }
)
print(f"{'✓ Station created' if created else '✓ Station exists'}: {station.station_id}")

# 5. EVSE + Connector 생성
evse, evse_created = EVSE.objects.get_or_create(
    charging_station=station,
    evse_id=1,
)
connector, conn_created = Connector.objects.get_or_create(
    evse=evse,
    connector_id=1,
    defaults={
        'connector_type': Connector.Type.TYPE2,
        'max_power_kw': 7.4,
        'current_status': Connector.Status.UNAVAILABLE,
    }
)
if conn_created:
    print("✓ EVSE + Connector created: connector_id=1, Type2, 7.4kW")
else:
    print("✓ EVSE + Connector already exists")

# 6. 테스트용 RFID 카드 생성
rfid_token, created = IdToken.objects.get_or_create(
    id_token='RFID-TEST-001',
    defaults={
        'token_type': IdToken.Type.RFID,
        'status': IdToken.Status.ACCEPTED,
        'user': testuser,
    }
)
print(f"{'✓ RFID token created' if created else '✓ RFID token exists'}: RFID-TEST-001 (Accepted)")

# 7. 앱 사용자용 가상 IdToken
app_token_id = f"APP-{testuser.pk}"
app_token, created = IdToken.objects.get_or_create(
    id_token=app_token_id,
    defaults={
        'token_type': IdToken.Type.APP,
        'status': IdToken.Status.ACCEPTED,
        'user': testuser,
    }
)
print(f"{'✓ App token created' if created else '✓ App token exists'}: {app_token_id} (Accepted)")

print("\n=== Test data setup complete ===")
print("""
접속 정보:
  Django Admin:  http://localhost:8000/admin/
    - 계정: admin / admin1234!

  API 테스트:
    - 일반 사용자: testuser / testpass1234
    - 충전기 ID:   CP-TEST-001

  시뮬레이터 실행:
    python tests/cp_simulator.py --station-id CP-TEST-001

  API 테스트 실행:
    python tests/test_api.py --station-id CP-TEST-001
""")
