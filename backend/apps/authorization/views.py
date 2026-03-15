from rest_framework import viewsets, status
from rest_framework.decorators import action
from rest_framework.permissions import IsAuthenticated, IsAdminUser
from rest_framework.response import Response

from .models import IdToken, AuthorizationRecord
from .serializers import IdTokenSerializer, AuthorizationRecordSerializer


class IdTokenViewSet(viewsets.ModelViewSet):
    queryset = IdToken.objects.select_related('user', 'operator').order_by('-created_at')
    serializer_class = IdTokenSerializer
    permission_classes = [IsAdminUser]

    def get_queryset(self):
        qs = super().get_queryset()
        status_filter = self.request.query_params.get('status')
        if status_filter:
            qs = qs.filter(status=status_filter)
        token_type = self.request.query_params.get('type')
        if token_type:
            qs = qs.filter(token_type=token_type)
        return qs

    @action(detail=True, methods=['post'])
    def block(self, request, pk=None):
        token = self.get_object()
        token.status = IdToken.Status.BLOCKED
        token.save(update_fields=['status', 'updated_at'])
        return Response({'status': 'blocked', 'id_token': token.id_token})

    @action(detail=True, methods=['post'])
    def accept(self, request, pk=None):
        token = self.get_object()
        token.status = IdToken.Status.ACCEPTED
        token.save(update_fields=['status', 'updated_at'])
        return Response({'status': 'accepted', 'id_token': token.id_token})
