import logging

from celery import shared_task
from django.db import transaction as db_transaction
from django.utils import timezone

from apps.ocpp16.models import OcppMessage
from apps.ocpp16.utils import utcnow_iso, parse_ocpp_timestamp
from apps.ocpp16.services.authorization import AuthorizationService
from apps.ocpp16.services.pricing import PricingService
from apps.ocpp16.services.notification import NotificationService
from .base import publish_response, log_ocpp_message

logger = logging.getLogger(__name__)


@shared_task(queue='ocpp.q.core', bind=True, max_retries=0, name='apps.ocpp16.tasks.core.handle_authorize')
def handle_authorize(self, station_id: str, msg_id: str, payload: dict):
    """Handle Authorize request from charge point."""
    try:
        log_ocpp_message(station_id, msg_id, OcppMessage.Direction.INBOUND, 'Authorize', payload)

        id_tag = payload.get('idTag', '')
        result = AuthorizationService.authorize(station_id=station_id, id_tag=id_tag)

        response = {"idTagInfo": result}
        publish_response(msg_id, response)
        log_ocpp_message(station_id, msg_id, OcppMessage.Direction.OUTBOUND, 'Authorize', response)

    except Exception as e:
        logger.exception(f"handle_authorize error for station={station_id}: {e}")
        publish_response(msg_id, {"idTagInfo": {"status": "Invalid"}})


@shared_task(queue='ocpp.q.core', bind=True, max_retries=0, name='apps.ocpp16.tasks.core.handle_start_transaction')
def handle_start_transaction(self, station_id: str, msg_id: str, payload: dict):
    """
    Handle StartTransaction from charge point.
    Creates a Transaction record and links to AppSession if applicable.
    """
    from apps.stations.models import ChargingStation, Connector
    from apps.transactions.models import Transaction
    from apps.authorization.models import IdToken
    from apps.reservations.models import Reservation

    try:
        log_ocpp_message(station_id, msg_id, OcppMessage.Direction.INBOUND, 'StartTransaction', payload)

        connector_id = payload.get('connectorId', 1)
        id_tag = payload.get('idTag', '')
        meter_start = payload.get('meterStart', 0)
        timestamp_str = payload.get('timestamp', utcnow_iso())
        reservation_id = payload.get('reservationId', 0)

        try:
            time_start = parse_ocpp_timestamp(timestamp_str)
        except ValueError:
            time_start = timezone.now()

        # Authorize the idTag first
        auth_result = AuthorizationService.authorize(station_id=station_id, id_tag=id_tag, connector_id=connector_id)

        # If not accepted, respond immediately without creating a transaction
        if auth_result.get('status') not in ('Accepted', 'ConcurrentTx'):
            logger.info(
                f"StartTransaction rejected: station={station_id} idTag={id_tag} status={auth_result.get('status')}"
            )
            publish_response(msg_id, {"transactionId": -1, "idTagInfo": auth_result})
            return

        try:
            station = ChargingStation.objects.get(station_id=station_id)
        except ChargingStation.DoesNotExist:
            logger.error(f"StartTransaction: station {station_id} not found")
            publish_response(msg_id, {"transactionId": -1, "idTagInfo": {"status": "Invalid"}})
            return

        # Auto-provision EVSE/Connector if first time seen (OCPP 1.6: no EVSE in messages)
        from apps.stations.models import EVSE
        evse, _ = EVSE.objects.get_or_create(
            charging_station=station,
            evse_id=1,
        )
        connector, conn_created = Connector.objects.get_or_create(
            evse=evse,
            connector_id=connector_id,
            defaults={'current_status': Connector.Status.PREPARING},
        )
        if conn_created:
            logger.info(f"StartTransaction: auto-created connector {connector_id} for {station_id}")

        # Get IdToken object (may be None for roaming/anonymous)
        id_token_obj = None
        try:
            id_token_obj = IdToken.objects.get(id_token=id_tag)
        except IdToken.DoesNotExist:
            pass

        with db_transaction.atomic():
            # Create transaction
            tx = Transaction.objects.create(
                charging_station=station,
                connector=connector,
                id_token=id_token_obj,
                state=Transaction.State.ACTIVE,
                time_start=time_start,
                meter_start=meter_start,
            )

            # Update connector status to Charging
            Connector.objects.filter(pk=connector.pk).update(
                current_status=Connector.Status.CHARGING,
                status_updated_at=timezone.now(),
            )

            # Handle reservation cancellation
            if reservation_id and reservation_id > 0:
                try:
                    Reservation.objects.filter(
                        reservation_id=reservation_id,
                        charging_station=station,
                        status=Reservation.Status.ACTIVE,
                    ).update(status=Reservation.Status.USED)
                except Exception as e:
                    logger.warning(f"Could not update reservation {reservation_id}: {e}")

            # Link to AppSession if this is an app-initiated charge (idTag starts with APP-)
            if id_tag.startswith('APP-'):
                try:
                    from apps.mobile_api.models import AppSession
                    app_session = AppSession.objects.filter(
                        charging_station=station,
                        connector_id=connector_id,
                        status=AppSession.Status.PENDING,
                    ).first()
                    if app_session:
                        app_session.transaction = tx
                        app_session.status = AppSession.Status.ACTIVE
                        app_session.save(update_fields=['transaction', 'status', 'updated_at'])
                        logger.info(f"Linked AppSession {app_session.session_id} to TX#{tx.transaction_id}")
                except Exception as e:
                    logger.error(f"Error linking AppSession: {e}")

        response = {
            "transactionId": tx.transaction_id,
            "idTagInfo": auth_result,
        }
        publish_response(msg_id, response)
        log_ocpp_message(station_id, msg_id, OcppMessage.Direction.OUTBOUND, 'StartTransaction', response)

        logger.info(
            f"StartTransaction: station={station_id} connector={connector_id} "
            f"idTag={id_tag} TX#{tx.transaction_id} meterStart={meter_start}"
        )

    except Exception as e:
        logger.exception(f"handle_start_transaction error for station={station_id}: {e}")
        publish_response(msg_id, {"transactionId": -1, "idTagInfo": {"status": "Invalid"}})


