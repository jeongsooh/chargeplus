import logging

from django.contrib import admin
from django.utils import timezone

from .models import AppSession

logger = logging.getLogger(__name__)


@admin.register(AppSession)
class AppSessionAdmin(admin.ModelAdmin):
    list_display = [
        'session_id', 'user', 'charging_station', 'connector_id',
        'status', 'kwh_current', 'final_kwh', 'final_cost',
        'created_at', 'updated_at',
    ]
    list_filter = ['status', 'charging_station']
    search_fields = ['session_id', 'user__username', 'charging_station__station_id']
    readonly_fields = [
        'session_id', 'user', 'charging_station', 'connector_id',
        'transaction', 'kwh_current', 'final_kwh', 'final_cost',
        'created_at', 'updated_at',
    ]
    date_hierarchy = 'created_at'
    actions = ['force_stop_sessions']

    def force_stop_sessions(self, request, queryset):
        """Force-stop active or pending sessions."""
        from apps.ocpp16.services.gateway_client import GatewayClient

        stopped_count = 0
        failed_count = 0

        for session in queryset.filter(status__in=['pending', 'active']):
            try:
                if session.status == 'active' and session.transaction:
                    station_id = session.charging_station.station_id
                    if GatewayClient.is_station_connected(station_id):
                        GatewayClient.send_command_async(
                            station_id,
                            "RemoteStopTransaction",
                            {"transactionId": session.transaction.transaction_id},
                        )

                session.status = 'failed'
                session.fail_reason = f'관리자에 의해 강제 종료됨 ({request.user.username})'
                session.save(update_fields=['status', 'fail_reason', 'updated_at'])
                stopped_count += 1
            except Exception as e:
                logger.error(f"Force stop failed for session {session.session_id}: {e}")
                failed_count += 1

        self.message_user(
            request,
            f"Force-stopped {stopped_count} sessions. {failed_count} failed."
        )

    force_stop_sessions.short_description = 'Force stop selected sessions'

    def has_add_permission(self, request):
        return False
