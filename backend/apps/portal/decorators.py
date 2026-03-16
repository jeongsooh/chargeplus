from functools import wraps
from django.shortcuts import redirect
from django.contrib import messages


def login_required_portal(view_func):
    """Redirect to portal login if not authenticated."""
    @wraps(view_func)
    def wrapper(request, *args, **kwargs):
        if not request.user.is_authenticated:
            return redirect('portal:login')
        return view_func(request, *args, **kwargs)
    return wrapper


def role_required(*roles):
    """Allow access only to users with one of the specified roles."""
    def decorator(view_func):
        @wraps(view_func)
        def wrapper(request, *args, **kwargs):
            if not request.user.is_authenticated:
                return redirect('portal:login')
            if request.user.role not in roles:
                messages.error(request, '접근 권한이 없습니다.')
                return redirect('portal:login')
            if request.user.status != 'active':
                messages.error(request, '계정이 활성화되어 있지 않습니다. 관리자 승인을 기다려 주세요.')
                return redirect('portal:login')
            return view_func(request, *args, **kwargs)
        return wrapper
    return decorator
