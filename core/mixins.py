from django.contrib.auth.mixins import LoginRequiredMixin
from django.core.exceptions import PermissionDenied


class RequerLoginMixin(LoginRequiredMixin):
    """Redireciona para login se o usuário não estiver autenticado."""

    pass


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
    """Exige permissão admin_sistema no perfil ativo."""

    def dispatch(self, request, *args, **kwargs):
        perfil = getattr(request, "perfil_acesso", None)
        if perfil is None or not perfil.admin_sistema:
            raise PermissionDenied
        return super().dispatch(request, *args, **kwargs)
