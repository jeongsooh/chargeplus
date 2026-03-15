from rest_framework import serializers

from .models import IdToken, AuthorizationRecord


class IdTokenSerializer(serializers.ModelSerializer):
    user_name = serializers.SerializerMethodField()

    class Meta:
        model = IdToken
        fields = [
            'id_token', 'token_type', 'status', 'expiry_date',
            'parent_id_token', 'user', 'user_name', 'operator',
            'created_at', 'updated_at',
        ]
        read_only_fields = ['created_at', 'updated_at']

    def get_user_name(self, obj):
        if obj.user:
            return obj.user.username
        return None


class AuthorizationRecordSerializer(serializers.ModelSerializer):
    class Meta:
        model = AuthorizationRecord
        fields = [
            'id', 'charging_station', 'connector_id',
            'id_token', 'status', 'authorized_at',
        ]
        read_only_fields = ['authorized_at']
