from rest_framework import serializers

from .models import Transaction, MeterValue


class MeterValueSerializer(serializers.ModelSerializer):
    class Meta:
        model = MeterValue
        fields = [
            'id', 'timestamp', 'measurand', 'phase',
            'value', 'unit', 'context', 'location',
        ]


class TransactionSerializer(serializers.ModelSerializer):
    meter_values = MeterValueSerializer(many=True, read_only=True)
    station_id = serializers.CharField(source='charging_station.station_id', read_only=True)
    connector_id = serializers.IntegerField(source='connector.connector_id', read_only=True)
    id_tag = serializers.CharField(source='id_token.id_token', read_only=True, allow_null=True)
    duration_seconds = serializers.SerializerMethodField()

    class Meta:
        model = Transaction
        fields = [
            'transaction_id', 'station_id', 'connector_id', 'id_tag',
            'state', 'time_start', 'time_end', 'duration_seconds',
            'meter_start', 'meter_stop', 'energy_kwh',
            'unit_price', 'amount', 'payment_status',
            'stop_reason', 'created_at', 'updated_at',
            'meter_values',
        ]

    def get_duration_seconds(self, obj):
        if obj.time_start and obj.time_end:
            return int((obj.time_end - obj.time_start).total_seconds())
        return None


class TransactionListSerializer(serializers.ModelSerializer):
    """Lightweight serializer for list view (no meter_values)."""
    station_id = serializers.CharField(source='charging_station.station_id', read_only=True)
    connector_id = serializers.IntegerField(source='connector.connector_id', read_only=True)
    id_tag = serializers.CharField(source='id_token.id_token', read_only=True, allow_null=True)

    class Meta:
        model = Transaction
        fields = [
            'transaction_id', 'station_id', 'connector_id', 'id_tag',
            'state', 'time_start', 'time_end',
            'energy_kwh', 'amount', 'payment_status',
            'stop_reason', 'created_at',
        ]
