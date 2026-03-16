from django.contrib import admin
from django.contrib.auth.admin import UserAdmin

from .models import User, PartnerProfile


@admin.register(User)
class CustomUserAdmin(UserAdmin):
    list_display = ['username', 'email', 'phone', 'role', 'status', 'first_name', 'is_staff', 'created_at']
    list_filter = ['role', 'status', 'is_staff', 'is_superuser']
    search_fields = ['username', 'email', 'phone', 'first_name', 'last_name']
    fieldsets = UserAdmin.fieldsets + (
        ('Portal', {'fields': ('phone', 'role', 'status')}),
    )
    add_fieldsets = UserAdmin.add_fieldsets + (
        ('Portal', {'fields': ('phone', 'role', 'status')}),
    )
    readonly_fields = ['created_at']


@admin.register(PartnerProfile)
class PartnerProfileAdmin(admin.ModelAdmin):
    list_display = ['business_name', 'business_no', 'user', 'contact_phone', 'created_at']
    search_fields = ['business_name', 'business_no', 'user__username']
    raw_id_fields = ['user']
