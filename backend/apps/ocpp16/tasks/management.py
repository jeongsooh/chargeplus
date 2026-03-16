import logging

from celery import shared_task
from django.utils import timezone

from apps.ocpp16.models import OcppMessage
from apps.ocpp16.utils import utcnow_iso
from .base import publish_response, log_ocpp_message

logger = logging.getLogger(__name__)


@shared_task(queue='ocpp.q.management', bind=True, max_retries=0, name='apps.ocpp16.tasks.management.handle_boot_notification')
def handle_boot_notification(self, station_id: str, msg_id: str, payload: dict):
    """
    Handle BootNotification from charge point.
    - get_or_create ChargingStation record
    - Update device info from payload
    - Set appropriate status
    - Return heartbeat interval and current time
    """
    from apps.stations.models import ChargingStation, Operator
    from apps.config.models import CsmsVariable
    from apps.ocpp16.redis_client import get_redis

    try:
        # Log incoming message
        log_ocpp_message(station_id, msg_id, OcppMessage.Direction.INBOUND, 'BootNotification', payload)

        # Get or create the charging station
        # We need an operator - use default or first available
        default_operator, _ = Operator.objects.get_or_create(
            code='DEFAULT',
            defaults={'name': 'Default Operator'},
        )

        station, created = ChargingStation.objects.get_or_create(
            station_id=station_id,
            defaults={
                'operator': default_operator,
                'status': ChargingStation.Status.OFFLINE,
            }
        )

        # Update station info from BootNotification payload
        update_fields = {
            'vendor_name': payload.get('chargePointVendor', ''),
            'model': payload.get('chargePointModel', ''),
            'serial_number': payload.get('chargePointSerialNumber', ''),
            'firmware_version': payload.get('firmwareVersion', ''),
            'iccid': payload.get('iccid', ''),
            'imsi': payload.get('imsi', ''),
            'last_boot_at': timezone.now(),
        }

        # Determine response status
        if station.is_active:
            update_fields['status'] = ChargingStation.Status.AVAILABLE
            response_status = 'Accepted'
        else:
            response_status = 'Rejected'

        ChargingStation.objects.filter(station_id=station_id).update(**update_fields)

        # Get heartbeat interval (per-station or global)
        interval = int(CsmsVariable.get("heartbeat_interval", station_id=station_id, default=60))

        # Update Redis connected key with appropriate TTL
        r = get_redis()
        r.set(f"ocpp:connected:{station_id}", "1", ex=3600)

        # Build response
        response = {
            "currentTime": utcnow_iso(),
            "interval": interval,
            "status": response_status,
        }

        publish_response(msg_id, response)
        log_ocpp_message(station_id, msg_id, OcppMessage.Direction.OUTBOUND, 'BootNotification', response)

        logger.info(
            f"BootNotification from {station_id}: vendor={payload.get('chargePointVendor')} "
            f"model={payload.get('chargePointModel')} -> {response_status}"
        )

    except Exception as e:
        logger.exception(f"handle_boot_notification error for station={station_id}: {e}")
        publish_response(msg_id, {
            "currentTime": utcnow_iso(),
            "interval": 60,
            "status": "Accepted",  # Accept even on error to avoid CP going offline
        })


@shared_task(queue='ocpp.q.management', bind=True, max_retries=0, name='apps.ocpp16.tasks.management.handle_data_transfer')
def handle_data_transfer(self, station_id: str, msg_id: str, payload: dict):
    """
    Handle DataTransfer from charge point.
    Routes by vendorId and messageId for vendor-specific processing.
    """
    try:
        log_ocpp_message(station_id, msg_id, OcppMessage.Direction.INBOUND, 'DataTransfer', payload)

        vendor_id = payload.get('vendorId', '')
        message_id = payload.get('messageId', '')
        data = payload.get('data', '')

        logger.info(f"DataTransfer from {station_id}: vendor={vendor_id} msgId={message_id}")

        # Route by vendor ID
        # Add vendor-specific handlers here as needed
        # Example:
        # if vendor_id == 'com.example.vendor':
        #     result = handle_vendor_specific(message_id, data)
        #     response = {"status": "Accepted", "data": result}
        # else:
        #     response = {"status": "UnknownVendorId"}

        response = {"status": "UnknownVendorId"}

        publish_response(msg_id, response)
        log_ocpp_message(station_id, msg_id, OcppMessage.Direction.OUTBOUND, 'DataTransfer', response)

    except Exception as e:
        logger.exception(f"handle_data_transfer error for station={station_id}: {e}")
        publish_response(msg_id, {"status": "Rejected"})


