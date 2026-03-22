from django.urls import path

from .views import (
    PaymentCreateView,
    PaymentIpnView,
    PaymentStatusView,
    PaymentReturnView,
    PaymentCancelView,
    PaymentMockView,
    PaymentMockSubmitView,
)

urlpatterns = [
    path('create/', PaymentCreateView.as_view(), name='payment-create'),
    path('ipn/', PaymentIpnView.as_view(), name='payment-ipn'),
    path('status/<str:order_reference>/', PaymentStatusView.as_view(), name='payment-status'),
    path('return/', PaymentReturnView.as_view(), name='payment-return'),
    path('cancel/', PaymentCancelView.as_view(), name='payment-cancel'),
    path('mock/', PaymentMockView.as_view(), name='payment-mock'),
    path('mock/submit/', PaymentMockSubmitView.as_view(), name='payment-mock-submit'),
]
