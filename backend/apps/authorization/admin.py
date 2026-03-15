from django.contrib import admin

from .models import IdToken, AuthorizationRecord, LocalAuthList


@admin.register(IdToken)
class IdTokenAdmin(admin.ModelAdmin):
    list_display = ['id_token', 'token_type', 'status', 'user', 'operator', 'expiry_date', 'created_at']
    list_filter = ['status', 'token_type']
    search_fields = ['id_token', 'user__username', 'user__phone']
    raw_id_fields = ['user', 'operator']
    readonly_fields = ['created_at', 'updated_at']
    actions = ['block_tokens', 'accept_tokens']

    def block_tokens(self, request, queryset):
        updated = queryset.update(status=IdToken.Status.BLOCKED)
        self.message_user(request, f"{updated} token(s) blocked.")

    block_tokens.short_description = 'Block selected tokens'

    def accept_tokens(self, request, queryset):
        updated = queryset.update(status=IdToken.Status.ACCEPTED)
        self.message_user(request, f"{updated} token(s) accepted.")

    accept_tokens.short_description = 'Accept selected tokens'


@admin.register(AuthorizationRecord)
class AuthorizationRecordAdmin(admin.ModelAdmin):
    list_display = ['id_token', 'charging_station', 'connector_id', 'status', 'authorized_at']
    list_filter = ['status']
    search_fields = ['id_token', 'charging_station__station_id']
    readonly_fields = ['authorized_at']
    date_hierarchy = 'authorized_at'


@admin.register(LocalAuthList)
class LocalAuthListAdmin(admin.ModelAdmin):
    list_display = ['charging_station', 'id_token', 'list_version']
    search_fields = ['charging_station__station_id', 'id_token']
    list_filter = ['list_version']
