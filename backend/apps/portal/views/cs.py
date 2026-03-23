import json
from datetime import date, timedelta

from django.contrib import messages
from django.contrib.auth.hashers import make_password
from django.core.paginator import Paginator
from django.db.models import Count, Sum, Q
from django.db.models.functions import TruncDay, TruncWeek, TruncMonth
from django.shortcuts import render, get_object_or_404, redirect
from django.utils import timezone
from django.utils.translation import gettext as _
from django.views.decorators.http import require_POST

from django.db.models import ProtectedError

from apps.authorization.models import IdToken
from apps.config.models import CsmsVariable
from apps.ocpp16.models import OcppMessage
from apps.portal.decorators import role_required
from apps.stations.models import ChargingStation, ChargingSite, Operator, FaultLog
from apps.transactions.models import Transaction
from apps.users.models import User, PartnerProfile, PaymentCard


# ─────────────────────────────────────────────────────────── dashboard ──────

@role_required('cs')
def dashboard(request):
    now = timezone.now()
    month_start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)

    stats = {
        'total_stations': ChargingStation.objects.filter(is_active=True).count(),
        'online_stations': ChargingStation.objects.filter(is_active=True).exclude(status='Offline').count(),
        'total_users': User.objects.filter(role='customer', is_active=True).count(),
        'total_partners': User.objects.filter(role='partner').count(),
        'pending_partners': User.objects.filter(role='partner', status='pending').count(),
        'month_sessions': Transaction.objects.filter(time_start__gte=month_start, state='Completed').count(),
        'month_energy': Transaction.objects.filter(
            time_start__gte=month_start, state='Completed'
        ).aggregate(total=Sum('energy_kwh'))['total'] or 0,
    }

    tab = request.GET.get('tab', 'daily')
    service_rows, prev_period_data = _build_service_stats(tab)

    return render(request, 'portal/cs/dashboard.html', {
        'stats': stats,
        'tab': tab,
        'service_rows': service_rows,
        'prev_period_data': prev_period_data,
    })


def _build_service_stats(tab):
    """Return list of dicts for the service status table (last 4 periods)."""
    now = timezone.now()

    if tab == 'weekly':
        trunc_fn = TruncWeek
        periods = [now - timedelta(weeks=i) for i in range(4, 0, -1)]
        label_fmt = lambda d: f"{d.isocalendar()[0]}년 {d.isocalendar()[1]}주"
        delta = timedelta(weeks=1)
    elif tab == 'monthly':
        trunc_fn = TruncMonth
        months = []
        cur = now.replace(day=1)
        for _ in range(4):
            months.insert(0, cur)
            if cur.month == 1:
                cur = cur.replace(year=cur.year - 1, month=12)
            else:
                cur = cur.replace(month=cur.month - 1)
        periods = months
        label_fmt = lambda d: d.strftime('%Y년 %m월')
        delta = None  # handled per-month
    else:  # daily
        trunc_fn = TruncDay
        periods = [now.date() - timedelta(days=i) for i in range(3, -1, -1)]
        label_fmt = lambda d: d.strftime('%m/%d')
        delta = timedelta(days=1)

    def _query_period(start, end):
        return Transaction.objects.filter(
            state='Completed', time_start__gte=start, time_start__lt=end
        ).aggregate(
            energy=Sum('energy_kwh'),
            amount=Sum('amount'),
            count=Count('transaction_id'),
        )

    rows = []
    prev_data = {}

    for i, period_start in enumerate(periods):
        if tab == 'daily':
            start = timezone.make_aware(timezone.datetime(
                period_start.year, period_start.month, period_start.day))
            end = start + timedelta(days=1)
            prev_start = start - timedelta(days=1)
            prev_end = start
        elif tab == 'weekly':
            # TruncWeek aligns to Monday
            wd = period_start.weekday()
            monday = period_start - timedelta(days=wd)
            start = timezone.make_aware(timezone.datetime(monday.year, monday.month, monday.day))
            end = start + timedelta(weeks=1)
            prev_start = start - timedelta(weeks=1)
            prev_end = start
        else:  # monthly
            start = timezone.make_aware(timezone.datetime(
                period_start.year, period_start.month, 1))
            if period_start.month == 12:
                end = timezone.make_aware(timezone.datetime(period_start.year + 1, 1, 1))
            else:
                end = timezone.make_aware(timezone.datetime(period_start.year, period_start.month + 1, 1))
            if period_start.month == 1:
                prev_start = timezone.make_aware(timezone.datetime(period_start.year - 1, 12, 1))
            else:
                prev_start = timezone.make_aware(timezone.datetime(period_start.year, period_start.month - 1, 1))
            prev_end = start

        curr = _query_period(start, end)
        prev = _query_period(prev_start, prev_end)

        def _diff(curr_val, prev_val):
            c = float(curr_val or 0)
            p = float(prev_val or 0)
            return round(c - p, 3)

        rows.append({
            'label': label_fmt(period_start),
            'start_iso': start.isoformat(),
            'end_iso': end.isoformat(),
            'energy': float(curr['energy'] or 0),
            'amount': float(curr['amount'] or 0),
            'count': curr['count'] or 0,
            'energy_diff': _diff(curr['energy'], prev['energy']),
            'amount_diff': _diff(curr['amount'], prev['amount']),
            'count_diff': (curr['count'] or 0) - (prev['count'] or 0),
        })

    return rows, {}


