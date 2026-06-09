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


def RequerPerfilMixin(perfis_permitidos):
    """Factory que retorna um mixin restrito aos nomes de perfil informados."""

    perfis = tuple(perfis_permitidos)

    class _RequerPerfilMixin(RequerLoginMixin):
        def dispatch(self, request, *args, **kwargs):
            perfil = getattr(request, "perfil_acesso", None)
            if perfil is None or perfil.nome not in perfis:
                raise PermissionDenied
            return super().dispatch(request, *args, **kwargs)

    return _RequerPerfilMixin


class RequerCriarOSMixin(RequerLoginMixin):
    """Exige permissão pode_criar_os no perfil ativo."""

    def dispatch(self, request, *args, **kwargs):
        perfil = getattr(request, "perfil_acesso", None)
        if perfil is None or not perfil.pode_criar_os:
            raise PermissionDenied
        return super().dispatch(request, *args, **kwargs)


class RequerEncerrarOSMixin(RequerLoginMixin):
    """Exige permissão pode_encerrar_os no perfil ativo."""

    def dispatch(self, request, *args, **kwargs):
        perfil = getattr(request, "perfil_acesso", None)
        if perfil is None or not perfil.pode_encerrar_os:
            raise PermissionDenied
        return super().dispatch(request, *args, **kwargs)


class RequerHomologarMixin(RequerLoginMixin):
    """Exige permissão pode_homologar no perfil ativo."""

    def dispatch(self, request, *args, **kwargs):
        perfil = getattr(request, "perfil_acesso", None)
        if perfil is None or not perfil.pode_homologar:
            raise PermissionDenied
        return super().dispatch(request, *args, **kwargs)


class RequerAdminMixin(RequerLoginMixin):
    """Exige permissão admin_sistema em algum vínculo ativo do servidor."""

    def dispatch(self, request, *args, **kwargs):
        if not request.user.is_authenticated:
            return self.handle_no_permission()
        if not getattr(request, "admin_sistema", False):
            raise PermissionDenied
        return super(RequerLoginMixin, self).dispatch(request, *args, **kwargs)
