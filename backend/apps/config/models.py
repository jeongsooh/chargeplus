import json
from django.db import models


class CsmsVariable(models.Model):
    """
    CSMS system configuration variable.
    Administrators can edit these via Django Admin.
    All service-layer logic reads settings through CsmsVariable.get().
    Per-station overrides are applied via StationVariable.
    """

    class ValueType(models.TextChoices):
        INT   = 'int',   'Integer'
        FLOAT = 'float', 'Float'
        STR   = 'str',   'String'
        BOOL  = 'bool',  'Boolean'
        JSON  = 'json',  'JSON'

    key            = models.CharField(max_length=100, unique=True)
    value          = models.TextField()
    value_type     = models.CharField(
        max_length=10,
        choices=ValueType.choices,
        default=ValueType.STR,
    )
    description    = models.TextField(blank=True)
    is_per_station = models.BooleanField(
        default=False,
        help_text="Whether this variable can be overridden per charging station via StationVariable",
    )
    updated_at     = models.DateTimeField(auto_now=True)
    updated_by     = models.CharField(max_length=50, blank=True)

    class Meta:
        db_table = 'cp_csms_variable'
        ordering = ['key']
        verbose_name = 'CSMS Variable'
        verbose_name_plural = 'CSMS Variables'

    def __str__(self):
        return f"{self.key}={self.value} ({self.value_type})"

    def get_typed_value(self):
        """Return value converted to the appropriate Python type."""
        if self.value_type == 'int':
            return int(self.value)
        if self.value_type == 'float':
            return float(self.value)
        if self.value_type == 'bool':
            return self.value.strip().lower() in ('true', '1', 'yes')
        if self.value_type == 'json':
            return json.loads(self.value)
        return self.value  # str

    @classmethod
    def get(cls, key: str, station_id: str = None, default=None):
        """
        Retrieve a configuration value with optional per-station override.

        Priority: StationVariable (if station_id provided) > CsmsVariable > default

        Results are cached in Django cache (TTL: 60 seconds).
        """
        from django.core.cache import cache

        cache_key = f"csmsvar:{key}:{station_id or 'global'}"
        cached = cache.get(cache_key)
        if cached is not None:
            return cached

        # Check per-station override
        if station_id:
            try:
                sv = StationVariable.objects.select_related('csms_variable').get(
                    charging_station__station_id=station_id,
                    csms_variable__key=key,
                )
                result = sv.get_typed_value()
                cache.set(cache_key, result, timeout=60)
                return result
            except StationVariable.DoesNotExist:
                pass

        # Global default
        try:
            var = cls.objects.get(key=key)
            result = var.get_typed_value()
            cache.set(cache_key, result, timeout=60)
            return result
        except cls.DoesNotExist:
            return default


class StationVariable(models.Model):
    """Per-station override of a CsmsVariable."""

    charging_station = models.ForeignKey(
        'stations.ChargingStation',
        on_delete=models.CASCADE,
        related_name='station_variables',
    )
    csms_variable    = models.ForeignKey(
        CsmsVariable,
        on_delete=models.CASCADE,
        related_name='station_overrides',
    )
    value            = models.TextField()
    updated_at       = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'cp_station_variable'
        unique_together = ('charging_station', 'csms_variable')
        verbose_name = 'Station Variable'
        verbose_name_plural = 'Station Variables'

    def __str__(self):
        return f"{self.charging_station_id} / {self.csms_variable.key}={self.value}"

    def get_typed_value(self):
        """Return value converted using the parent CsmsVariable's type."""
        vtype = self.csms_variable.value_type
        if vtype == 'int':
            return int(self.value)
        if vtype == 'float':
            return float(self.value)
        if vtype == 'bool':
            return self.value.strip().lower() in ('true', '1', 'yes')
        if vtype == 'json':
            return json.loads(self.value)
        return self.value