@role_required('cs')
def stats_detail(request):
    """Detail breakdown by site/charger for a given period."""
    start_iso = request.GET.get('start', '')
    end_iso = request.GET.get('end', '')
    tab = request.GET.get('tab', 'daily')

    try:
        from django.utils.dateparse import parse_datetime
        start = parse_datetime(start_iso)
        end = parse_datetime(end_iso)
    except Exception:
        return redirect('portal:cs_dashboard')

    base_qs = Transaction.objects.filter(state='Completed', time_start__gte=start, time_start__lt=end)

    # Breakdown by site
    by_site = (
        base_qs
        .values('charging_station__site__site_name', 'charging_station__site__id')
        .annotate(energy=Sum('energy_kwh'), amount=Sum('amount'), count=Count('transaction_id'))
        .order_by('-energy')
    )

    # Breakdown by charger
    by_charger = (
        base_qs
        .values('charging_station__station_id', 'charging_station__site__site_name')
        .annotate(energy=Sum('energy_kwh'), amount=Sum('amount'), count=Count('transaction_id'))
        .order_by('-energy')
    )

    # Previous period comparison
    delta = end - start
    prev_start = start - delta
    prev_end = start
    prev_qs = Transaction.objects.filter(state='Completed', time_start__gte=prev_start, time_start__lt=prev_end)

    prev_by_charger = {
        r['charging_station__station_id']: r
        for r in prev_qs.values('charging_station__station_id')
        .annotate(energy=Sum('energy_kwh'), amount=Sum('amount'), count=Count('transaction_id'))
    }

    charger_rows = []
    for row in by_charger:
        sid = row['charging_station__station_id']
        prev = prev_by_charger.get(sid, {})
        charger_rows.append({
            **row,
            'energy_diff': float(row['energy'] or 0) - float(prev.get('energy') or 0),
            'amount_diff': float(row['amount'] or 0) - float(prev.get('amount') or 0),
            'count_diff': (row['count'] or 0) - (prev.get('count') or 0),
        })

    return render(request, 'portal/cs/stats_detail.html', {
        'start': start,
        'end': end,
        'tab': tab,
        'by_site': by_site,
        'charger_rows': charger_rows,
    })


# ──────────────────────────────────────────────────────────── users ──────────

@role_required('cs')
def users_list(request):
    qs = User.objects.all().order_by('-created_at')
    role_filter = request.GET.get('role', '')
    status_filter = request.GET.get('status', '')
    q = request.GET.get('q', '')
    if role_filter:
        qs = qs.filter(role=role_filter)
    if status_filter:
        qs = qs.filter(status=status_filter)
    if q:
        qs = qs.filter(Q(username__icontains=q) | Q(email__icontains=q) | Q(first_name__icontains=q))
    return render(request, 'portal/cs/users.html', {
        'users': qs, 'role_filter': role_filter, 'status_filter': status_filter, 'q': q,
    })


