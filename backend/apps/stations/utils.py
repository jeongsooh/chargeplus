"""
충전기 EVSE/Connector 구조 유틸리티.

OCPP 1.6에서 connectorId는 충전기 단위의 flat 1-based 정수이다.
서버 DB는 ChargingStation → EVSE → Connector 계층 구조를 사용하므로,
flat connectorId를 (evse_id, connector_id_within_evse) 로 변환하는 로직이 필요하다.

매핑 공식 (num_connectors_per_evse = C):
  evse_id          = (flat_id - 1) // C + 1
  connector_within = (flat_id - 1) %  C + 1

예시:
  C=1  → flat 1→(EVSE1,C1), flat 2→(EVSE2,C1), flat 3→(EVSE3,C1), flat 4→(EVSE4,C1)
  C=2  → flat 1→(EVSE1,C1), flat 2→(EVSE1,C2), flat 3→(EVSE2,C1), flat 4→(EVSE2,C2)
  C=4  → flat 1→(EVSE1,C1), flat 2→(EVSE1,C2), flat 3→(EVSE1,C3), flat 4→(EVSE1,C4)
"""
import logging

from django.utils import timezone

logger = logging.getLogger(__name__)


def resolve_connector_location(station, flat_connector_id: int) -> tuple[int, int]:
    """
    OCPP flat connectorId → (evse_id, connector_id_within_evse).

    Args:
        station: ChargingStation 인스턴스
        flat_connector_id: OCPP 1.6 connectorId (1 이상)

    Returns:
        (evse_id, connector_id_within_evse) 튜플
    """
    c_per_evse = max(station.num_connectors_per_evse or 1, 1)
    evse_id = (flat_connector_id - 1) // c_per_evse + 1
    connector_within = (flat_connector_id - 1) % c_per_evse + 1
    return evse_id, connector_within


def provision_connectors(station) -> None:
    """
    num_evses × num_connectors_per_evse 구조로 EVSE/Connector를 생성한다.

    - 이미 존재하는 EVSE/Connector는 생성하지 않는다 (get_or_create).
    - 설정 범위 밖의 기존 EVSE/Connector는 건드리지 않는다.
    - 새로 생성된 Connector의 initial status = UNAVAILABLE.

    BootNotification 처리 후 호출.
    """
    from apps.stations.models import EVSE, Connector

    num_evses = max(station.num_evses or 1, 1)
    num_connectors = max(station.num_connectors_per_evse or 1, 1)

    created_count = 0
    for evse_idx in range(1, num_evses + 1):
        evse, evse_created = EVSE.objects.get_or_create(
            charging_station=station,
            evse_id=evse_idx,
        )
        if evse_created:
            logger.info(f"provision_connectors: created EVSE-{evse_idx} for {station.station_id}")

        for conn_idx in range(1, num_connectors + 1):
            _, conn_created = Connector.objects.get_or_create(
                evse=evse,
                connector_id=conn_idx,
                defaults={
                    'current_status': Connector.Status.UNAVAILABLE,
                    'status_updated_at': timezone.now(),
                },
            )
            if conn_created:
                created_count += 1

    if created_count:
        logger.info(
            f"provision_connectors: {station.station_id} — "
            f"created {created_count} connector(s) "
            f"({num_evses} EVSE × {num_connectors} connector)"
        )
