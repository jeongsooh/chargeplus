from rest_framework import viewsets
from rest_framework.permissions import IsAuthenticated

from .models import Transaction
from .serializers import TransactionSerializer, TransactionListSerializer


class TransactionViewSet(viewsets.ReadOnlyModelViewSet):
    """
    ViewSet for listing and retrieving charging transactions.
    Supports filtering by station_id, state, date range.
    """
    queryset = Transaction.objects.select_related(
        'charging_station', 'connector', 'id_token'
    ).prefetch_related('meter_values').order_by('-created_at')
    permission_classes = [IsAuthenticated]

    def get_serializer_class(self):
        if self.action == 'list':
            return TransactionListSerializer
        return TransactionSerializer

    def get_queryset(self):
        qs = super().get_queryset()

        station_id = self.request.query_params.get('station_id')
        if station_id:
            qs = qs.filter(charging_station__station_id=station_id)

        state = self.request.query_params.get('state')
        if state:
            qs = qs.filter(state=state)

        start_date = self.request.query_params.get('start_date')
        if start_date:
            qs = qs.filter(time_start__date__gte=start_date)

        end_date = self.request.query_params.get('end_date')
        if end_date:
            qs = qs.filter(time_start__date__lte=end_date)

        id_tag = self.request.query_params.get('id_tag')
        if id_tag:
            qs = qs.filter(id_token__id_token=id_tag)

        return qs
