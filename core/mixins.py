from django.contrib.auth.mixins import LoginRequiredMixin
from django.core.exceptions import PermissionDenied
from django.http import JsonResponse


class RequerLoginMixin(LoginRequiredMixin):
    """Redireciona para login se o usuário não estiver autenticado."""

    pass


class RequerLoginJSONMixin(LoginRequiredMixin):
    """Exige login e retorna JSON 401 em vez de redirect (para APIs fetch)."""

    def handle_no_permission(self):
        return JsonResponse({"error": "Autenticação necessária."}, status=401)


class RequerAdminMixin(RequerLoginMixin):
    """Exige permissão admin_sistema em algum vínculo ativo do servidor."""

    def dispatch(self, request, *args, **kwargs):
        if not request.user.is_authenticated:
            return self.handle_no_permission()
        if not getattr(request, "admin_sistema", False):
            raise PermissionDenied
        return super(RequerLoginMixin, self).dispatch(request, *args, **kwargs)