@role_required('cs')
def user_create(request):
    if request.method == 'POST':
        username = request.POST.get('username', '').strip()
        password = request.POST.get('password', '')
        email = request.POST.get('email', '').strip()
        first_name = request.POST.get('first_name', '').strip()
        phone = request.POST.get('phone', '').strip()
        role = request.POST.get('role', 'customer')
        status = 'active' if role == 'customer' else request.POST.get('status', 'pending')

        if not username or not password:
            messages.error(request, _('아이디와 비밀번호는 필수입니다.'))
            return render(request, 'portal/cs/user_form.html')
        if User.objects.filter(username=username).exists():
            messages.error(request, _('이미 사용 중인 아이디입니다.'))
            return render(request, 'portal/cs/user_form.html')

        user = User.objects.create_user(
            username=username, password=password,
            email=email, first_name=first_name,
            phone=phone, role=role, status=status,
        )
        if role == 'partner':
            PartnerProfile.objects.create(
                user=user,
                business_name=request.POST.get('business_name', '').strip(),
                business_no=request.POST.get('business_no', '').strip(),
                contact_phone=request.POST.get('contact_phone', '').strip(),
            )
        messages.success(request, _(f"사용자 '{username}'이 생성되었습니다."))
        return redirect('portal:cs_users')
    return render(request, 'portal/cs/user_form.html')


@role_required('cs')
def user_detail(request, user_id):
    target = get_object_or_404(User, pk=user_id)
    payment_cards = PaymentCard.objects.filter(user=target).order_by('-created_at')

    if request.method == 'POST':
        action = request.POST.get('action')
        if action == 'update_profile':
            target.first_name = request.POST.get('first_name', '').strip()
            target.email = request.POST.get('email', '').strip()
            target.phone = request.POST.get('phone', '').strip()
            target.role = request.POST.get('role', target.role)
            target.status = request.POST.get('status', target.status)
            new_pw = request.POST.get('new_password', '')
            if new_pw:
                target.set_password(new_pw)
            target.save()
            messages.success(request, _('사용자 정보가 수정되었습니다.'))

        elif action == 'add_card':
            nickname = request.POST.get('nickname', '').strip()
            card_last4 = request.POST.get('card_last4', '').strip()
            card_type = request.POST.get('card_type', '국내카드')
            if nickname and card_last4:
                # Set new card as default if first card
                is_default = not payment_cards.exists()
                if request.POST.get('is_default') == '1':
                    PaymentCard.objects.filter(user=target).update(is_default=False)
                    is_default = True
                PaymentCard.objects.create(
                    user=target, nickname=nickname,
                    card_last4=card_last4, card_type=card_type,
                    is_default=is_default,
                )
                messages.success(request, _('카드가 등록되었습니다.'))
            else:
                messages.error(request, _('카드 별칭과 끝 4자리를 입력해 주세요.'))

        elif action == 'delete_card':
            card_id = request.POST.get('card_id')
            PaymentCard.objects.filter(pk=card_id, user=target).delete()
            messages.success(request, _('카드가 삭제되었습니다.'))

        elif action == 'set_default_card':
            card_id = request.POST.get('card_id')
            PaymentCard.objects.filter(user=target).update(is_default=False)
            PaymentCard.objects.filter(pk=card_id, user=target).update(is_default=True)

        return redirect('portal:cs_user_detail', user_id=user_id)

    return render(request, 'portal/cs/user_detail.html', {
        'target': target,
        'payment_cards': payment_cards,
        'card_types': PaymentCard.CardType.choices,
    })


