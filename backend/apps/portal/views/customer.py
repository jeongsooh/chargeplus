from django.core.paginator import Paginator
from django.shortcuts import render, get_object_or_404, redirect
from django.contrib import messages
from django.utils.translation import gettext as _
from django.views.decorators.http import require_http_methods

from apps.portal.decorators import role_required
from apps.authorization.models import IdToken
from apps.transactions.models import Transaction


@role_required('customer')
def dashboard(request):
    recent = Transaction.objects.filter(
        id_token__user=request.user, state='Completed'
    ).order_by('-time_start')[:5]
    cards = IdToken.objects.filter(user=request.user)
    return render(request, 'portal/customer/dashboard.html', {
        'recent_sessions': recent,
        'cards': cards,
    })


@role_required('customer')
def history(request):
    sessions = Transaction.objects.filter(
        id_token__user=request.user
    ).select_related('charging_station').order_by('-time_start')
    return render(request, 'portal/customer/history.html', {'sessions': sessions})


@role_required('customer')
def cards_list(request):
    cards = IdToken.objects.filter(user=request.user).order_by('-created_at')
    return render(request, 'portal/customer/cards.html', {'cards': cards})


@role_required('customer')
@require_http_methods(['POST'])
def card_add(request):
    id_token_val = request.POST.get('id_token', '').strip().upper()
    if not id_token_val:
        messages.error(request, _('카드 번호를 입력해 주세요.'))
        return redirect('portal:customer_cards')
    if IdToken.objects.filter(id_token=id_token_val).exists():
        messages.error(request, _('이미 등록된 카드 번호입니다.'))
        return redirect('portal:customer_cards')
    IdToken.objects.create(
        id_token=id_token_val,
        token_type='RFID',
        status='Accepted',
        user=request.user,
    )
    messages.success(request, _(f"카드 {id_token_val}가 등록되었습니다."))
    return redirect('portal:customer_cards')


@role_required('customer')
@require_http_methods(['POST'])
def card_delete(request, token_id):
    card = get_object_or_404(IdToken, id_token=token_id, user=request.user)
    card.delete()
    messages.success(request, _('카드가 삭제되었습니다.'))
    return redirect('portal:customer_cards')


@role_required('customer')
def payments_list(request):
    from apps.payment.models import PaymentTransaction

    qs = PaymentTransaction.objects.filter(user=request.user).order_by('-created_at')

    status_q = request.GET.get('status_q', '')
    if status_q:
        qs = qs.filter(status=status_q)

    paginator = Paginator(qs, 20)
    page = paginator.get_page(request.GET.get('page', 1))

    from apps.payment.models import PaymentTransaction as PT
    return render(request, 'portal/customer/payments.html', {
        'page': page,
        'status_q': status_q,
        'status_choices': PT.Status.choices,
    })


@role_required('customer')
def profile_view(request):
    if request.method == 'POST':
        user = request.user
        user.first_name = request.POST.get('first_name', '').strip()
        user.email = request.POST.get('email', '').strip()
        user.phone = request.POST.get('phone', '').strip()

        new_password = request.POST.get('new_password', '')
        if new_password:
            if len(new_password) < 8:
                messages.error(request, _('비밀번호는 8자 이상이어야 합니다.'))
                return render(request, 'portal/customer/profile.html')
            user.set_password(new_password)

        user.save()
        messages.success(request, _('프로필이 업데이트되었습니다.'))
        if new_password:
            from django.contrib.auth import update_session_auth_hash
            update_session_auth_hash(request, user)
        return redirect('portal:customer_profile')

    return render(request, 'portal/customer/profile.html')
