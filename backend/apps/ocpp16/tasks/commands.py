import logging

from celery import shared_task

from apps.ocpp16.models import OcppMessage
from .base import log_ocpp_message

logger = logging.getLogger(__name__)


@shared_task(queue='ocpp.q.commands', bind=True, max_retries=0, name='apps.ocpp16.tasks.commands.process_command_result')
def process_command_result(self, station_id: str, msg_id: str, action: str, payload: dict):
    """
    Process the result of a CSMS → CP command.
    Called after the charge point responds to a downstream command.
    Handles post-processing like updating DeviceConfiguration from GetConfiguration.
    """
    try:
        log_ocpp_message(station_id, msg_id, OcppMessage.Direction.OUTBOUND, f'{action}Response', payload)

        if action == 'GetConfiguration':
            _handle_get_configuration_result(station_id, payload)

        elif action == 'ChangeConfiguration':
            _handle_change_configuration_result(station_id, payload)

        elif action == 'Reset':
            logger.info(f"Reset result for {station_id}: {payload.get('status')}")

        elif action == 'ClearCache':
            logger.info(f"ClearCache result for {station_id}: {payload.get('status')}")

        elif action == 'RemoteStartTransaction':
            _handle_remote_start_result(station_id, msg_id, payload)

        elif action == 'RemoteStopTransaction':
            logger.info(f"RemoteStopTransaction result for {station_id}: {payload.get('status')}")

        elif action == 'UnlockConnector':
            logger.info(f"UnlockConnector result for {station_id}: {payload.get('status')}")

        else:
            logger.info(f"Command result {action} for {station_id}: {payload}")

    except Exception as e:
        logger.exception(f"process_command_result error for station={station_id} action={action}: {e}")


def _handle_get_configuration_result(station_id: str, payload: dict):
    """
    Update DeviceConfiguration records from GetConfiguration response.
    Bulk upsert configuration key-value pairs.
    """
    from apps.stations.models import ChargingStation, DeviceConfiguration

    try:
        station = ChargingStation.objects.get(station_id=station_id)
    except ChargingStation.DoesNotExist:
        logger.warning(f"GetConfiguration: station {station_id} not found")
        return

    config_keys = payload.get('configurationKey', [])
    if not config_keys:
        logger.info(f"GetConfiguration for {station_id}: no configuration keys returned")
        return

    upserted = 0
    for item in config_keys:
        key = item.get('key', '')
        value = item.get('value', '')
        readonly = item.get('readonly', False)

        if not key:
            continue

        try:
            DeviceConfiguration.objects.update_or_create(
                charging_station=station,
                key=key,
                defaults={
                    'value': value,
                    'is_readonly': readonly,
                }
            )
            upserted += 1
        except Exception as e:
            logger.error(f"Error upserting DeviceConfiguration {key} for {station_id}: {e}")

    logger.info(f"GetConfiguration for {station_id}: upserted {upserted} configuration keys")


def _handle_change_configuration_result(station_id: str, payload: dict):
    """Log the ChangeConfiguration result."""
    result_status = payload.get('status', 'Unknown')
    logger.info(f"ChangeConfiguration result for {station_id}: {result_status}")


def _handle_remote_start_result(station_id: str, msg_id: str, payload: dict):
    """Log the RemoteStartTransaction result."""
    result_status = payload.get('status', 'Unknown')
    logger.info(f"RemoteStartTransaction result for {station_id}: {result_status}")

    if result_status == 'Rejected':
        # If remote start was rejected, we may need to mark any pending AppSession as failed
        # However, we don't have session_id here; the mobile_api view handles this via timeout
        logger.warning(f"RemoteStartTransaction REJECTED for {station_id}")