@role_required('cs')
@require_POST
def user_delete(request, user_id):
    target = get_object_or_404(User, pk=user_id)
    if target == request.user:
        messages.error(request, _('자기 자신은 삭제할 수 없습니다.'))
        return redirect('portal:cs_users')
    username = target.username
    try:
        target.delete()
        messages.success(request, _(f"'{username}' 사용자가 삭제되었습니다."))
    except ProtectedError:
        messages.error(request, _(f"'{username}' 사용자는 연결된 데이터(충전이력 등)가 있어 삭제할 수 없습니다."))
    return redirect('portal:cs_users')


@role_required('cs')
@require_POST
def user_toggle_status(request, user_id):
    user = get_object_or_404(User, pk=user_id)
    if user == request.user:
        messages.error(request, _('자기 자신의 상태는 변경할 수 없습니다.'))
    else:
        user.status = 'inactive' if user.status == 'active' else 'active'
        user.save(update_fields=['status'])
        messages.success(request, _(f"{user.username} 상태가 {user.status}로 변경되었습니다."))
    return redirect('portal:cs_users')


# ──────────────────────────────────────────────────────────── partners ────────

@role_required('cs')
def partners_list(request):
    partners = PartnerProfile.objects.select_related('user').order_by('-created_at')
    pending_only = request.GET.get('pending', '')
    if pending_only:
        partners = partners.filter(user__status='pending')
    return render(request, 'portal/cs/partners.html', {
        'partners': partners, 'pending_only': pending_only,
    })


@role_required('cs')
def partner_create(request):
    if request.method == 'POST':
        username = request.POST.get('username', '').strip()
        password = request.POST.get('password', 'ChargePlus1234!')
        email = request.POST.get('email', '').strip()
        first_name = request.POST.get('first_name', '').strip()
        business_name = request.POST.get('business_name', '').strip()
        business_no = request.POST.get('business_no', '').strip()
        contact_phone = request.POST.get('contact_phone', '').strip()

        if not username or not business_name:
            messages.error(request, _('아이디와 사업체명은 필수입니다.'))
            return render(request, 'portal/cs/partner_form.html')
        if User.objects.filter(username=username).exists():
            messages.error(request, _('이미 사용 중인 아이디입니다.'))
            return render(request, 'portal/cs/partner_form.html')

        user = User.objects.create_user(
            username=username, password=password,
            email=email, first_name=first_name,
            role='partner', status='active',
        )
        PartnerProfile.objects.create(
            user=user, business_name=business_name,
            business_no=business_no, contact_phone=contact_phone,
        )
        messages.success(request, _(f"파트너 '{business_name}'이 생성되었습니다. 초기 비밀번호: {password}"))
        return redirect('portal:cs_partners')
    return render(request, 'portal/cs/partner_form.html')


@role_required('cs')
def partner_detail(request, partner_id):
    profile = get_object_or_404(PartnerProfile, pk=partner_id)
    sites = ChargingSite.objects.filter(partner=profile).annotate(
        station_count=Count('stations')
    )
    stations = ChargingStation.objects.filter(site__partner=profile).select_related('site')

    if request.method == 'POST':
        action = request.POST.get('action')
        if action == 'update':
            profile.business_name = request.POST.get('business_name', '').strip()
            profile.business_no = request.POST.get('business_no', '').strip()
            profile.contact_phone = request.POST.get('contact_phone', '').strip()
            profile.save()
            profile.user.first_name = request.POST.get('first_name', '').strip()
            profile.user.email = request.POST.get('email', '').strip()
            profile.user.save(update_fields=['first_name', 'email'])
            messages.success(request, _('파트너 정보가 수정되었습니다.'))
        return redirect('portal:cs_partner_detail', partner_id=partner_id)

    return render(request, 'portal/cs/partner_detail.html', {
        'profile': profile, 'sites': sites, 'stations': stations,
    })


@role_required('cs')
@require_POST
def partner_approve(request, partner_id):
    profile = get_object_or_404(PartnerProfile, pk=partner_id)
    action = request.POST.get('action')
    if action == 'approve':
        profile.user.status = 'active'
        profile.user.save(update_fields=['status'])
        messages.success(request, _(f"{profile.business_name} 파트너가 승인되었습니다."))
    elif action == 'reject':
        profile.user.status = 'inactive'
        profile.user.save(update_fields=['status'])
        messages.warning(request, _(f"{profile.business_name} 파트너가 반려되었습니다."))
    return redirect('portal:cs_partners')


