from django.db import models


class ChargingSite(models.Model):
    """Charging site (physical location) belonging to a partner."""
    partner    = models.ForeignKey(
        'users.PartnerProfile',
        on_delete=models.PROTECT,
        related_name='sites',
        verbose_name='파트너',
    )
    site_name  = models.CharField(max_length=100, verbose_name='충전소명')
    address    = models.CharField(max_length=200, blank=True, verbose_name='주소')
    unit_price = models.DecimalField(
        max_digits=8, decimal_places=2, default=0,
        verbose_name='충전단가(원/kWh)',
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'cp_charging_site'
        verbose_name = 'Charging Site'
        verbose_name_plural = 'Charging Sites'

    def __str__(self):
        return f"{self.site_name} ({self.partner.business_name})"


class Operator(models.Model):
    """Charging station operator (business entity)."""
    name       = models.CharField(max_length=100)
    code       = models.CharField(max_length=20, unique=True)  # e.g. EVN, KCC
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'cp_operator'
        verbose_name = 'Operator'
        verbose_name_plural = 'Operators'

    def __str__(self):
        return f"{self.name} ({self.code})"


class ChargingStation(models.Model):
    """Charging Station (Charge Point) - OCPP entity."""

    class Status(models.TextChoices):
        AVAILABLE   = 'Available',   'Available'
        UNAVAILABLE = 'Unavailable', 'Unavailable'
        FAULTED     = 'Faulted',     'Faulted'
        OFFLINE     = 'Offline',     'Offline'

    # OCPP chargePointIdentifier, used in URL path /{station_id}
    station_id      = models.CharField(max_length=50, unique=True)

    # Business owner
    operator        = models.ForeignKey(
        Operator,
        on_delete=models.PROTECT,
        related_name='stations',
    )

    # Charging site (physical location managed by a partner)
    site            = models.ForeignKey(
        ChargingSite,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='stations',
        verbose_name='충전소',
    )

    # Fields populated from BootNotification
    vendor_name     = models.CharField(max_length=50, blank=True)
    model           = models.CharField(max_length=50, blank=True)
    serial_number   = models.CharField(max_length=50, blank=True)
    firmware_version = models.CharField(max_length=50, blank=True)
    iccid           = models.CharField(max_length=50, blank=True)  # SIM card ID
    imsi            = models.CharField(max_length=50, blank=True)

    # Status
    status          = models.CharField(
        max_length=20,
        choices=Status.choices,
        default=Status.OFFLINE,
    )
    last_heartbeat  = models.DateTimeField(null=True, blank=True)
    last_boot_at    = models.DateTimeField(null=True, blank=True)

    # Location
    address         = models.CharField(max_length=200, blank=True)
    latitude        = models.DecimalField(max_digits=9, decimal_places=6, null=True, blank=True)
    longitude       = models.DecimalField(max_digits=9, decimal_places=6, null=True, blank=True)

    # Admin
    is_active       = models.BooleanField(default=True)
    note            = models.TextField(blank=True)
    created_at      = models.DateTimeField(auto_now_add=True)
    updated_at      = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'cp_charging_station'
        verbose_name = 'Charging Station'
        verbose_name_plural = 'Charging Stations'

    def __str__(self):
        return f"{self.station_id} ({self.status})"


class EVSE(models.Model):
    """EVSE (Electric Vehicle Supply Equipment) - charging unit within a station."""

    charging_station = models.ForeignKey(
        ChargingStation,
        on_delete=models.CASCADE,
        related_name='evses',
    )
    evse_id          = models.PositiveSmallIntegerField()

    class Meta:
        db_table = 'cp_evse'
        unique_together = ('charging_station', 'evse_id')
        verbose_name = 'EVSE'
        verbose_name_plural = 'EVSEs'

    def __str__(self):
        return f"{self.charging_station.station_id} / EVSE-{self.evse_id}"


class Connector(models.Model):
    """Individual connector/charging port (OCPP connectorId >= 1)."""

    class Status(models.TextChoices):
        AVAILABLE     = 'Available',     'Available'
        PREPARING     = 'Preparing',     'Preparing'
        CHARGING      = 'Charging',      'Charging'
        SUSPENDEDEVSE = 'SuspendedEVSE', 'Suspended EVSE'
        SUSPENDEDEV   = 'SuspendedEV',   'Suspended EV'
        FINISHING     = 'Finishing',     'Finishing'
        RESERVED      = 'Reserved',      'Reserved'
        UNAVAILABLE   = 'Unavailable',   'Unavailable'
        FAULTED       = 'Faulted',       'Faulted'

    class Type(models.TextChoices):
        TYPE1   = 'Type1',   'Type 1 (SAE J1772)'
        TYPE2   = 'Type2',   'Type 2 (IEC 62196)'
        CHADEMO = 'CHAdeMO', 'CHAdeMO'
        CCS1    = 'CCS1',    'CCS1'
        CCS2    = 'CCS2',    'CCS2'
        SCHUKO  = 'Schuko',  'Schuko'
        OTHER   = 'Other',   'Other'

    evse             = models.ForeignKey(
        EVSE,
        on_delete=models.CASCADE,
        related_name='connectors',
    )
    connector_id     = models.PositiveSmallIntegerField()
    # OCPP connectorId (1-based). 0 is reserved for station-wide status.

    connector_type   = models.CharField(max_length=20, choices=Type.choices, default=Type.TYPE2)
    max_power_kw     = models.DecimalField(max_digits=6, decimal_places=2, null=True, blank=True)
    current_status   = models.CharField(max_length=20, choices=Status.choices, default=Status.UNAVAILABLE)
    status_updated_at = models.DateTimeField(null=True, blank=True)
    error_code       = models.CharField(max_length=50, blank=True)
    info             = models.CharField(max_length=50, blank=True)
    vendor_id        = models.CharField(max_length=255, blank=True)
    vendor_error_code = models.CharField(max_length=50, blank=True)

    class Meta:
        db_table = 'cp_connector'
        unique_together = ('evse', 'connector_id')
        verbose_name = 'Connector'
        verbose_name_plural = 'Connectors'

    def __str__(self):
        return f"{self.evse.charging_station.station_id} / Connector-{self.connector_id} ({self.current_status})"


class DeviceConfiguration(models.Model):
    """Charging station configuration parameter (from GetConfiguration / ChangeConfiguration)."""

    charging_station = models.ForeignKey(
        ChargingStation,
        on_delete=models.CASCADE,
        related_name='configurations',
    )
    key              = models.CharField(max_length=50)
    value            = models.TextField(blank=True)
    is_readonly      = models.BooleanField(default=False)
    updated_at       = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'cp_device_configuration'
        unique_together = ('charging_station', 'key')
        verbose_name = 'Device Configuration'
        verbose_name_plural = 'Device Configurations'

    def __str__(self):
        return f"{self.charging_station.station_id} / {self.key}={self.value}"


class FaultLog(models.Model):
    """Manual fault history entry for a charging station."""

    class FaultType(models.TextChoices):
        CONNECTOR   = 'connector',    '커넥터 불량'
        COMM        = 'comm',         '통신 오류'
        POWER       = 'power',        '전원 불량'
        DISPLAY     = 'display',      '디스플레이 불량'
        OTHER       = 'other',        '기타'

    charging_station = models.ForeignKey(
        ChargingStation,
        on_delete=models.CASCADE,
        related_name='fault_logs',
        verbose_name='충전기',
    )
    reported_at      = models.DateTimeField(verbose_name='장애 발생 시각')
    fault_type       = models.CharField(max_length=20, choices=FaultType.choices, default=FaultType.OTHER)
    description      = models.TextField(verbose_name='장애 내용')
    resolved_at      = models.DateTimeField(null=True, blank=True, verbose_name='복구 시각')
    reported_by      = models.CharField(max_length=50, verbose_name='입력자')
    created_at       = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'cp_fault_log'
        verbose_name = 'Fault Log'
        verbose_name_plural = 'Fault Logs'
        ordering = ['-reported_at']

    def __str__(self):
        return f"{self.charging_station.station_id} {self.fault_type} @ {self.reported_at:%Y-%m-%d %H:%M}"


class FirmwareHistory(models.Model):
    """Firmware update history for a charging station."""

    class Status(models.TextChoices):
        DOWNLOADED          = 'Downloaded',         'Downloaded'
        DOWNLOAD_FAILED     = 'DownloadFailed',      'Download Failed'
        DOWNLOADING         = 'Downloading',         'Downloading'
        IDLE                = 'Idle',                'Idle'
        INSTALLATION_FAILED = 'InstallationFailed',  'Installation Failed'
        INSTALLING          = 'Installing',          'Installing'
        INSTALLED           = 'Installed',           'Installed'

    charging_station  = models.ForeignKey(
        ChargingStation,
        on_delete=models.CASCADE,
        related_name='firmware_history',
    )
    firmware_url      = models.URLField(max_length=512)
    retrieve_date     = models.DateTimeField()
    status            = models.CharField(max_length=30, choices=Status.choices, default=Status.IDLE)
    status_updated_at = models.DateTimeField(null=True, blank=True)
    requested_at      = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'cp_firmware_history'
        verbose_name = 'Firmware History'
        verbose_name_plural = 'Firmware Histories'
        ordering = ['-requested_at']

    def __str__(self):
        return f"{self.charging_station.station_id} / {self.status} ({self.requested_at:%Y-%m-%d})"
