import logging

from apps.config.models import CsmsVariable

logger = logging.getLogger(__name__)


class PricingService:
    """Calculates charging fees based on energy consumed."""

    @staticmethod
    def calculate(station_id: str, energy_kwh: float) -> int:
        """
        Calculate charging cost in KRW.

        Priority:
          1. Prefix-based override (unit_price_overrides JSON variable)
          2. Per-station price (StationVariable override of default_unit_price)
          3. Global default price (default_unit_price)

        Args:
            station_id: Charging station identifier
            energy_kwh: Energy consumed in kWh

        Returns:
            int: Total cost in KRW
        """
        if energy_kwh <= 0:
            return 0

        # 1. Check prefix-based overrides
        overrides = CsmsVariable.get("unit_price_overrides", default={})
        if isinstance(overrides, dict):
            for prefix, price in overrides.items():
                if station_id.startswith(prefix):
                    cost = int(energy_kwh * int(price))
                    logger.debug(
                        f"Pricing: station={station_id} prefix={prefix} "
                        f"price={price} energy={energy_kwh}kWh cost={cost}KRW"
                    )
                    return cost

        # 2. Station-level override or global default
        unit_price = CsmsVariable.get("default_unit_price", station_id=station_id, default=270)
        cost = int(energy_kwh * int(unit_price))
        logger.debug(
            f"Pricing: station={station_id} price={unit_price} "
            f"energy={energy_kwh}kWh cost={cost}KRW"
        )
        return cost
