from django.contrib import admin
from django.urls import path, include

urlpatterns = [
    path('admin/', admin.site.urls),
    path('i18n/', include('django.conf.urls.i18n')),
    # Portal (session-based, web UI)
    path('', include('apps.portal.urls', namespace='portal')),
    # REST API (JWT-based)
    path('api/', include('apps.mobile_api.urls')),
    path('api/payment/', include('apps.payment.urls')),
    path('api/v1/', include('apps.ocpp16.urls')),
    path('api/v1/stations/', include('apps.stations.urls')),
    path('api/v1/transactions/', include('apps.transactions.urls')),
    path('api/v1/cards/', include('apps.authorization.urls')),
]
