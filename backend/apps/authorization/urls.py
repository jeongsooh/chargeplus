from django.urls import path, include
from rest_framework.routers import DefaultRouter

from .views import IdTokenViewSet

router = DefaultRouter()
router.register(r'', IdTokenViewSet, basename='idtoken')

urlpatterns = [
    path('', include(router.urls)),
]
