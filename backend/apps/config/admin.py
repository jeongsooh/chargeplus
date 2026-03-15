from django.contrib import admin

from .models import CsmsVariable, StationVariable


@admin.register(CsmsVariable)
class CsmsVariableAdmin(admin.ModelAdmin):
    list_display = ['key', 'value', 'value_type', 'is_per_station', 'description', 'updated_at', 'updated_by']
    readonly_fields = ['updated_at', 'updated_by']
    search_fields = ['key', 'description']
    list_filter = ['value_type', 'is_per_station']
    ordering = ['key']

    def save_model(self, request, obj, form, change):
        obj.updated_by = request.user.username
        super().save_model(request, obj, form, change)
        # Invalidate cache for this key
        from django.core.cache import cache
        cache.delete(f"csmsvar:{obj.key}:global")
        # Also remove station-specific caches using delete_many pattern
        # Since we can't do pattern delete easily, we rely on TTL expiry for station caches


@admin.register(StationVariable)
class StationVariableAdmin(admin.ModelAdmin):
    list_display = ['charging_station', 'csms_variable', 'value', 'updated_at']
    list_filter = ['csms_variable']
    search_fields = ['charging_station__station_id', 'csms_variable__key']
    raw_id_fields = ['charging_station', 'csms_variable']

    def save_model(self, request, obj, form, change):
        super().save_model(request, obj, form, change)
        # Invalidate station-specific cache
        from django.core.cache import cache
        cache.delete(f"csmsvar:{obj.csms_variable.key}:{obj.charging_station.station_id}")
