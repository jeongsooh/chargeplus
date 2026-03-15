import logging

from django.contrib import admin
from django.http import HttpResponseRedirect
from django.urls import reverse

from apps.config.models import StationVariable

from .models import (
    Operator, ChargingStation, EVSE, Connector,
    DeviceConfiguration, FirmwareHistory,
)

logger = logging.getLogger(__name__)


class ConnectorInline(admin.TabularInline):
    model = Connector
    extra = 0
    fields = ['connector_id', 'connector_type', 'max_power_kw', 'current_status', 'error_code']
    readonly_fields = ['current_status', 'error_code']


class EVSEInline(admin.TabularInline):
    model = EVSE
    extra = 0
    fields = ['evse_id']
    show_change_link = True


class DeviceConfigurationInline(admin.TabularInline):
    model = DeviceConfiguration
    extra = 0
    fields = ['key', 'value', 'is_readonly', 'updated_at']
    readonly_fields = ['updated_at']


class FirmwareHistoryInline(admin.TabularInline):
    model = FirmwareHistory
    extra = 0
    fields = ['firmware_url', 'status', 'requested_at', 'status_updated_at']
    readonly_fields = ['requested_at', 'status_updated_at']


class StationVariableInline(admin.TabularInline):
    model = StationVariable
    extra = 1
    fields = ['csms_variable', 'value', 'updated_at']
    readonly_fields = ['updated_at']

    def formfield_for_foreignkey(self, db_field, request, **kwargs):
        if db_field.name == 'csms_variable':
            from apps.config.models import CsmsVariable
            kwargs['queryset'] = CsmsVariable.objects.filter(is_per_station=True)
        return super().formfield_for_foreignkey(db_field, request, **kwargs)


@admin.register(Operator)
class OperatorAdmin(admin.ModelAdmin):
    list_display = ['name', 'code', 'created_at']
    search_fields = ['name', 'code']


@admin.register(ChargingStation)
class ChargingStationAdmin(admin.ModelAdmin):
    list_display = [
        'station_id', 'operator', 'status', 'vendor_name', 'model',
        'firmware_version', 'last_heartbeat', 'is_active',
    ]
    list_filter = ['status', 'operator', 'is_active']
    search_fields = ['station_id', 'vendor_name', 'serial_number', 'address']
    readonly_fields = ['last_heartbeat', 'last_boot_at', 'created_at', 'updated_at']
    inlines = [EVSEInline, DeviceConfigurationInline, FirmwareHistoryInline, StationVariableInline]
    actions = ['send_soft_reset', 'send_hard_reset', 'get_configuration']

    def send_soft_reset(self, request, queryset):
        from apps.ocpp16.services.gateway_client import GatewayClient
        success, failed = 0, 0
        for station in queryset:
            try:
                if GatewayClient.is_station_connected(station.station_id):
                    GatewayClient.send_command(station.station_id, 'Reset', {'type': 'Soft'}, timeout=10)
                    success += 1
                else:
                    failed += 1
            except Exception as e:
                logger.error(f"Soft reset failed for {station.station_id}: {e}")
                failed += 1
        self.message_user(request, f"Soft reset: {success} succeeded, {failed} failed/offline.")

    send_soft_reset.short_description = 'Send Soft Reset'

    def send_hard_reset(self, request, queryset):
        from apps.ocpp16.services.gateway_client import GatewayClient
        success, failed = 0, 0
        for station in queryset:
            try:
                if GatewayClient.is_station_connected(station.station_id):
                    GatewayClient.send_command(station.station_id, 'Reset', {'type': 'Hard'}, timeout=10)
                    success += 1
                else:
                    failed += 1
            except Exception as e:
                logger.error(f"Hard reset failed for {station.station_id}: {e}")
                failed += 1
        self.message_user(request, f"Hard reset: {success} succeeded, {failed} failed/offline.")

    send_hard_reset.short_description = 'Send Hard Reset'

    def get_configuration(self, request, queryset):
        from apps.ocpp16.services.gateway_client import GatewayClient
        success, failed = 0, 0
        for station in queryset:
            try:
                if GatewayClient.is_station_connected(station.station_id):
                    GatewayClient.send_command(station.station_id, 'GetConfiguration', {}, timeout=15)
                    success += 1
                else:
                    failed += 1
            except Exception as e:
                logger.error(f"GetConfiguration failed for {station.station_id}: {e}")
                failed += 1
        self.message_user(request, f"GetConfiguration: {success} succeeded, {failed} failed/offline.")

    get_configuration.short_description = 'Get Configuration'


@admin.register(EVSE)
class EVSEAdmin(admin.ModelAdmin):
    list_display = ['charging_station', 'evse_id']
    inlines = [ConnectorInline]


@admin.register(Connector)
class ConnectorAdmin(admin.ModelAdmin):
    list_display = [
        'get_station_id', 'connector_id', 'connector_type',
        'max_power_kw', 'current_status', 'error_code', 'status_updated_at',
    ]
    list_filter = ['current_status', 'connector_type']
    search_fields = ['evse__charging_station__station_id']

    def get_station_id(self, obj):
        return obj.evse.charging_station.station_id
    get_station_id.short_description = 'Station ID'


@admin.register(DeviceConfiguration)
class DeviceConfigurationAdmin(admin.ModelAdmin):
    list_display = ['charging_station', 'key', 'value', 'is_readonly', 'updated_at']
    list_filter = ['is_readonly']
    search_fields = ['charging_station__station_id', 'key']
    readonly_fields = ['updated_at']


@admin.register(FirmwareHistory)
class FirmwareHistoryAdmin(admin.ModelAdmin):
    list_display = ['charging_station', 'status', 'firmware_url', 'requested_at', 'status_updated_at']
    list_filter = ['status']
    search_fields = ['charging_station__station_id']
    readonly_fields = ['requested_at']
