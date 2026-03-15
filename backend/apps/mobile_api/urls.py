from django.urls import path

from .views import LoginView, ChargeStartView, ChargeStatusView, ChargeStopView

urlpatterns = [
    path('login', LoginView.as_view(), name='mobile-login'),
    path('charge/start', ChargeStartView.as_view(), name='mobile-charge-start'),
    path('charge/status', ChargeStatusView.as_view(), name='mobile-charge-status'),
    path('charge/stop', ChargeStopView.as_view(), name='mobile-charge-stop'),
]
