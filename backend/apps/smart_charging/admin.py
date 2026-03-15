from django.contrib import admin

from .models import ChargingProfile, ChargingSchedule


class ChargingScheduleInline(admin.StackedInline):
    model = ChargingSchedule
    extra = 0


@admin.register(ChargingProfile)
class ChargingProfileAdmin(admin.ModelAdmin):
    list_display = [
        'charging_profile_id', 'charging_station', 'connector_id',
        'profile_purpose', 'profile_kind', 'stack_level', 'valid_from', 'valid_to',
    ]
    list_filter = ['profile_purpose', 'profile_kind']
    search_fields = ['charging_station__station_id']
    inlines = [ChargingScheduleInline]


@admin.register(ChargingSchedule)
class ChargingScheduleAdmin(admin.ModelAdmin):
    list_display = ['profile', 'charging_rate_unit', 'duration', 'start_schedule']
