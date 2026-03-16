from django.shortcuts import render, get_object_or_404, redirect
from django.contrib import messages
from django.db.models import Sum, Count, Q
from django.utils import timezone

from apps.portal.decorators import role_required
from apps.stations.models import ChargingStation, ChargingSite
from apps.transactions.models import Transaction


@role_required('partner')
def dashboard(request):
    profile = request.user.partner_profile
    sites = ChargingSite.objects.filter(partner=profile).annotate(
        station_count=Count('stations')
    )
    now = timezone.now()
    month_start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)

    station_ids = ChargingStation.objects.filter(
        site__partner=profile
    ).values_list('id', flat=True)

    month_stats = Transaction.objects.filter(
        charging_station_id__in=station_ids,
        state='Completed',
        time_start__gte=month_start,
    ).aggregate(
        energy=Sum('energy_kwh'),
        amount=Sum('amount'),
        count=Count('transaction_id'),
    )

    return render(request, 'portal/partner/dashboard.html', {
        'profile': profile,
        'sites': sites,
        'month_energy': month_stats['energy'] or 0,
        'month_amount': month_stats['amount'] or 0,
        'month_count': month_stats['count'] or 0,
    })


@role_required('partner')
def sites_list(request):
    profile = request.user.partner_profile
    sites = ChargingSite.objects.filter(partner=profile).annotate(
        station_count=Count('stations')
    ).order_by('site_name')
    return render(request, 'portal/partner/sites.html', {'sites': sites, 'profile': profile})


@role_required('partner')
def site_update_price(request, site_id):
    if request.method != 'POST':
        return redirect('portal:partner_sites')
    profile = request.user.partner_profile
    site = get_object_or_404(ChargingSite, pk=site_id, partner=profile)
    unit_price = request.POST.get('unit_price', '0')
    try:
        site.unit_price = float(unit_price)
        site.save(update_fields=['unit_price'])
        messages.success(request, f"'{site.site_name}' 충전단가가 업데이트되었습니다.")
    except ValueError:
        messages.error(request, '올바른 금액을 입력해 주세요.')
    return redirect('portal:partner_sites')


@role_required('partner')
def chargers_list(request):
    profile = request.user.partner_profile
    stations = ChargingStation.objects.filter(
        site__partner=profile
    ).select_related('site').prefetch_related('evses__connectors').order_by('station_id')
    return render(request, 'portal/partner/chargers.html', {
        'stations': stations,
        'profile': profile,
    })


@role_required('partner')
def stats_view(request):
    profile = request.user.partner_profile
    now = timezone.now()
    month_start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)

    # Previous month
    if month_start.month == 1:
        prev_month_start = month_start.replace(year=month_start.year - 1, month=12)
    else:
        prev_month_start = month_start.replace(month=month_start.month - 1)

    station_ids = ChargingStation.objects.filter(
        site__partner=profile
    ).values_list('id', flat=True)

    def _stats(start, end):
        return Transaction.objects.filter(
            charging_station_id__in=station_ids,
            state='Completed',
            time_start__gte=start,
            time_start__lt=end,
        ).aggregate(
            energy=Sum('energy_kwh'),
            amount=Sum('amount'),
            count=Count('transaction_id'),
        )

    curr = _stats(month_start, now)
    prev = _stats(prev_month_start, month_start)

    return render(request, 'portal/partner/stats.html', {
        'profile': profile,
        'curr': curr,
        'prev': prev,
        'month_label': month_start.strftime('%Y년 %m월'),
        'prev_month_label': prev_month_start.strftime('%Y년 %m월'),
    })
