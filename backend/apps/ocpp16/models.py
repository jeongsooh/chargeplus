from django.db import models


class OcppMessage(models.Model):
    """OCPP message audit log (all inbound and outbound messages)."""

    class Direction(models.IntegerChoices):
        INBOUND  = 2, 'CP → CSMS'
        OUTBOUND = 3, 'CSMS → CP'
        ERROR    = 4, 'Error'

    station_id  = models.CharField(max_length=50, db_index=True)
    msg_id      = models.CharField(max_length=36)
    direction   = models.SmallIntegerField(choices=Direction.choices)
    action      = models.CharField(max_length=50)
    payload     = models.JSONField()
    created_at  = models.DateTimeField(auto_now_add=True, db_index=True)

    class Meta:
        db_table = 'cp_ocpp_message'
        verbose_name = 'OCPP Message'
        verbose_name_plural = 'OCPP Messages'
        indexes = [
            models.Index(fields=['station_id', '-created_at']),
            models.Index(fields=['action', '-created_at']),
        ]
        ordering = ['-created_at']

    def __str__(self):
        direction_label = self.get_direction_display()
        return f"{self.station_id} {direction_label} {self.action} @ {self.created_at:%H:%M:%S}"
