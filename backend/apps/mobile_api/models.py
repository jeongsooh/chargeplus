from django.db import models


class AppSession(models.Model):
    """
    Mobile app charging session.
    Lifecycle: pending → active → stopped (or failed)
    """

    class Status(models.TextChoices):
        PENDING  = 'pending',  'Pending'   # RemoteStart sent, waiting for EV connection
        ACTIVE   = 'active',   'Active'    # StartTransaction received, charging in progress
        FAILED   = 'failed',   'Failed'    # Timeout or EV not connected
        STOPPED  = 'stopped',  'Stopped'   # Charging complete (StopTransaction processed)

    # Primary key: composite key combining timestamp + station_id
    session_id       = models.CharField(max_length=80, unique=True, primary_key=True)

    user             = models.ForeignKey(
        'users.User',
        on_delete=models.PROTECT,
        related_name='app_sessions',
    )
    charging_station = models.ForeignKey(
        'stations.ChargingStation',
        on_delete=models.PROTECT,
        related_name='app_sessions',
    )
    connector_id     = models.PositiveSmallIntegerField(default=1)
    transaction      = models.OneToOneField(
        'transactions.Transaction',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='app_session',
    )

    class GoalType(models.TextChoices):
        TIME   = 'time',   'Time (minutes)'
        KWH    = 'kwh',    'Energy (kWh)'
        AMOUNT = 'amount', 'Amount (KRW)'
        FREE   = 'free',   'Free (no limit)'

    status           = models.CharField(
        max_length=10,
        choices=Status.choices,
        default=Status.PENDING,
    )
    fail_reason      = models.CharField(max_length=200, blank=True)

    # Charging goal (set at session creation)
    goal_type        = models.CharField(
        max_length=10,
        choices=GoalType.choices,
        default=GoalType.FREE,
    )
    goal_value       = models.DecimalField(
        max_digits=10, decimal_places=2, null=True, blank=True
    )

    # Real-time charging amount (updated by MeterValues)
    kwh_current      = models.DecimalField(max_digits=8, decimal_places=3, default=0)
    # Final settled values (set when status → stopped)
    final_kwh        = models.DecimalField(max_digits=8, decimal_places=3, null=True, blank=True)
    final_cost       = models.IntegerField(null=True, blank=True)  # KRW

    created_at       = models.DateTimeField(auto_now_add=True)
    updated_at       = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'cp_app_session'
        verbose_name = 'App Session'
        verbose_name_plural = 'App Sessions'
        indexes = [
            models.Index(fields=['user', '-created_at']),
            models.Index(fields=['charging_station', 'status']),
        ]
        ordering = ['-created_at']

    def __str__(self):
        return f"Session {self.session_id} ({self.status}) user={self.user_id}"
