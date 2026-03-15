from django.urls import path, include
from rest_framework.routers import DefaultRouter

from .views import ChargingStationViewSet, CommandView

router = DefaultRouter()
router.register(r'', ChargingStationViewSet, basename='station')

urlpatterns = [
    path('', include(router.urls)),
    path('<str:station_id>/command/', CommandView.as_view(), name='station-command'),
]
