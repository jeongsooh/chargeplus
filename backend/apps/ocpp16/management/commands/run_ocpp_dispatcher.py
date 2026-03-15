import json
import logging
import signal
import sys

from django.core.management.base import BaseCommand

logger = logging.getLogger(__name__)

# Map OCPP action names to Celery task functions and queues
ACTION_ROUTER = {
    "BootNotification": ("apps.ocpp16.tasks.management.handle_boot_notification", "ocpp.q.management"),
    "Heartbeat": ("apps.ocpp16.tasks.telemetry.handle_heartbeat", "ocpp.q.telemetry"),
    "StatusNotification": ("apps.ocpp16.tasks.telemetry.handle_status_notification", "ocpp.q.telemetry"),
    "Authorize": ("apps.ocpp16.tasks.core.handle_authorize", "ocpp.q.core"),
    "StartTransaction": ("apps.ocpp16.tasks.core.handle_start_transaction", "ocpp.q.core"),
    "StopTransaction": ("apps.ocpp16.tasks.core.handle_stop_transaction", "ocpp.q.core"),
    "MeterValues": ("apps.ocpp16.tasks.telemetry.handle_meter_values", "ocpp.q.telemetry"),
    "DataTransfer": ("apps.ocpp16.tasks.management.handle_data_transfer", "ocpp.q.management"),
    "FirmwareStatusNotification": ("apps.ocpp16.tasks.management.handle_firmware_status_notification", "ocpp.q.management"),
    "DiagnosticsStatusNotification": ("apps.ocpp16.tasks.management.handle_diagnostics_status_notification", "ocpp.q.management"),
}


class Command(BaseCommand):
    help = 'Consume OCPP upstream messages from Redis queue and dispatch to Celery workers'

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._running = True

    def add_arguments(self, parser):
        parser.add_argument(
            '--queue',
            type=str,
            default='ocpp:upstream',
            help='Redis queue key to consume from (default: ocpp:upstream)',
        )
        parser.add_argument(
            '--timeout',
            type=int,
            default=5,
            help='BRPOP timeout in seconds (default: 5)',
        )

    def handle(self, *args, **options):
        queue_key = options['queue']
        brpop_timeout = options['timeout']

        self.stdout.write(
            self.style.SUCCESS(f'Starting OCPP dispatcher on queue: {queue_key}')
        )

        # Setup graceful shutdown
        signal.signal(signal.SIGINT, self._handle_shutdown)
        signal.signal(signal.SIGTERM, self._handle_shutdown)

        from apps.ocpp16.redis_client import get_redis
        r = get_redis()

        # Import task functions lazily (after Django is set up)
        from apps.ocpp16.tasks.management import (
            handle_boot_notification, handle_data_transfer,
            handle_firmware_status_notification, handle_diagnostics_status_notification,
        )
        from apps.ocpp16.tasks.telemetry import (
            handle_heartbeat, handle_status_notification, handle_meter_values,
        )
        from apps.ocpp16.tasks.core import (
            handle_authorize, handle_start_transaction, handle_stop_transaction,
        )

        TASK_MAP = {
            "BootNotification": (handle_boot_notification, "ocpp.q.management"),
            "Heartbeat": (handle_heartbeat, "ocpp.q.telemetry"),
            "StatusNotification": (handle_status_notification, "ocpp.q.telemetry"),
            "Authorize": (handle_authorize, "ocpp.q.core"),
            "StartTransaction": (handle_start_transaction, "ocpp.q.core"),
            "StopTransaction": (handle_stop_transaction, "ocpp.q.core"),
            "MeterValues": (handle_meter_values, "ocpp.q.telemetry"),
            "DataTransfer": (handle_data_transfer, "ocpp.q.management"),
            "FirmwareStatusNotification": (handle_firmware_status_notification, "ocpp.q.management"),
            "DiagnosticsStatusNotification": (handle_diagnostics_status_notification, "ocpp.q.management"),
        }

        self.stdout.write(f'Dispatcher ready. Listening on {queue_key}...')
        message_count = 0

        while self._running:
            try:
                # BRPOP blocks up to `brpop_timeout` seconds
                result = r.brpop(queue_key, timeout=brpop_timeout)

                if result is None:
                    # Timeout with no message; loop again
                    continue

                _, raw = result

                try:
                    data = json.loads(raw)
                except json.JSONDecodeError as e:
                    logger.error(f"Dispatcher: invalid JSON in queue: {e} | raw={raw[:200]}")
                    continue

                action = data.get('action', '')
                station_id = data.get('station_id', '')
                msg_id = data.get('msg_id', '')
                payload = data.get('payload', {})

                if not action:
                    logger.warning(f"Dispatcher: message without action: {data}")
                    continue

                if action not in TASK_MAP:
                    logger.warning(f"Dispatcher: unknown action '{action}' from {station_id}")
                    # Publish error response so Gateway doesn't hang
                    self._publish_error_response(r, msg_id)
                    continue

                task_fn, queue = TASK_MAP[action]

                # Dispatch to Celery
                task_fn.apply_async(
                    args=[station_id, msg_id, payload],
                    queue=queue,
                )

                message_count += 1
                if message_count % 100 == 0:
                    self.stdout.write(f'Dispatcher: processed {message_count} messages')

                logger.debug(
                    f"Dispatcher: dispatched {action} from {station_id} "
                    f"(msg_id={msg_id}) to queue={queue}"
                )

            except KeyboardInterrupt:
                break
            except Exception as e:
                logger.error(f"Dispatcher error: {e}")
                # Brief pause to avoid tight error loops
                import time
                time.sleep(0.1)

        self.stdout.write(
            self.style.SUCCESS(
                f'Dispatcher stopped. Total messages processed: {message_count}'
            )
        )

    def _handle_shutdown(self, signum, frame):
        """Handle SIGINT/SIGTERM gracefully."""
        self.stdout.write(self.style.WARNING('Dispatcher: shutdown signal received'))
        self._running = False

    def _publish_error_response(self, r, msg_id: str):
        """Publish an error response for unknown actions so the Gateway doesn't hang."""
        import json
        try:
            r.publish(
                f"ocpp:response:{msg_id}",
                json.dumps({
                    "msg_id": msg_id,
                    "payload": {"error": "NotImplemented"},
                })
            )
        except Exception as e:
            logger.error(f"Failed to publish error response for msg_id={msg_id}: {e}")
