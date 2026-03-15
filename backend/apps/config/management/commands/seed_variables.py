import logging

from django.core.management.base import BaseCommand

logger = logging.getLogger(__name__)

INITIAL_VARIABLES = [
    {
        "key": "heartbeat_interval",
        "value": "60",
        "value_type": "int",
        "is_per_station": True,
        "description": "BootNotification 응답에 포함되는 heartbeat 주기 (초). "
                       "충전기가 이 주기로 Heartbeat를 전송한다.",
    },
    {
        "key": "connection_timeout",
        "value": "30",
        "value_type": "int",
        "is_per_station": False,
        "description": "RemoteStartTransaction 전송 후 StartTransaction 수신 대기 시간 (초).",
    },
    {
        "key": "pending_session_timeout",
        "value": "120",
        "value_type": "int",
        "is_per_station": False,
        "description": "AppSession이 pending 상태로 유지되는 최대 시간 (초). "
                       "초과 시 status=failed로 전환.",
    },
    {
        "key": "default_unit_price",
        "value": "270",
        "value_type": "int",
        "is_per_station": True,
        "description": "기본 충전 단가 (원/kWh). StationVariable로 충전기별 override 가능.",
    },
    {
        "key": "unit_price_overrides",
        "value": '{"EVN03": 210, "EVN07": 245}',
        "value_type": "json",
        "is_per_station": False,
        "description": "충전기 ID prefix 기반 단가 override 테이블 (JSON). "
                       "station_id.startswith(prefix) 순서로 매칭.",
    },
    {
        "key": "nonuser_unit_price",
        "value": "350",
        "value_type": "int",
        "is_per_station": False,
        "description": "비회원(앱 미사용) 충전 단가 (원/kWh).",
    },
    {
        "key": "jwt_access_token_lifetime_hours",
        "value": "24",
        "value_type": "int",
        "is_per_station": False,
        "description": "앱 JWT Access Token 유효 시간 (시간 단위).",
    },
    {
        "key": "notification_enabled",
        "value": "true",
        "value_type": "bool",
        "is_per_station": False,
        "description": "카카오 알림톡 / SMS 발송 활성화 여부.",
    },
    {
        "key": "notification_error_enabled",
        "value": "true",
        "value_type": "bool",
        "is_per_station": True,
        "description": "충전기 에러 발생 시 관리자 알림 발송 여부.",
    },
    {
        "key": "firmware_server_url",
        "value": "ftp://firmware.example.com/",
        "value_type": "str",
        "is_per_station": False,
        "description": "UpdateFirmware 명령에 사용될 기본 펌웨어 서버 URL.",
    },
    {
        "key": "session_cleanup_after_hours",
        "value": "24",
        "value_type": "int",
        "is_per_station": False,
        "description": "stopped/failed AppSession을 DB에서 정리하기까지의 보존 시간 (시간).",
    },
]


class Command(BaseCommand):
    help = 'Seed initial CsmsVariable records (upsert - does not overwrite existing values)'

    def handle(self, *args, **options):
        from apps.config.models import CsmsVariable

        created_count = 0
        skipped_count = 0

        for var_data in INITIAL_VARIABLES:
            key = var_data['key']
            try:
                obj, created = CsmsVariable.objects.get_or_create(
                    key=key,
                    defaults={
                        'value': var_data['value'],
                        'value_type': var_data['value_type'],
                        'is_per_station': var_data['is_per_station'],
                        'description': var_data.get('description', ''),
                        'updated_by': 'seed_variables',
                    },
                )
                if created:
                    created_count += 1
                    self.stdout.write(self.style.SUCCESS(f"  Created: {key}={var_data['value']}"))
                else:
                    skipped_count += 1
                    self.stdout.write(f"  Skipped (already exists): {key}")
            except Exception as e:
                self.stdout.write(self.style.ERROR(f"  Error seeding {key}: {e}"))
                logger.error(f"Error seeding CsmsVariable {key}: {e}")

        self.stdout.write(
            self.style.SUCCESS(
                f"\nSeed complete: {created_count} created, {skipped_count} skipped."
            )
        )
