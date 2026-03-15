from django.db import models


class Transaction(models.Model):
    """Charging transaction record."""

    class State(models.TextChoices):
        PENDING   = 'Pending',   'Pending'
        ACTIVE    = 'Active',    'Active'
        COMPLETED = 'Completed', 'Completed'
        FAILED    = 'Failed',    'Failed'

    class StopReason(models.TextChoices):
        DE_AUTHORIZED   = 'DeAuthorized',    'De-Authorized'
        EMERGENCY_STOP  = 'EmergencyStop',   'Emergency Stop'
        EV_DISCONNECTED = 'EVDisconnected',  'EV Disconnected'
        HARD_RESET      = 'HardReset',       'Hard Reset'
        LOCAL           = 'Local',           'Local'
        OTHER           = 'Other',           'Other'
        POWER_LOSS      = 'PowerLoss',       'Power Loss'
        REBOOT          = 'Reboot',          'Reboot'
        REMOTE          = 'Remote',          'Remote'
        SOFT_RESET      = 'SoftReset',       'Soft Reset'
        UNLOCK_COMMAND  = 'UnlockCommand',   'Unlock Command'

    # OCPP transaction_id (assigned by CSMS in StartTransaction response)
    transaction_id   = models.AutoField(primary_key=True)

    charging_station = models.ForeignKey(
        'stations.ChargingStation',
        on_delete=models.PROTECT,
        related_name='transactions',
    )
    connector        = models.ForeignKey(
        'stations.Connector',
        on_delete=models.PROTECT,
        related_name='transactions',
    )
    id_token         = models.ForeignKey(
        'authorization.IdToken',
        on_delete=models.PROTECT,
        related_name='transactions',
        null=True,
        blank=True,
    )

    state            = models.CharField(max_length=20, choices=State.choices, default=State.PENDING)

    # Timestamps
    time_start       = models.DateTimeField(null=True, blank=True)
    time_end         = models.DateTimeField(null=True, blank=True)

    # Meter readings in Wh
    meter_start      = models.BigIntegerField(default=0)
    meter_stop       = models.BigIntegerField(null=True, blank=True)

    # Calculated energy
    energy_kwh       = models.DecimalField(max_digits=8, decimal_places=3, null=True, blank=True)

    # Pricing
    unit_price       = models.DecimalField(max_digits=6, decimal_places=2, null=True, blank=True)  # KRW/kWh
    amount           = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True)  # total KRW

    # Stop info
    stop_reason      = models.CharField(max_length=30, choices=StopReason.choices, blank=True)

    # Payment
    payment_status   = models.CharField(max_length=20, default='pending')
    # pending / success / failed / refunded

    created_at       = models.DateTimeField(auto_now_add=True)
    updated_at       = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'cp_transaction'
        verbose_name = 'Transaction'
        verbose_name_plural = 'Transactions'
        indexes = [
            models.Index(fields=['charging_station', 'state']),
            models.Index(fields=['id_token', '-time_start']),
        ]
        ordering = ['-created_at']

    def __str__(self):
        return f"TX#{self.transaction_id} {self.charging_station_id} ({self.state})"


class MeterValue(models.Model):
    """Meter value measurement from a charging session."""

    class Measurand(models.TextChoices):
        ENERGY_ACTIVE_IMPORT = 'Energy.Active.Import.Register', 'Energy Active Import Register'
        POWER_ACTIVE_IMPORT  = 'Power.Active.Import',          'Power Active Import'
        CURRENT_IMPORT       = 'Current.Import',               'Current Import'
        VOLTAGE              = 'Voltage',                      'Voltage'
        SOC                  = 'SoC',                          'State of Charge'
        TEMPERATURE          = 'Temperature',                  'Temperature'
        FREQUENCY            = 'Frequency',                    'Frequency'

    class Unit(models.TextChoices):
        WH      = 'Wh',      'Wh'
        KWH     = 'kWh',     'kWh'
        W       = 'W',       'W'
        KW      = 'kW',      'kW'
        A       = 'A',       'A'
        V       = 'V',       'V'
        PCT     = 'Percent', 'Percent'
        CELSIUS = 'Celsius', 'Celsius'

    transaction = models.ForeignKey(
        Transaction,
        on_delete=models.CASCADE,
        related_name='meter_values',
    )
    timestamp   = models.DateTimeField(db_index=True)
    measurand   = models.CharField(
        max_length=50,
        choices=Measurand.choices,
        default=Measurand.ENERGY_ACTIVE_IMPORT,
    )
    phase       = models.CharField(max_length=10, blank=True)
    # L1, L2, L3, N, L1-N, L2-N, L3-N, L1-L2, L2-L3, L1-L3
    value       = models.DecimalField(max_digits=12, decimal_places=4)
    unit        = models.CharField(max_length=10, choices=Unit.choices, default=Unit.WH)
    context     = models.CharField(max_length=30, blank=True)
    # Sample.Periodic, Transaction.Begin, Transaction.End, etc.
    location    = models.CharField(max_length=20, blank=True)
    # Body, Cable, EV, Inlet, Outlet

    class Meta:
        db_table = 'cp_meter_value'
        verbose_name = 'Meter Value'
        verbose_name_plural = 'Meter Values'
        indexes = [
            models.Index(fields=['transaction', 'measurand', 'timestamp']),
        ]
        ordering = ['timestamp']

    def __str__(self):
        return f"TX#{self.transaction_id} {self.measurand}={self.value}{self.unit} @ {self.timestamp:%H:%M:%S}"
