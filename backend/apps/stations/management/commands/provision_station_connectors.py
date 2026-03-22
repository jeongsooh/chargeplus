"""
관리 명령: provision_station_connectors

등록된 충전기의 num_evses × num_connectors_per_evse 기준으로
EVSE/Connector DB 구조를 생성/보정한다.

사용법:
    python manage.py provision_station_connectors
    python manage.py provision_station_connectors --station_id ENT300136
    python manage.py provision_station_connectors --reset_status
"""
from django.core.management.base import BaseCommand
from django.utils import timezone


class Command(BaseCommand):
    help = 'EVSE/Connector 구조를 num_evses × num_connectors_per_evse 기준으로 생성/보정합니다.'

    def add_arguments(self, parser):
        parser.add_argument(
            '--station_id',
            type=str,
            default='',
            help='특정 station_id만 처리 (생략 시 전체)',
        )
        parser.add_argument(
            '--reset_status',
            action='store_true',
            help='모든 Connector status를 UNAVAILABLE로 초기화',
        )

    def handle(self, *args, **options):
        from apps.stations.models import ChargingStation, Connector
        from apps.stations.utils import provision_connectors

        station_id = options.get('station_id', '').strip()
        reset_status = options.get('reset_status', False)

        qs = ChargingStation.objects.all().order_by('station_id')
        if station_id:
            qs = qs.filter(station_id=station_id)

        if not qs.exists():
            self.stdout.write(self.style.WARNING('처리할 충전기가 없습니다.'))
            return

        for station in qs:
            provision_connectors(station)
            total = station.num_evses * station.num_connectors_per_evse
            self.stdout.write(
                self.style.SUCCESS(
                    f'✓ {station.station_id}: '
                    f'{station.num_evses} EVSE × {station.num_connectors_per_evse} connector '
                    f'= 총 {total}개'
                )
            )

            if reset_status:
                updated = Connector.objects.filter(
                    evse__charging_station=station,
                ).update(
                    current_status=Connector.Status.UNAVAILABLE,
                    status_updated_at=timezone.now(),
                )
                self.stdout.write(f'  → {updated}개 커넥터 상태 UNAVAILABLE 초기화')

        self.stdout.write(self.style.SUCCESS(f'\n완료: {qs.count()}개 충전기 처리'))
