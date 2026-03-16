from django.urls import path
from apps.portal.views import auth, cs, partner, customer

app_name = 'portal'

urlpatterns = [
    # ── Auth ──────────────────────────────────────────────────────────────────
    path('', auth.login_view, name='login'),
    path('logout/', auth.logout_view, name='logout'),
    path('register/', auth.register_select, name='register_select'),
    path('register/customer/', auth.register_customer, name='register_customer'),
    path('register/partner/', auth.register_partner, name='register_partner'),
    path('register/cs/', auth.register_cs, name='register_cs'),

    # ── CS portal ─────────────────────────────────────────────────────────────
    path('portal/cs/', cs.dashboard, name='cs_dashboard'),
    path('portal/cs/stats/detail/', cs.stats_detail, name='cs_stats_detail'),

    # Users
    path('portal/cs/users/', cs.users_list, name='cs_users'),
    path('portal/cs/users/create/', cs.user_create, name='cs_user_create'),
    path('portal/cs/users/<int:user_id>/', cs.user_detail, name='cs_user_detail'),
    path('portal/cs/users/<int:user_id>/delete/', cs.user_delete, name='cs_user_delete'),
    path('portal/cs/users/<int:user_id>/toggle/', cs.user_toggle_status, name='cs_user_toggle'),

    # Partners
    path('portal/cs/partners/', cs.partners_list, name='cs_partners'),
    path('portal/cs/partners/create/', cs.partner_create, name='cs_partner_create'),
    path('portal/cs/partners/<int:partner_id>/', cs.partner_detail, name='cs_partner_detail'),
    path('portal/cs/partners/<int:partner_id>/approve/', cs.partner_approve, name='cs_partner_approve'),
    path('portal/cs/partners/<int:partner_id>/delete/', cs.partner_delete, name='cs_partner_delete'),

    # Chargers
    path('portal/cs/chargers/', cs.chargers_list, name='cs_chargers'),
    path('portal/cs/chargers/create/', cs.charger_create, name='cs_charger_create'),
    path('portal/cs/chargers/<int:station_pk>/', cs.charger_detail, name='cs_charger_detail'),
    path('portal/cs/chargers/<int:station_pk>/fault/', cs.charger_fault_add, name='cs_charger_fault_add'),
    path('portal/cs/chargers/<int:station_pk>/delete/', cs.charger_delete, name='cs_charger_delete'),

    # IdTokens (충전카드)
    path('portal/cs/idtokens/', cs.idtokens_list, name='cs_idtokens'),
    path('portal/cs/idtokens/create/', cs.idtoken_create, name='cs_idtoken_create'),
    path('portal/cs/idtokens/<str:token_id>/edit/', cs.idtoken_edit, name='cs_idtoken_edit'),
    path('portal/cs/idtokens/<str:token_id>/delete/', cs.idtoken_delete, name='cs_idtoken_delete'),

    # Sites
    path('portal/cs/sites/', cs.sites_list, name='cs_sites'),
    path('portal/cs/sites/create/', cs.site_create, name='cs_site_create'),

    # Sessions
    path('portal/cs/sessions/', cs.sessions_list, name='cs_sessions'),

    # System Ops
    path('portal/cs/ops/config/', cs.ops_config, name='cs_ops_config'),
    path('portal/cs/ops/msglog/', cs.ops_msglog, name='cs_ops_msglog'),

    # ── Partner portal ────────────────────────────────────────────────────────
    path('portal/partner/', partner.dashboard, name='partner_dashboard'),
    path('portal/partner/sites/', partner.sites_list, name='partner_sites'),
    path('portal/partner/sites/<int:site_id>/price/', partner.site_update_price, name='partner_site_price'),
    path('portal/partner/chargers/', partner.chargers_list, name='partner_chargers'),
    path('portal/partner/stats/', partner.stats_view, name='partner_stats'),

    # ── Customer portal ───────────────────────────────────────────────────────
    path('portal/customer/', customer.dashboard, name='customer_dashboard'),
    path('portal/customer/history/', customer.history, name='customer_history'),
    path('portal/customer/cards/', customer.cards_list, name='customer_cards'),
    path('portal/customer/cards/add/', customer.card_add, name='customer_card_add'),
    path('portal/customer/cards/<str:token_id>/delete/', customer.card_delete, name='customer_card_delete'),
    path('portal/customer/profile/', customer.profile_view, name='customer_profile'),
]
