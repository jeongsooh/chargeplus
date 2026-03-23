from django.shortcuts import render, redirect
from django.contrib.auth import authenticate, login, logout
from django.contrib import messages
from django.utils.translation import gettext as _
from django.views.decorators.http import require_http_methods

from apps.users.models import User, PartnerProfile


@require_http_methods(['GET', 'POST'])
def login_view(request):
    if request.user.is_authenticated:
        return _redirect_by_role(request.user)

    if request.method == 'POST':
        username = request.POST.get('username', '').strip()
        password = request.POST.get('password', '')
        user = authenticate(request, username=username, password=password)
        if user is None:
            messages.error(request, _('아이디 또는 비밀번호가 올바르지 않습니다.'))
            return render(request, 'portal/auth/login.html')
        if user.status != 'active':
            messages.error(request, _('계정이 활성화되어 있지 않습니다. 관리자 승인을 기다려 주세요.'))
            return render(request, 'portal/auth/login.html')
        login(request, user)
        return _redirect_by_role(user)

    return render(request, 'portal/auth/login.html')


def logout_view(request):
    logout(request)
    return redirect('portal:login')


def register_select(request):
    return render(request, 'portal/auth/register_select.html')


@require_http_methods(['GET', 'POST'])
def register_customer(request):
    if request.method == 'POST':
        username = request.POST.get('username', '').strip()
        password = request.POST.get('password', '')
        password2 = request.POST.get('password2', '')
        email = request.POST.get('email', '').strip()
        first_name = request.POST.get('first_name', '').strip()
        phone = request.POST.get('phone', '').strip()

        error = _validate_registration(username, password, password2)
        if error:
            messages.error(request, error)
            return render(request, 'portal/auth/register_customer.html')

        user = User.objects.create_user(
            username=username,
            password=password,
            email=email,
            first_name=first_name,
            phone=phone,
            role=User.Role.CUSTOMER,
            status=User.PortalStatus.ACTIVE,
        )
        login(request, user)
        messages.success(request, _('가입을 환영합니다!'))
        return redirect('portal:customer_dashboard')

    return render(request, 'portal/auth/register_customer.html')


@require_http_methods(['GET', 'POST'])
def register_partner(request):
    if request.method == 'POST':
        username = request.POST.get('username', '').strip()
        password = request.POST.get('password', '')
        password2 = request.POST.get('password2', '')
        email = request.POST.get('email', '').strip()
        first_name = request.POST.get('first_name', '').strip()
        phone = request.POST.get('phone', '').strip()
        business_name = request.POST.get('business_name', '').strip()
        business_no = request.POST.get('business_no', '').strip()
        contact_phone = request.POST.get('contact_phone', '').strip()

        error = _validate_registration(username, password, password2)
        if not business_name:
            error = _('사업체명을 입력해 주세요.')
        if not business_no:
            error = _('사업자번호를 입력해 주세요.')
        if error:
            messages.error(request, error)
            return render(request, 'portal/auth/register_partner.html')

        user = User.objects.create_user(
            username=username,
            password=password,
            email=email,
            first_name=first_name,
            phone=phone,
            role=User.Role.PARTNER,
            status=User.PortalStatus.PENDING,
        )
        PartnerProfile.objects.create(
            user=user,
            business_name=business_name,
            business_no=business_no,
            contact_phone=contact_phone,
        )
        messages.success(request, _('파트너 가입 신청이 완료되었습니다. 관리자 승인 후 이용하실 수 있습니다.'))
        return redirect('portal:login')

    return render(request, 'portal/auth/register_partner.html')


@require_http_methods(['GET', 'POST'])
def register_cs(request):
    if request.method == 'POST':
        username = request.POST.get('username', '').strip()
        password = request.POST.get('password', '')
        password2 = request.POST.get('password2', '')
        email = request.POST.get('email', '').strip()
        first_name = request.POST.get('first_name', '').strip()
        phone = request.POST.get('phone', '').strip()

        error = _validate_registration(username, password, password2)
        if error:
            messages.error(request, error)
            return render(request, 'portal/auth/register_cs.html')

        User.objects.create_user(
            username=username,
            password=password,
            email=email,
            first_name=first_name,
            phone=phone,
            role=User.Role.CS,
            status=User.PortalStatus.PENDING,
        )
        messages.success(request, _('고객센터 가입 신청이 완료되었습니다. Django 관리자 승인 후 이용하실 수 있습니다.'))
        return redirect('portal:login')

    return render(request, 'portal/auth/register_cs.html')


# --- helpers ---

def _redirect_by_role(user):
    role_urls = {
        'cs':       'portal:cs_dashboard',
        'partner':  'portal:partner_dashboard',
        'customer': 'portal:customer_dashboard',
    }
    from django.urls import reverse
    return redirect(reverse(role_urls.get(user.role, 'portal:login')))


def _validate_registration(username, password, password2):
    if not username:
        return _('아이디를 입력해 주세요.')
    if User.objects.filter(username=username).exists():
        return _('이미 사용 중인 아이디입니다.')
    if len(password) < 8:
        return _('비밀번호는 8자 이상이어야 합니다.')
    if password != password2:
        return _('비밀번호가 일치하지 않습니다.')
    return None
