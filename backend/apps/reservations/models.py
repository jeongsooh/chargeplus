from django.db import models


class Reservation(models.Model):
    """Charging slot reservation."""

    class Status(models.TextChoices):
        ACTIVE    = 'Active',    'Active'
        CANCELLED = 'Cancelled', 'Cancelled'
        EXPIRED   = 'Expired',   'Expired'
        USED      = 'Used',      'Used'
        FAILED    = 'Failed',    'Failed'  # ReserveNow rejected by CP

    reservation_id   = models.AutoField(primary_key=True)
    charging_station = models.ForeignKey(
        'stations.ChargingStation',
        on_delete=models.PROTECT,
        related_name='reservations',
    )
    connector        = models.ForeignKey(
        'stations.Connector',
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name='reservations',
    )
    id_token         = models.ForeignKey(
        'authorization.IdToken',
        on_delete=models.PROTECT,
        related_name='reservations',
    )
    expiry_date      = models.DateTimeField()
    status           = models.CharField(max_length=20, choices=Status.choices, default=Status.ACTIVE)
    created_at       = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'cp_reservation'
        verbose_name = 'Reservation'
        verbose_name_plural = 'Reservations'
        ordering = ['-created_at']

    def __str__(self):
        return f"Reservation#{self.reservation_id} {self.charging_station_id} ({self.status})"
