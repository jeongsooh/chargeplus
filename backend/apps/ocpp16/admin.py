import json

from django.contrib import admin
from django.utils.html import format_html

from .models import OcppMessage


@admin.register(OcppMessage)
class OcppMessageAdmin(admin.ModelAdmin):
    list_display = ['created_at', 'station_id', 'direction', 'action', 'msg_id']
    list_filter = ['direction', 'action']
    search_fields = ['station_id', 'action', 'msg_id']
    readonly_fields = ['station_id', 'msg_id', 'direction', 'action', 'payload_pretty', 'created_at']
    date_hierarchy = 'created_at'
    ordering = ['-created_at']

    def payload_pretty(self, obj):
        """Display JSON payload with formatting."""
        try:
            formatted = json.dumps(obj.payload, indent=2, ensure_ascii=False)
            return format_html('<pre style="font-size:11px">{}</pre>', formatted)
        except Exception:
            return str(obj.payload)

    payload_pretty.short_description = 'Payload'

    def get_fields(self, request, obj=None):
        return ['station_id', 'msg_id', 'direction', 'action', 'payload_pretty', 'created_at']

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False
