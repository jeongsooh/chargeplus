from django.contrib import admin

from .models import Transaction, MeterValue


class MeterValueInline(admin.TabularInline):
    model = MeterValue
    extra = 0
    fields = ['timestamp', 'measurand', 'value', 'unit', 'context']
    readonly_fields = ['timestamp', 'measurand', 'value', 'unit', 'context']
    max_num = 50  # Limit inline display

    def has_add_permission(self, request, obj=None):
        return False


@admin.register(Transaction)
class TransactionAdmin(admin.ModelAdmin):
    list_display = [
        'transaction_id', 'charging_station', 'connector', 'id_token',
        'state', 'time_start', 'time_end', 'energy_kwh', 'amount', 'payment_status',
    ]
    list_filter = ['state', 'payment_status', 'charging_station']
    search_fields = ['transaction_id', 'charging_station__station_id', 'id_token__id_token']
    readonly_fields = [
        'transaction_id', 'meter_start', 'meter_stop', 'energy_kwh',
        'time_start', 'time_end', 'created_at', 'updated_at',
    ]
    date_hierarchy = 'time_start'
    inlines = [MeterValueInline]

    def has_add_permission(self, request):
        return False


@admin.register(MeterValue)
class MeterValueAdmin(admin.ModelAdmin):
    list_display = ['transaction', 'timestamp', 'measurand', 'value', 'unit', 'context']
    list_filter = ['measurand', 'unit']
    search_fields = ['transaction__transaction_id']
    readonly_fields = ['timestamp']
    date_hierarchy = 'timestamp'

    def has_add_permission(self, request):
        return False
