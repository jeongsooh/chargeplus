import logging
from decimal import Decimal

from celery import shared_task
from django.utils import timezone

from apps.ocpp16.models import OcppMessage
from apps.ocpp16.utils import utcnow_iso, parse_ocpp_timestamp
from .base import publish_response, log_ocpp_message

logger = logging.getLogger(__name__)


@shared_task(queue='ocpp.q.telemetry', bind=True, max_retries=0, name='apps.ocpp16.tasks.telemetry.handle_heartbeat')
def handle_heartbeat(self, station_id: str, msg_id: str, payload: dict):
    """
    Handle Heartbeat from charge point.
    Updates last_heartbeat timestamp and refreshes Redis TTL.
    """
    from apps.stations.models import ChargingStation
    from apps.config.models import CsmsVariable
    from apps.ocpp16.redis_client import get_redis

    try:
        log_ocpp_message(station_id, msg_id, OcppMessage.Direction.INBOUND, 'Heartbeat', payload)

        # Update heartbeat timestamp
        ChargingStation.objects.filter(station_id=station_id).update(
            last_heartbeat=timezone.now()
        )

        # Refresh Redis connected key TTL
        interval = int(CsmsVariable.get("heartbeat_interval", station_id=station_id, default=60))
        r = get_redis()
        r.set(f"ocpp:connected:{station_id}", "1", ex=interval * 3)

        response = {"currentTime": utcnow_iso()}
        publish_response(msg_id, response)
        log_ocpp_message(station_id, msg_id, OcppMessage.Direction.OUTBOUND, 'Heartbeat', response)

    except Exception as e:
        logger.exception(f"handle_heartbeat error for station={station_id}: {e}")
        publish_response(msg_id, {"currentTime": utcnow_iso()})


@shared_task(queue='ocpp.q.telemetry', bind=True, max_retries=0, name='apps.ocpp16.tasks.telemetry.handle_status_notification')
def handle_status_notification(self, station_id: str, msg_id: str, payload: dict):
    """
    Handle StatusNotification from charge point.
    - connectorId=0: update ChargingStation.status
    - connectorId>=1: update Connector status fields
    - Send error alert if error_code != 'NoError'
    """
    from apps.stations.models import ChargingStation, Connector
    from apps.ocpp16.services.notification import NotificationService

    try:
        log_ocpp_message(station_id, msg_id, OcppMessage.Direction.INBOUND, 'StatusNotification', payload)

        connector_id = payload.get('connectorId', 0)
        ocpp_status = payload.get('status', 'Available')
        error_code = payload.get('errorCode', 'NoError')
        info = payload.get('info', '')
        vendor_id = payload.get('vendorId', '')
        vendor_error_code = payload.get('vendorErrorCode', '')

        now = timezone.now()

        if connector_id == 0:
            # Station-wide status
            status_map = {
                'Available': ChargingStation.Status.AVAILABLE,
                'Unavailable': ChargingStation.Status.UNAVAILABLE,
                'Faulted': ChargingStation.Status.FAULTED,
            }
            station_status = status_map.get(ocpp_status, ChargingStation.Status.UNAVAILABLE)
            ChargingStation.objects.filter(station_id=station_id).update(status=station_status)
            logger.info(f"StatusNotification: station={station_id} connector=0 status={ocpp_status}")

        else:
            # Individual connector status — auto-create EVSE/Connector if first time seen
            from apps.stations.models import EVSE
            from apps.stations.utils import resolve_connector_location
            try:
                station = ChargingStation.objects.get(station_id=station_id)

                evse_id, connector_within = resolve_connector_location(station, connector_id)
                evse, _ = EVSE.objects.get_or_create(
                    charging_station=station,
                    evse_id=evse_id,
                )

                connector, created = Connector.objects.get_or_create(
                    evse=evse,
                    connector_id=connector_within,
                    defaults={
                        'current_status': ocpp_status,
                        'error_code': error_code,
                        'info': info,
                        'vendor_id': vendor_id,
                        'vendor_error_code': vendor_error_code,
                        'status_updated_at': now,
                    },
                )

                if not created:
                    Connector.objects.filter(pk=connector.pk).update(
                        current_status=ocpp_status,
                        error_code=error_code,
                        info=info,
                        vendor_id=vendor_id,
                        vendor_error_code=vendor_error_code,
                        status_updated_at=now,
                    )

                logger.info(
                    f"StatusNotification: station={station_id} connector={connector_id} "
                    f"→ EVSE-{evse_id}/C-{connector_within} "
                    f"status={ocpp_status} error={error_code}"
                    + (" (auto-created)" if created else "")
                )
            except ChargingStation.DoesNotExist:
                logger.warning(f"StatusNotification: station {station_id} not found in DB")

        # Send error alert if there's a fault
        if error_code and error_code != 'NoError':
            NotificationService.send_error_alert(station_id, connector_id, error_code)

        publish_response(msg_id, {})
        log_ocpp_message(station_id, msg_id, OcppMessage.Direction.OUTBOUND, 'StatusNotification', {})

    except Exception as e:
        logger.exception(f"handle_status_notification error for station={station_id}: {e}")
        publish_response(msg_id, {})


