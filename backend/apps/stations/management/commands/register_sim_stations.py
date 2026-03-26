"""
관리 명령: register_sim_stations

SIM-0001 ~ SIM-0100 시리얼 번호를 가진 가상 충전기를 DB에 사전 등록한다.
충전기 ID 패턴: CP-SIM-0001 ~ CP-SIM-0100

사용법:
    python manage.py register_sim_stations
    python manage.py register_sim_stations --count 10
    python manage.py register_sim_stations --start 1 --count 5
"""
from django.core.management.base import BaseCommand


class Command(BaseCommand):
    help = 'SIM-XXXX 시리얼의 가상 충전기를 DB에 사전 등록합니다.'

    def add_arguments(self, parser):
        parser.add_argument(
            '--start',
            type=int,
            default=1,
            help='시작 번호 (기본값: 1)',
        )
        parser.add_argument(
            '--count',
            type=int,
            default=100,
            help='등록할 충전기 수 (기본값: 100)',
        )

    def handle(self, *args, **options):
        from apps.stations.models import ChargingStation, Operator
        from apps.stations.utils import provision_connectors

        start = options['start']
        count = options['count']

        operator, created = Operator.objects.get_or_create(
            code='SIM',
            defaults={'name': 'Simulator'},
        )
        if created:
            self.stdout.write(self.style.SUCCESS('Operator SIM 생성됨'))

        created_count = 0
        skipped_count = 0

        for i in range(start, start + count):
            serial = f'SIM-{i:04d}'
            cp_id = f'CP-SIM-{i:04d}'

            station, was_created = ChargingStation.objects.get_or_create(
                serial_number=serial,
                defaults={
                    'station_id': cp_id,
                    'operator': operator,
                    'is_active': True,
                    'num_evses': 1,
                    'num_connectors_per_evse': 1,
                },
            )

            if was_created:
                provision_connectors(station)
                created_count += 1
            else:
                skipped_count += 1

        self.stdout.write(
            self.style.SUCCESS(
                f'완료: {created_count}개 생성, {skipped_count}개 이미 존재'
            )
        )
