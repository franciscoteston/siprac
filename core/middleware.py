from django.db.models import Q
from django.utils import timezone

from core.models import Servidor

# Ordem decrescente de hierarquia (índice menor = maior nível).
HIERARQUIA_PERFIS = (
    "Administrador",
    "Diretor",
    "Aux. Téc. Direção",
    "Coordenador",
    "Aux. Téc. Coord.",
    "Técnico",
    "Aux. Adm. Gestão",
    "Aux. Adm. Pesquisa",
)


def _nivel_hierarquico(nome_perfil: str) -> int:
    try:
        return HIERARQUIA_PERFIS.index(nome_perfil)
    except ValueError:
        return len(HIERARQUIA_PERFIS)


def obter_perfil_acesso_ativo(servidor: Servidor):
    """Retorna o PerfilAcesso do vínculo ativo de maior hierarquia."""
    hoje = timezone.localdate()
    vinculos_ativos = servidor.vinculos_unidade.filter(
        Q(data_fim__isnull=True) | Q(data_fim__gte=hoje),
    ).select_related("perfil")

    vinculo_escolhido = None
    melhor_nivel = len(HIERARQUIA_PERFIS)

    for vinculo in vinculos_ativos:
        nivel = _nivel_hierarquico(vinculo.perfil.nome)
        if nivel < melhor_nivel:
            melhor_nivel = nivel
            vinculo_escolhido = vinculo

    if vinculo_escolhido is None:
        return None
    return vinculo_escolhido.perfil


class PerfilAcessoMiddleware:
    """Anexa o perfil de acesso ativo do servidor autenticado à requisição."""

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        request.perfil_acesso = None

        if request.user.is_authenticated:
            try:
                servidor = request.user.servidor
            except Servidor.DoesNotExist:
                servidor = None

            if servidor is not None:
                request.perfil_acesso = obter_perfil_acesso_ativo(servidor)

        return self.get_response(request)
