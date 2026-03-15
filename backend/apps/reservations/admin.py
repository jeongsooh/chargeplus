from django.contrib import admin

from .models import Reservation


@admin.register(Reservation)
class ReservationAdmin(admin.ModelAdmin):
    list_display = ['reservation_id', 'charging_station', 'connector', 'id_token', 'status', 'expiry_date', 'created_at']
    list_filter = ['status']
    search_fields = ['charging_station__station_id', 'id_token__id_token']
    readonly_fields = ['created_at']