@role_required('cs')
@require_POST
def partner_delete(request, partner_id):
    profile = get_object_or_404(PartnerProfile, pk=partner_id)
    name = profile.business_name
    try:
        profile.user.delete()  # cascades to PartnerProfile
        messages.success(request, _(f"파트너 '{name}'이 삭제되었습니다."))
    except ProtectedError:
        messages.error(request, _(f"'{name}' 파트너는 소속 충전소가 있어 삭제할 수 없습니다. 충전소를 먼저 삭제해 주세요."))
    return redirect('portal:cs_partners')


# ──────────────────────────────────────────────────────────── chargers ────────

@role_required('cs')
def chargers_list(request):
    stations = ChargingStation.objects.select_related('operator', 'site').order_by('station_id')
    status_filter = request.GET.get('status', '')
    q = request.GET.get('q', '')
    if status_filter:
        stations = stations.filter(status=status_filter)
    if q:
        stations = stations.filter(Q(station_id__icontains=q) | Q(address__icontains=q))
    return render(request, 'portal/cs/chargers.html', {
        'stations': stations, 'status_filter': status_filter, 'q': q,
        'status_choices': ChargingStation.Status.choices,
    })


@role_required('cs')
def charger_create(request):
    operators = Operator.objects.all().order_by('name')
    sites = ChargingSite.objects.select_related('partner').order_by('site_name')
    if request.method == 'POST':
        station_id = request.POST.get('station_id', '').strip().upper()
        operator_id = request.POST.get('operator_id', '')
        site_id = request.POST.get('site_id', '') or None
        address = request.POST.get('address', '').strip()

        if not station_id or not operator_id:
            messages.error(request, _('충전기 ID와 운영사는 필수입니다.'))
        elif ChargingStation.objects.filter(station_id=station_id).exists():
            messages.error(request, _('이미 존재하는 충전기 ID입니다.'))
        else:
            ChargingStation.objects.create(
                station_id=station_id,
                operator_id=operator_id,
                site_id=site_id,
                address=address,
                status=ChargingStation.Status.OFFLINE,
            )
            messages.success(request, _(f"충전기 '{station_id}'이 등록되었습니다."))
            return redirect('portal:cs_chargers')

    return render(request, 'portal/cs/charger_form.html', {
        'operators': operators, 'sites': sites,
    })


@role_required('cs')
def charger_detail(request, station_pk):
    station = get_object_or_404(ChargingStation, pk=station_pk)
    fault_logs = FaultLog.objects.filter(charging_station=station).order_by('-reported_at')
    sessions = Transaction.objects.filter(
        charging_station=station
    ).order_by('-time_start')[:20]

    return render(request, 'portal/cs/charger_detail.html', {
        'station': station,
        'fault_logs': fault_logs,
        'sessions': sessions,
        'fault_type_choices': FaultLog.FaultType.choices,
    })


@role_required('cs')
@require_POST
def charger_fault_add(request, station_pk):
    station = get_object_or_404(ChargingStation, pk=station_pk)
    fault_type = request.POST.get('fault_type', 'other')
    description = request.POST.get('description', '').strip()
    reported_at_str = request.POST.get('reported_at', '')

    if not description:
        messages.error(request, _('장애 내용을 입력해 주세요.'))
        return redirect('portal:cs_charger_detail', station_pk=station_pk)

    try:
        from django.utils.dateparse import parse_datetime
        reported_at = parse_datetime(reported_at_str) or timezone.now()
        if timezone.is_naive(reported_at):
            reported_at = timezone.make_aware(reported_at)
    except Exception:
        reported_at = timezone.now()

    FaultLog.objects.create(
        charging_station=station,
        reported_at=reported_at,
        fault_type=fault_type,
        description=description,
        reported_by=request.user.username,
    )
    messages.success(request, _('장애이력이 등록되었습니다.'))
    return redirect('portal:cs_charger_detail', station_pk=station_pk)


