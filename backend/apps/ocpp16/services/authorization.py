import logging

from apps.authorization.models import IdToken, AuthorizationRecord

logger = logging.getLogger(__name__)


class AuthorizationService:
    """Handles OCPP authorization logic."""

    @staticmethod
    def authorize(station_id: str, id_tag: str, connector_id: int = 0) -> dict:
        """
        Process an Authorize request and return idTagInfo dict.

        Checks:
          1. IdToken existence
          2. Expiry date
          3. Blocked status
          4. Concurrent active transaction check

        Returns:
            dict: OCPP idTagInfo (e.g., {"status": "Accepted", "expiryDate": "..."})
        """
        from apps.transactions.models import Transaction
        from apps.stations.models import ChargingStation
        from django.utils import timezone

        try:
            token = IdToken.objects.get(id_token=id_tag)
        except IdToken.DoesNotExist:
            logger.info(f"Authorization failed: id_tag={id_tag} not found")
            AuthorizationService._record_auth(station_id, connector_id, id_tag, 'Invalid')
            return {"status": "Invalid"}
        except IdToken.MultipleObjectsReturned:
            logger.error(f"Multiple IdToken records for id_tag={id_tag}")
            return {"status": "Blocked"}

        # Check expiry
        if token.expiry_date and token.expiry_date < timezone.now():
            status = "Expired"
        elif token.status == IdToken.Status.BLOCKED:
            status = "Blocked"
        elif token.status == IdToken.Status.ACCEPTED:
            # Check for concurrent active transaction
            active = Transaction.objects.filter(
                id_token=token,
                state=Transaction.State.ACTIVE,
            ).exists()
            status = "ConcurrentTx" if active else "Accepted"
        else:
            status = token.status

        AuthorizationService._record_auth(station_id, connector_id, id_tag, status)

        result = {"status": status}
        if token.expiry_date:
            result["expiryDate"] = token.expiry_date.strftime("%Y-%m-%dT%H:%M:%S.000Z")
        if token.parent_id_token:
            result["parentIdTag"] = token.parent_id_token

        logger.info(f"Authorization {id_tag} at {station_id}: {status}")
        return result

    @staticmethod
    def _record_auth(station_id: str, connector_id: int, id_tag: str, status: str) -> None:
        """Save an authorization audit record."""
        from apps.stations.models import ChargingStation
        try:
            station = ChargingStation.objects.get(station_id=station_id)
            AuthorizationRecord.objects.create(
                charging_station=station,
                connector_id=connector_id,
                id_token=id_tag,
                status=status,
            )
        except ChargingStation.DoesNotExist:
            logger.warning(f"Cannot record auth: station {station_id} not found")
        except Exception as e:
            logger.error(f"Failed to record authorization: {e}")