@shared_task(queue='ocpp.q.telemetry', bind=True, max_retries=0, name='apps.ocpp16.tasks.telemetry.handle_meter_values')
def handle_meter_values(self, station_id: str, msg_id: str, payload: dict):
    """
    Handle MeterValues from charge point.
    - Saves MeterValue records to database
    - Updates AppSession.kwh_current for active app sessions
    """
    from apps.transactions.models import Transaction, MeterValue

    try:
        log_ocpp_message(station_id, msg_id, OcppMessage.Direction.INBOUND, 'MeterValues', payload)

        transaction_id = payload.get('transactionId')
        connector_id = payload.get('connectorId', 1)
        meter_value_list = payload.get('meterValue', [])

        transaction = None
        if transaction_id:
            try:
                transaction = Transaction.objects.get(
                    transaction_id=transaction_id,
                    state=Transaction.State.ACTIVE,
                )
            except Transaction.DoesNotExist:
                logger.warning(f"MeterValues: transaction {transaction_id} not found or not active")

        # Process and save meter values
        meter_value_objects = []
        latest_energy_wh = None  # Track latest Energy.Active.Import.Register

        for mv_entry in meter_value_list:
            ts_str = mv_entry.get('timestamp', '')
            sampled_values = mv_entry.get('sampledValue', [])

            try:
                timestamp = parse_ocpp_timestamp(ts_str)
            except ValueError:
                timestamp = timezone.now()

            for sv in sampled_values:
                measurand = sv.get('measurand', 'Energy.Active.Import.Register')
                value_str = sv.get('value', '0')
                unit = sv.get('unit', 'Wh')
                phase = sv.get('phase', '')
                context = sv.get('context', '')
                location = sv.get('location', '')

                try:
                    value = Decimal(str(value_str))
                except Exception:
                    logger.warning(f"Cannot parse meter value: {value_str}")
                    continue

                if transaction:
                    meter_value_objects.append(MeterValue(
                        transaction=transaction,
                        timestamp=timestamp,
                        measurand=measurand,
                        phase=phase,
                        value=value,
                        unit=unit,
                        context=context,
                        location=location,
                    ))

                # Track energy for AppSession update
                if measurand == 'Energy.Active.Import.Register':
                    # Convert to Wh if needed
                    if unit == 'kWh':
                        latest_energy_wh = float(value) * 1000
                    else:
                        latest_energy_wh = float(value)

        # Bulk insert meter values
        if meter_value_objects:
            MeterValue.objects.bulk_create(meter_value_objects, ignore_conflicts=False)
            logger.debug(f"Saved {len(meter_value_objects)} meter values for TX#{transaction_id}")

        # Update AppSession current kWh
        if transaction and latest_energy_wh is not None:
            try:
                from apps.mobile_api.models import AppSession
                kwh_current = (latest_energy_wh - transaction.meter_start) / 1000.0
                if kwh_current < 0:
                    kwh_current = 0.0
                AppSession.objects.filter(
                    transaction=transaction,
                    status=AppSession.Status.ACTIVE,
                ).update(kwh_current=round(kwh_current, 3))
            except Exception as e:
                logger.error(f"Failed to update AppSession kwh_current: {e}")

        publish_response(msg_id, {})
        log_ocpp_message(station_id, msg_id, OcppMessage.Direction.OUTBOUND, 'MeterValues', {})

    except Exception as e:
        logger.exception(f"handle_meter_values error for station={station_id}: {e}")
        publish_response(msg_id, {})