@role_required('cs')
@require_POST
def charger_delete(request, station_pk):
    station = get_object_or_404(ChargingStation, pk=station_pk)
    station_id = station.station_id
    try:
        station.delete()
        messages.success(request, _(f"충전기 '{station_id}'이 삭제되었습니다."))
    except ProtectedError:
        messages.error(request, _(f"'{station_id}' 충전기는 충전이력이 있어 삭제할 수 없습니다."))
    return redirect('portal:cs_chargers')


# ──────────────────────────────────────────────────────── idtokens ───────────

def _idtoken_form_ctx():
    return {
        'status_choices': IdToken.Status.choices,
        'type_choices': IdToken.Type.choices,
        'users': User.objects.filter(is_active=True).order_by('username'),
    }


@role_required('cs')
def idtokens_list(request):
    qs = IdToken.objects.select_related('user').order_by('-created_at')
    status_filter = request.GET.get('status', '')
    type_filter = request.GET.get('token_type', '')
    q = request.GET.get('q', '')

    if status_filter:
        qs = qs.filter(status=status_filter)
    if type_filter:
        qs = qs.filter(token_type=type_filter)
    if q:
        qs = qs.filter(Q(id_token__icontains=q) | Q(user__username__icontains=q))

    paginator = Paginator(qs, 20)
    page = paginator.get_page(request.GET.get('page', 1))

    return render(request, 'portal/cs/idtokens.html', {
        'page': page,
        'status_filter': status_filter,
        'type_filter': type_filter,
        'q': q,
        'status_choices': IdToken.Status.choices,
        'type_choices': IdToken.Type.choices,
    })


@role_required('cs')
def idtoken_create(request):
    ctx = _idtoken_form_ctx()
    if request.method == 'POST':
        id_token_val = request.POST.get('id_token', '').strip().upper()
        token_type = request.POST.get('token_type', 'RFID')
        status = request.POST.get('status', 'Accepted')
        user_id = request.POST.get('user_id', '') or None
        expiry_date = _parse_expiry(request.POST.get('expiry_date', ''))

        if not id_token_val:
            messages.error(request, _('카드 번호를 입력해 주세요.'))
            return render(request, 'portal/cs/idtoken_form.html', ctx)
        if IdToken.objects.filter(id_token=id_token_val).exists():
            messages.error(request, _('이미 등록된 카드 번호입니다.'))
            return render(request, 'portal/cs/idtoken_form.html', ctx)

        IdToken.objects.create(
            id_token=id_token_val, token_type=token_type,
            status=status, user_id=user_id, expiry_date=expiry_date,
        )
        messages.success(request, _(f"충전카드 '{id_token_val}'이 등록되었습니다."))
        return redirect('portal:cs_idtokens')

    return render(request, 'portal/cs/idtoken_form.html', ctx)


@role_required('cs')
def idtoken_edit(request, token_id):
    token = get_object_or_404(IdToken, pk=token_id)
    ctx = {**_idtoken_form_ctx(), 'token': token}

    if request.method == 'POST':
        token.token_type = request.POST.get('token_type', token.token_type)
        token.status = request.POST.get('status', token.status)
        token.user_id = request.POST.get('user_id', '') or None
        token.expiry_date = _parse_expiry(request.POST.get('expiry_date', ''))
        token.save()
        messages.success(request, _(f"충전카드 '{token.id_token}'이 수정되었습니다."))
        return redirect('portal:cs_idtokens')

    return render(request, 'portal/cs/idtoken_form.html', ctx)


@role_required('cs')
@require_POST
def idtoken_delete(request, token_id):
    token = get_object_or_404(IdToken, pk=token_id)
    token_val = token.id_token
    try:
        token.delete()
        messages.success(request, _(f"충전카드 '{token_val}'이 삭제되었습니다."))
    except ProtectedError:
        messages.error(request, _(f"'{token_val}' 카드는 충전이력이 있어 삭제할 수 없습니다."))
    return redirect('portal:cs_idtokens')


