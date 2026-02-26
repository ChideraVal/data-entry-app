from django.shortcuts import redirect

def enforce_password_change_middleware(get_response):
    def inner(request):
        print(f'Hello there, request to {request.get_full_path()}.')
        response = get_response(request)
        
        user = request.user
        
        if not user.is_authenticated:
            return redirect("signin")
        
        if not user.has_changed_password:
            return redirect("change_password")
        
        return response
    return inner