@shared_task(queue='ocpp.q.core', bind=True, max_retries=0, name='apps.ocpp16.tasks.core.handle_stop_transaction')
def handle_stop_transaction(self, station_id: str, msg_id: str, payload: dict):
    """
    Handle StopTransaction from charge point.
    Completes the transaction, calculates energy/cost, updates connector status,
    links to AppSession and sends notifications.
    """
    from apps.transactions.models import Transaction, MeterValue
    from apps.stations.models import Connector
    from decimal import Decimal

    try:
        log_ocpp_message(station_id, msg_id, OcppMessage.Direction.INBOUND, 'StopTransaction', payload)

        transaction_id = payload.get('transactionId')
        meter_stop = payload.get('meterStop', 0)
        timestamp_str = payload.get('timestamp', utcnow_iso())
        stop_reason = payload.get('reason', 'Other')
        transaction_data = payload.get('transactionData', [])
        id_tag = payload.get('idTag', '')

        try:
            time_end = parse_ocpp_timestamp(timestamp_str)
        except ValueError:
            time_end = timezone.now()

        with db_transaction.atomic():
            try:
                tx = Transaction.objects.select_for_update().get(
                    transaction_id=transaction_id,
                    state=Transaction.State.ACTIVE,
                )
            except Transaction.DoesNotExist:
                logger.error(f"StopTransaction: TX#{transaction_id} not found or not active")
                publish_response(msg_id, {"idTagInfo": {"status": "Accepted"}})
                return

            # Calculate energy
            energy_wh = meter_stop - tx.meter_start
            energy_kwh = max(0.0, energy_wh / 1000.0)

            # Calculate cost
            cost = PricingService.calculate(station_id, energy_kwh)

            # Get unit price that was applied
            from apps.config.models import CsmsVariable
            unit_price = CsmsVariable.get("default_unit_price", station_id=station_id, default=270)

            # Update transaction
            tx.meter_stop = meter_stop
            tx.time_end = time_end
            tx.stop_reason = stop_reason if stop_reason in [r.value for r in Transaction.StopReason] else 'Other'
            tx.state = Transaction.State.COMPLETED
            tx.energy_kwh = Decimal(str(round(energy_kwh, 3)))
            tx.unit_price = Decimal(str(unit_price))
            tx.amount = Decimal(str(cost))
            tx.save(update_fields=[
                'meter_stop', 'time_end', 'stop_reason', 'state',
                'energy_kwh', 'unit_price', 'amount', 'updated_at'
            ])

            # Update connector status to Finishing
            Connector.objects.filter(
                evse__charging_station__station_id=station_id,
                connector_id=tx.connector.connector_id,
            ).update(
                current_status=Connector.Status.FINISHING,
                status_updated_at=timezone.now(),
            )

        # Process transactionData meter values (outside atomic to avoid long transactions)
        if transactionData := payload.get('transactionData', []):
            meter_value_objects = []
            for mv_entry in transactionData:
                ts_str = mv_entry.get('timestamp', '')
                sampled_values = mv_entry.get('sampledValue', [])
                try:
                    timestamp = parse_ocpp_timestamp(ts_str)
                except ValueError:
                    timestamp = time_end

                for sv in sampled_values:
                    measurand = sv.get('measurand', 'Energy.Active.Import.Register')
                    value_str = sv.get('value', '0')
                    unit = sv.get('unit', 'Wh')
                    try:
                        value = Decimal(str(value_str))
                        meter_value_objects.append(MeterValue(
                            transaction=tx,
                            timestamp=timestamp,
                            measurand=measurand,
                            phase=sv.get('phase', ''),
                            value=value,
                            unit=unit,
                            context=sv.get('context', 'Transaction.End'),
                            location=sv.get('location', ''),
                        ))
                    except Exception:
                        pass

            if meter_value_objects:
                MeterValue.objects.bulk_create(meter_value_objects, ignore_conflicts=True)

        # Update AppSession
        app_session = None
        try:
            from apps.mobile_api.models import AppSession
            app_session = AppSession.objects.filter(transaction=tx).first()
            if app_session:
                AppSession.objects.filter(pk=app_session.pk).update(
                    status=AppSession.Status.STOPPED,
                    final_kwh=tx.energy_kwh,
                    final_cost=cost,
                    updated_at=timezone.now(),
                )
        except Exception as e:
            logger.error(f"Error updating AppSession for TX#{transaction_id}: {e}")

        # Send charge complete notification
        if app_session:
            try:
                user_phone = app_session.user.phone if app_session.user else ''
                if user_phone:
                    NotificationService.send_charge_complete(
                        user_phone=user_phone,
                        kwh=float(tx.energy_kwh),
                        cost=cost,
                        station_id=station_id,
                    )
            except Exception as e:
                logger.error(f"Error sending charge complete notification: {e}")

        response = {"idTagInfo": {"status": "Accepted"}}
        publish_response(msg_id, response)
        log_ocpp_message(station_id, msg_id, OcppMessage.Direction.OUTBOUND, 'StopTransaction', response)

        logger.info(
            f"StopTransaction: station={station_id} TX#{transaction_id} "
            f"energy={energy_kwh:.3f}kWh cost={cost}KRW reason={stop_reason}"
        )

    except Exception as e:
        logger.exception(f"handle_stop_transaction error for station={station_id}: {e}")
        publish_response(msg_id, {"idTagInfo": {"status": "Accepted"}})


@shared_task(queue='ocpp.q.core', bind=True, max_retries=0, name='apps.ocpp16.tasks.core.check_pending_session_timeout')
def check_pending_session_timeout(self, session_id: str):
    """
    Check if an AppSession has been in pending state too long.
    If so, mark it as failed.
    Called via Celery countdown after RemoteStartTransaction.
    """
    from apps.mobile_api.models import AppSession

    try:
        session = AppSession.objects.get(session_id=session_id, status=AppSession.Status.PENDING)
        session.status = AppSession.Status.FAILED
        session.fail_reason = '차량이 연결되지 않았습니다.'
        session.save(update_fields=['status', 'fail_reason', 'updated_at'])
        logger.info(f"AppSession {session_id} timed out -> failed")
    except AppSession.DoesNotExist:
        # Session already active or completed; this is normal
        logger.debug(f"AppSession {session_id} not in pending state (already progressed)")
    except Exception as e:
        logger.error(f"check_pending_session_timeout error for {session_id}: {e}")
