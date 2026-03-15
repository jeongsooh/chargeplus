from django.db import models


class ChargingProfile(models.Model):
    """OCPP Charging Profile - defines power/current limits over time."""

    class Purpose(models.TextChoices):
        CHARGE_POINT_MAX = 'ChargePointMaxProfile', 'Charge Point Max Profile'
        TX_DEFAULT       = 'TxDefaultProfile',      'TX Default Profile'
        TX_PROFILE       = 'TxProfile',             'TX Profile'

    class Kind(models.TextChoices):
        ABSOLUTE  = 'Absolute',  'Absolute'
        RECURRING = 'Recurring', 'Recurring'
        RELATIVE  = 'Relative',  'Relative'

    class RecurrencyKind(models.TextChoices):
        DAILY  = 'Daily',  'Daily'
        WEEKLY = 'Weekly', 'Weekly'

    charging_station    = models.ForeignKey(
        'stations.ChargingStation',
        on_delete=models.CASCADE,
        related_name='charging_profiles',
    )
    connector_id        = models.PositiveSmallIntegerField(default=0)
    charging_profile_id = models.PositiveIntegerField()
    stack_level         = models.PositiveSmallIntegerField(default=0)
    profile_purpose     = models.CharField(max_length=30, choices=Purpose.choices)
    profile_kind        = models.CharField(max_length=20, choices=Kind.choices)
    recurrency_kind     = models.CharField(max_length=10, choices=RecurrencyKind.choices, blank=True)
    valid_from          = models.DateTimeField(null=True, blank=True)
    valid_to            = models.DateTimeField(null=True, blank=True)
    transaction         = models.ForeignKey(
        'transactions.Transaction',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='charging_profiles',
    )
    created_at          = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'cp_charging_profile'
        unique_together = ('charging_station', 'connector_id', 'stack_level', 'profile_purpose')
        verbose_name = 'Charging Profile'
        verbose_name_plural = 'Charging Profiles'

    def __str__(self):
        return f"{self.charging_station_id} Profile#{self.charging_profile_id} ({self.profile_purpose})"


class ChargingSchedule(models.Model):
    """Time-based power/current schedule within a charging profile."""

    class Unit(models.TextChoices):
        A = 'A', 'Amperes'
        W = 'W', 'Watts'

    profile            = models.OneToOneField(
        ChargingProfile,
        on_delete=models.CASCADE,
        related_name='schedule',
    )
    duration           = models.PositiveIntegerField(null=True, blank=True)  # seconds
    start_schedule     = models.DateTimeField(null=True, blank=True)
    charging_rate_unit = models.CharField(max_length=2, choices=Unit.choices)
    min_charging_rate  = models.DecimalField(max_digits=5, decimal_places=1, null=True, blank=True)
    # ChargingSchedulePeriod stored as JSON array
    schedule_periods   = models.JSONField(default=list)
    # [{"startPeriod": 0, "limit": 32.0, "numberPhases": 3}, ...]

    class Meta:
        db_table = 'cp_charging_schedule'
        verbose_name = 'Charging Schedule'
        verbose_name_plural = 'Charging Schedules'

    def __str__(self):
        return f"Schedule for Profile#{self.profile.charging_profile_id} ({self.charging_rate_unit})"
