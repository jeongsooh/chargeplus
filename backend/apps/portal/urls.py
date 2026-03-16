from django.urls import path
from apps.portal.views import auth, cs, partner, customer

app_name = 'portal'

urlpatterns = [
    # Auth
    path('', auth.login_view, name='login'),
    path('logout/', auth.logout_view, name='logout'),
    path('register/', auth.register_select, name='register_select'),
    path('register/customer/', auth.register_customer, name='register_customer'),
    path('register/partner/', auth.register_partner, name='register_partner'),
    path('register/cs/', auth.register_cs, name='register_cs'),

    # CS portal
    path('portal/cs/', cs.dashboard, name='cs_dashboard'),
    path('portal/cs/users/', cs.users_list, name='cs_users'),
    path('portal/cs/users/<int:user_id>/toggle/', cs.user_toggle_status, name='cs_user_toggle'),
    path('portal/cs/partners/', cs.partners_list, name='cs_partners'),
    path('portal/cs/partners/<int:partner_id>/approve/', cs.partner_approve, name='cs_partner_approve'),
    path('portal/cs/chargers/', cs.chargers_list, name='cs_chargers'),
    path('portal/cs/sites/', cs.sites_list, name='cs_sites'),
    path('portal/cs/sites/create/', cs.site_create, name='cs_site_create'),
    path('portal/cs/sessions/', cs.sessions_list, name='cs_sessions'),
    path('portal/cs/config/', cs.config_view, name='cs_config'),

    # Partner portal
    path('portal/partner/', partner.dashboard, name='partner_dashboard'),
    path('portal/partner/sites/', partner.sites_list, name='partner_sites'),
    path('portal/partner/sites/<int:site_id>/price/', partner.site_update_price, name='partner_site_price'),
    path('portal/partner/chargers/', partner.chargers_list, name='partner_chargers'),
    path('portal/partner/stats/', partner.stats_view, name='partner_stats'),

    # Customer portal
    path('portal/customer/', customer.dashboard, name='customer_dashboard'),
    path('portal/customer/history/', customer.history, name='customer_history'),
    path('portal/customer/cards/', customer.cards_list, name='customer_cards'),
    path('portal/customer/cards/add/', customer.card_add, name='customer_card_add'),
    path('portal/customer/cards/<str:token_id>/delete/', customer.card_delete, name='customer_card_delete'),
    path('portal/customer/profile/', customer.profile_view, name='customer_profile'),
]
