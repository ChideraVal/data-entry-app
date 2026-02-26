from functools import wraps
from django.core.exceptions import PermissionDenied
from django.http import JsonResponse

class Roles:
    SUPER_ADMIN = "super admin"
    ADMIN = "admin"
    MEMBER = "member"


class ViewType:
    HTML = "html"
    JSON = "json"


def _handle_denied(view_type, message):
    if view_type == "json":
        return JsonResponse({
            "success": False,
            "error": message
        })
    
    # default: html
    raise PermissionDenied(message)

def require_roles(allowed_roles, view_type="html"):
    def decorator(view_func):
        @wraps(view_func)
        def _wrapped_view(request, *args, **kwargs):
            user = request.user
            if not user.is_authenticated:
                return _handle_denied(view_type, "Authentication required")
            
            if user.role not in allowed_roles:
                return _handle_denied(view_type, "Permission denied")
            
            return view_func(request, *args, **kwargs)
        return _wrapped_view
    return decorator

def block_roles(blocked_roles, view_type="html"):
    def decorator(view_func):
        @wraps(view_func)
        def _wrapped_view(request, *args, **kwargs):
            user = request.user
            if not user.is_authenticated:
                return _handle_denied(view_type, "Authentication required")
            
            if user.role in blocked_roles:
                return _handle_denied(view_type, "Permission denied")
            
            return view_func(request, *args, **kwargs)
        return _wrapped_view
    return decorator
