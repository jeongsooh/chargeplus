from django.db import models


class IdToken(models.Model):
    """RFID card or app token (OCPP idTag)."""

    class Status(models.TextChoices):
        ACCEPTED      = 'Accepted',     'Accepted'
        BLOCKED       = 'Blocked',      'Blocked'
        EXPIRED       = 'Expired',      'Expired'
        INVALID       = 'Invalid',      'Invalid'
        CONCURRENT_TX = 'ConcurrentTx', 'Concurrent Transaction'

    class Type(models.TextChoices):
        RFID    = 'RFID',    'RFID Card'
        APP     = 'APP',     'Mobile App Token'
        ROAMING = 'ROAMING', 'Roaming Card'

    # OCPP idTag value - primary key
    id_token        = models.CharField(max_length=36, unique=True, primary_key=True)

    token_type      = models.CharField(
        max_length=10,
        choices=Type.choices,
        default=Type.RFID,
    )
    status          = models.CharField(
        max_length=20,
        choices=Status.choices,
        default=Status.INVALID,
    )
    expiry_date     = models.DateTimeField(null=True, blank=True)
    parent_id_token = models.CharField(max_length=36, blank=True)
    # Group card support (OCPP parentIdTag)

    user            = models.ForeignKey(
        'users.User',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='tokens',
    )
    operator        = models.ForeignKey(
        'stations.Operator',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
    )  # For roaming cards

    created_at      = models.DateTimeField(auto_now_add=True)
    updated_at      = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'cp_id_token'
        verbose_name = 'ID Token'
        verbose_name_plural = 'ID Tokens'

    def __str__(self):
        return f"{self.id_token} ({self.token_type}, {self.status})"


class AuthorizationRecord(models.Model):
    """Audit log of card authorization attempts."""

    charging_station = models.ForeignKey(
        'stations.ChargingStation',
        on_delete=models.PROTECT,
    )
    connector_id     = models.PositiveSmallIntegerField()
    id_token         = models.CharField(max_length=36)  # raw value (survives token deletion)
    status           = models.CharField(max_length=20)  # Authorize response status
    authorized_at    = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'cp_authorization_record'
        verbose_name = 'Authorization Record'
        verbose_name_plural = 'Authorization Records'
        ordering = ['-authorized_at']

    def __str__(self):
        return f"{self.id_token} on {self.charging_station_id} @ {self.authorized_at:%Y-%m-%d %H:%M} -> {self.status}"


class LocalAuthList(models.Model):
    """Local authorization list on a charging station (offline authorization)."""

    charging_station = models.ForeignKey(
        'stations.ChargingStation',
        on_delete=models.CASCADE,
        related_name='local_auth_list',
    )
    id_token         = models.CharField(max_length=36)
    id_tag_info      = models.JSONField()
    # {"status": "Accepted", "expiryDate": "...", "parentIdTag": "..."}
    list_version     = models.PositiveIntegerField(default=0)

    class Meta:
        db_table = 'cp_local_auth_list'
        unique_together = ('charging_station', 'id_token')
        verbose_name = 'Local Auth List Entry'
        verbose_name_plural = 'Local Auth List Entries'

    def __str__(self):
        return f"{self.charging_station_id} / {self.id_token} v{self.list_version}"