@shared_task(queue='ocpp.q.management', bind=True, max_retries=0, name='apps.ocpp16.tasks.management.handle_firmware_status_notification')
def handle_firmware_status_notification(self, station_id: str, msg_id: str, payload: dict):
    """
    Handle FirmwareStatusNotification from charge point.
    Updates the firmware history record and station firmware version on success.
    """
    from apps.stations.models import ChargingStation, FirmwareHistory
    from apps.ocpp16.services.notification import NotificationService

    try:
        log_ocpp_message(station_id, msg_id, OcppMessage.Direction.INBOUND, 'FirmwareStatusNotification', payload)

        fw_status = payload.get('status', '')
        logger.info(f"FirmwareStatusNotification from {station_id}: status={fw_status}")

        # Find the latest firmware history record for this station
        try:
            fw_history = FirmwareHistory.objects.filter(
                charging_station__station_id=station_id
            ).latest('requested_at')

            # Map OCPP firmware status to our model status
            status_map = {
                'Downloaded': FirmwareHistory.Status.DOWNLOADED,
                'DownloadFailed': FirmwareHistory.Status.DOWNLOAD_FAILED,
                'Downloading': FirmwareHistory.Status.DOWNLOADING,
                'Idle': FirmwareHistory.Status.IDLE,
                'InstallationFailed': FirmwareHistory.Status.INSTALLATION_FAILED,
                'Installing': FirmwareHistory.Status.INSTALLING,
                'Installed': FirmwareHistory.Status.INSTALLED,
            }
            model_status = status_map.get(fw_status, FirmwareHistory.Status.IDLE)

            FirmwareHistory.objects.filter(pk=fw_history.pk).update(
                status=model_status,
                status_updated_at=timezone.now(),
            )

            # If installed: update station firmware version
            if fw_status == 'Installed':
                # Extract version from URL (simplified; ideally store version separately)
                fw_url = fw_history.firmware_url
                fw_version = fw_url.split('/')[-1] if '/' in fw_url else fw_url
                ChargingStation.objects.filter(station_id=station_id).update(
                    firmware_version=fw_version
                )
                logger.info(f"Firmware installed on {station_id}: {fw_version}")

            # Alert on failure
            if fw_status in ('DownloadFailed', 'InstallationFailed'):
                NotificationService.send_error_alert(station_id, 0, f'FirmwareStatus:{fw_status}')

        except FirmwareHistory.DoesNotExist:
            logger.warning(f"No firmware history found for {station_id}")

        # OCPP response is empty object
        publish_response(msg_id, {})
        log_ocpp_message(station_id, msg_id, OcppMessage.Direction.OUTBOUND, 'FirmwareStatusNotification', {})

    except Exception as e:
        logger.exception(f"handle_firmware_status_notification error for station={station_id}: {e}")
        publish_response(msg_id, {})


@shared_task(queue='ocpp.q.management', name='apps.ocpp16.tasks.management.cleanup_ocpp_messages')
def cleanup_ocpp_messages():
    """Delete OcppMessage records older than ocpp_message_log_retention_days (default 30 days)."""
    from apps.config.models import CsmsVariable
    retention_days = int(CsmsVariable.get('ocpp_message_log_retention_days', default=30))
    cutoff = timezone.now() - timezone.timedelta(days=retention_days)
    deleted, _ = OcppMessage.objects.filter(created_at__lt=cutoff).delete()
    logger.info(f"cleanup_ocpp_messages: deleted {deleted} records older than {retention_days} days")


@shared_task(queue='ocpp.q.management', bind=True, max_retries=0, name='apps.ocpp16.tasks.management.handle_diagnostics_status_notification')
def handle_diagnostics_status_notification(self, station_id: str, msg_id: str, payload: dict):
    """
    Handle DiagnosticsStatusNotification from charge point.
    Logs the diagnostics upload status.
    """
    try:
        log_ocpp_message(station_id, msg_id, OcppMessage.Direction.INBOUND, 'DiagnosticsStatusNotification', payload)

        diag_status = payload.get('status', '')
        logger.info(f"DiagnosticsStatusNotification from {station_id}: status={diag_status}")

        # OCPP response is empty object
        publish_response(msg_id, {})
        log_ocpp_message(station_id, msg_id, OcppMessage.Direction.OUTBOUND, 'DiagnosticsStatusNotification', {})

    except Exception as e:
        logger.exception(f"handle_diagnostics_status_notification error for station={station_id}: {e}")
        publish_response(msg_id, {})