def _parse_expiry(expiry_str):
    """Parse datetime-local string to aware datetime or None."""
    if not expiry_str:
        return None
    from django.utils.dateparse import parse_datetime
    dt = parse_datetime(expiry_str)
    if dt and timezone.is_naive(dt):
        dt = timezone.make_aware(dt)
    return dt


# ──────────────────────────────────────────────────────────── sites ───────────

@role_required('cs')
def sites_list(request):
    sites = ChargingSite.objects.select_related('partner__user').annotate(
        station_count=Count('stations')
    ).order_by('site_name')
    return render(request, 'portal/cs/sites.html', {'sites': sites})


@role_required('cs')
def site_create(request):
    if request.method == 'POST':
        partner_id = request.POST.get('partner_id')
        site_name = request.POST.get('site_name', '').strip()
        address = request.POST.get('address', '').strip()
        unit_price = request.POST.get('unit_price', '0')
        if not site_name or not partner_id:
            messages.error(request, _('충전소명과 파트너를 선택해 주세요.'))
        else:
            ChargingSite.objects.create(
                partner_id=partner_id, site_name=site_name,
                address=address, unit_price=unit_price,
            )
            messages.success(request, _(f"충전소 '{site_name}'이 등록되었습니다."))
            return redirect('portal:cs_sites')
    partners = PartnerProfile.objects.select_related('user').filter(user__status='active')
    return render(request, 'portal/cs/site_form.html', {'partners': partners})


# ──────────────────────────────────────────────────────────── sessions ────────

@role_required('cs')
def sessions_list(request):
    qs = Transaction.objects.select_related('charging_station', 'id_token__user').order_by('-time_start')

    # Filters
    date_from = request.GET.get('date_from', '')
    date_to = request.GET.get('date_to', '')
    site_id = request.GET.get('site_id', '')
    station_q = request.GET.get('station_q', '')
    user_q = request.GET.get('user_q', '')

    if date_from:
        qs = qs.filter(time_start__date__gte=date_from)
    if date_to:
        qs = qs.filter(time_start__date__lte=date_to)
    if site_id:
        qs = qs.filter(charging_station__site_id=site_id)
    if station_q:
        qs = qs.filter(charging_station__station_id__icontains=station_q)
    if user_q:
        qs = qs.filter(
            Q(id_token__user__username__icontains=user_q) |
            Q(id_token__id_token__icontains=user_q)
        )

    paginator = Paginator(qs, 20)
    page = paginator.get_page(request.GET.get('page', 1))
    sites = ChargingSite.objects.order_by('site_name')

    return render(request, 'portal/cs/sessions.html', {
        'page': page,
        'sites': sites,
        'date_from': date_from, 'date_to': date_to,
        'site_id': site_id, 'station_q': station_q, 'user_q': user_q,
    })


# ─────────────────────────────────────────────────────────── payments ────

@role_required('cs')
def payments_list(request):
    from apps.payment.models import PaymentTransaction

    qs = PaymentTransaction.objects.select_related('user').order_by('-created_at')

    station_q = request.GET.get('station_q', '')
    user_q = request.GET.get('user_q', '')
    status_q = request.GET.get('status_q', '')
    date_from = request.GET.get('date_from', '')
    date_to = request.GET.get('date_to', '')

    if station_q:
        qs = qs.filter(station_id__icontains=station_q)
    if user_q:
        qs = qs.filter(
            Q(user__username__icontains=user_q) |
            Q(user__email__icontains=user_q) |
            Q(user__first_name__icontains=user_q)
        )
    if status_q:
        qs = qs.filter(status=status_q)
    if date_from:
        qs = qs.filter(created_at__date__gte=date_from)
    if date_to:
        qs = qs.filter(created_at__date__lte=date_to)

    paginator = Paginator(qs, 20)
    page = paginator.get_page(request.GET.get('page', 1))

    from apps.payment.models import PaymentTransaction as PT
    return render(request, 'portal/cs/payments.html', {
        'page': page,
        'station_q': station_q, 'user_q': user_q,
        'status_q': status_q, 'date_from': date_from, 'date_to': date_to,
        'status_choices': PT.Status.choices,
    })


