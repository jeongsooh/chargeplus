from django.shortcuts import render, get_object_or_404, redirect
from django.contrib import messages
from django.db.models import Count, Sum, Q
from django.utils import timezone
from datetime import timedelta

from apps.portal.decorators import role_required
from apps.users.models import User, PartnerProfile
from apps.stations.models import ChargingStation, ChargingSite
from apps.transactions.models import Transaction
from apps.config.models import CsmsVariable


@role_required('cs')
def dashboard(request):
    now = timezone.now()
    month_start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)

    stats = {
        'total_stations': ChargingStation.objects.count(),
        'online_stations': ChargingStation.objects.exclude(status='Offline').count(),
        'total_users': User.objects.filter(role='customer').count(),
        'total_partners': User.objects.filter(role='partner').count(),
        'pending_partners': User.objects.filter(role='partner', status='pending').count(),
        'month_sessions': Transaction.objects.filter(
            time_start__gte=month_start, state='Completed'
        ).count(),
        'month_energy': Transaction.objects.filter(
            time_start__gte=month_start, state='Completed'
        ).aggregate(total=Sum('energy_kwh'))['total'] or 0,
    }
    return render(request, 'portal/cs/dashboard.html', {'stats': stats})


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
        'users': qs,
        'role_filter': role_filter,
        'status_filter': status_filter,
        'q': q,
    })


@role_required('cs')
def user_toggle_status(request, user_id):
    if request.method != 'POST':
        return redirect('portal:cs_users')
    user = get_object_or_404(User, pk=user_id)
    if user == request.user:
        messages.error(request, '자기 자신의 상태는 변경할 수 없습니다.')
        return redirect('portal:cs_users')
    user.status = 'inactive' if user.status == 'active' else 'active'
    user.save(update_fields=['status'])
    messages.success(request, f"{user.username} 상태가 {user.status}로 변경되었습니다.")
    return redirect('portal:cs_users')


@role_required('cs')
def partners_list(request):
    partners = PartnerProfile.objects.select_related('user').order_by('-created_at')
    pending_only = request.GET.get('pending', '')
    if pending_only:
        partners = partners.filter(user__status='pending')
    return render(request, 'portal/cs/partners.html', {
        'partners': partners,
        'pending_only': pending_only,
    })


@role_required('cs')
def partner_approve(request, partner_id):
    if request.method != 'POST':
        return redirect('portal:cs_partners')
    profile = get_object_or_404(PartnerProfile, pk=partner_id)
    action = request.POST.get('action')
    if action == 'approve':
        profile.user.status = 'active'
        profile.user.save(update_fields=['status'])
        messages.success(request, f"{profile.business_name} 파트너가 승인되었습니다.")
    elif action == 'reject':
        profile.user.status = 'inactive'
        profile.user.save(update_fields=['status'])
        messages.warning(request, f"{profile.business_name} 파트너가 반려되었습니다.")
    return redirect('portal:cs_partners')


@role_required('cs')
def chargers_list(request):
    stations = ChargingStation.objects.select_related('operator', 'site').order_by('station_id')
    status_filter = request.GET.get('status', '')
    q = request.GET.get('q', '')
    if status_filter:
        stations = stations.filter(status=status_filter)
    if q:
        stations = stations.filter(
            Q(station_id__icontains=q) | Q(address__icontains=q)
        )
    return render(request, 'portal/cs/chargers.html', {
        'stations': stations,
        'status_filter': status_filter,
        'q': q,
        'status_choices': ChargingStation.Status.choices,
    })


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
            messages.error(request, '충전소명과 파트너를 선택해 주세요.')
        else:
            partner = get_object_or_404(PartnerProfile, pk=partner_id)
            ChargingSite.objects.create(
                partner=partner,
                site_name=site_name,
                address=address,
                unit_price=unit_price,
            )
            messages.success(request, f"충전소 '{site_name}'이 등록되었습니다.")
            return redirect('portal:cs_sites')

    partners = PartnerProfile.objects.select_related('user').filter(user__status='active')
    return render(request, 'portal/cs/site_form.html', {'partners': partners})


@role_required('cs')
def sessions_list(request):
    sessions = Transaction.objects.select_related(
        'charging_station', 'id_token'
    ).order_by('-time_start')[:200]
    return render(request, 'portal/cs/sessions.html', {'sessions': sessions})


@role_required('cs')
def config_view(request):
    variables = CsmsVariable.objects.all().order_by('key')
    if request.method == 'POST':
        key = request.POST.get('key', '').strip()
        value = request.POST.get('value', '').strip()
        if key:
            CsmsVariable.objects.filter(key=key).update(
                value=value,
                updated_by=request.user.username,
            )
            messages.success(request, f"'{key}' 변수가 업데이트되었습니다.")
            return redirect('portal:cs_config')
    return render(request, 'portal/cs/config.html', {'variables': variables})
