from rest_framework import serializers

from .models import ChargingStation, EVSE, Connector, DeviceConfiguration, FirmwareHistory


class ConnectorSerializer(serializers.ModelSerializer):
    class Meta:
        model = Connector
        fields = [
            'connector_id', 'connector_type', 'max_power_kw',
            'current_status', 'status_updated_at', 'error_code',
        ]


class EVSESerializer(serializers.ModelSerializer):
    connectors = ConnectorSerializer(many=True, read_only=True)

    class Meta:
        model = EVSE
        fields = ['evse_id', 'connectors']


class DeviceConfigurationSerializer(serializers.ModelSerializer):
    class Meta:
        model = DeviceConfiguration
        fields = ['key', 'value', 'is_readonly', 'updated_at']


class FirmwareHistorySerializer(serializers.ModelSerializer):
    class Meta:
        model = FirmwareHistory
        fields = ['id', 'firmware_url', 'retrieve_date', 'status', 'status_updated_at', 'requested_at']


class ChargingStationSerializer(serializers.ModelSerializer):
    evses = EVSESerializer(many=True, read_only=True)
    operator_name = serializers.CharField(source='operator.name', read_only=True)

    class Meta:
        model = ChargingStation
        fields = [
            'station_id', 'operator', 'operator_name',
            'vendor_name', 'model', 'serial_number', 'firmware_version',
            'status', 'last_heartbeat', 'last_boot_at',
            'address', 'latitude', 'longitude',
            'is_active', 'note',
            'created_at', 'updated_at',
            'evses',
        ]
        read_only_fields = [
            'vendor_name', 'model', 'serial_number', 'firmware_version',
            'status', 'last_heartbeat', 'last_boot_at', 'created_at', 'updated_at',
        ]


class ChargingStationListSerializer(serializers.ModelSerializer):
    """Lightweight serializer for list view."""
    operator_name = serializers.CharField(source='operator.name', read_only=True)
    connector_count = serializers.SerializerMethodField()
    available_connectors = serializers.SerializerMethodField()

    class Meta:
        model = ChargingStation
        fields = [
            'station_id', 'operator', 'operator_name',
            'vendor_name', 'model', 'status',
            'last_heartbeat', 'address',
            'is_active', 'connector_count', 'available_connectors',
        ]

    def get_connector_count(self, obj):
        return Connector.objects.filter(evse__charging_station=obj).count()

    def get_available_connectors(self, obj):
        return Connector.objects.filter(
            evse__charging_station=obj,
            current_status='Available',
        ).count()