# ──────────────────────────────────────────────────────── system ops ──────────

@role_required('cs')
def ops_active_stations(request):
    from apps.ocpp16.redis_client import get_redis

    r = get_redis()
    stations = ChargingStation.objects.filter(is_active=True).prefetch_related(
        'evses__connectors'
    ).order_by('station_id')

    station_list = []
    for st in stations:
        if r.exists(f"ocpp:connected:{st.station_id}"):
            connectors = []
            for evse in st.evses.all():
                for conn in evse.connectors.all():
                    connectors.append({
                        'evse_id': evse.evse_id,
                        'connector_id': conn.connector_id,
                        'status': conn.current_status,
                        'error_code': conn.error_code,
                    })
            station_list.append({'station': st, 'connectors': connectors})

    return render(request, 'portal/cs/ops_active_stations.html', {
        'station_list': station_list,
    })


@role_required('cs')
def ops_station_cmd(request, station_id):
    """AJAX POST: send OCPP command to a station, return JSON."""
    import json as _json
    from django.http import JsonResponse
    from apps.ocpp16.services.gateway_client import GatewayClient

    if request.method != 'POST':
        return JsonResponse({'success': False, 'error': 'Method not allowed'}, status=405)

    try:
        body = _json.loads(request.body)
        action = body.get('action', '').strip()
        payload = body.get('payload', {})
    except Exception as e:
        return JsonResponse({'success': False, 'error': f'Invalid JSON: {e}'}, status=400)

    if not action:
        return JsonResponse({'success': False, 'error': 'action is required'}, status=400)

    if not GatewayClient.is_station_connected(station_id):
        return JsonResponse({'success': False, 'error': '충전기가 오프라인입니다.'})

    try:
        if action == 'UpdateFirmware':
            GatewayClient.send_command_async(station_id, action, payload)
            result = {'message': '펌웨어 업데이트 명령이 전송되었습니다 (비동기).'}
        else:
            timeout = 15 if action in ('GetConfiguration', 'GetLocalListVersion', 'GetCompositeSchedule') else 30
            result = GatewayClient.send_command(station_id, action, payload, timeout=timeout)
        return JsonResponse({'success': True, 'result': result})
    except TimeoutError:
        return JsonResponse({'success': False, 'error': f'{action} 응답 시간 초과.'})
    except Exception as e:
        return JsonResponse({'success': False, 'error': str(e)})


@role_required('cs')
def ops_config(request):
    variables = CsmsVariable.objects.all().order_by('key')
    if request.method == 'POST':
        key = request.POST.get('key', '').strip()
        value = request.POST.get('value', '').strip()
        if key:
            CsmsVariable.objects.filter(key=key).update(
                value=value, updated_by=request.user.username,
            )
            messages.success(request, _(f"'{key}' 변수가 업데이트되었습니다."))
            return redirect('portal:cs_ops_config')
    return render(request, 'portal/cs/ops_config.html', {'variables': variables})


@role_required('cs')
def ops_msglog(request):
    qs = OcppMessage.objects.order_by('-created_at')

    date_from = request.GET.get('date_from', '')
    date_to = request.GET.get('date_to', '')
    station_q = request.GET.get('station_q', '')
    action_q = request.GET.get('action_q', '')

    if date_from:
        qs = qs.filter(created_at__date__gte=date_from)
    if date_to:
        qs = qs.filter(created_at__date__lte=date_to)
    if station_q:
        qs = qs.filter(station_id__icontains=station_q)
    if action_q:
        qs = qs.filter(action__icontains=action_q)

    paginator = Paginator(qs, 20)
    page = paginator.get_page(request.GET.get('page', 1))

    return render(request, 'portal/cs/ops_msglog.html', {
        'page': page,
        'date_from': date_from, 'date_to': date_to,
        'station_q': station_q, 'action_q': action_q,
    })
