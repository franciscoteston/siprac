from django.db.models import Q
from django.utils import timezone

from core.models import Servidor

# Ordem decrescente de hierarquia por nome de perfil (legado).
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

# Hierarquia por nível de visibilidade (menor = maior prioridade).
ORDEM_VISIBILIDADE = {
    "TOTAL": 0,
    "DEPARTAMENTO": 1,
    "UNIDADE": 2,
}


def _nivel_hierarquico(nome_perfil: str) -> int:
    try:
        return HIERARQUIA_PERFIS.index(nome_perfil)
    except ValueError:
        return len(HIERARQUIA_PERFIS)


def _vinculos_unidade_ativos(servidor: Servidor):
    hoje = timezone.localdate()
    return servidor.vinculos_unidade.filter(
        data_inicio__lte=hoje,
    ).filter(
        Q(data_fim__isnull=True) | Q(data_fim__gte=hoje),
    ).select_related("unidade", "perfil")


def servidor_tem_admin_sistema(servidor: Servidor) -> bool:
    """True se o servidor tem vínculo vigente com perfil admin_sistema."""
    hoje = timezone.localdate()
    return servidor.vinculos_unidade.filter(
        Q(data_fim__isnull=True) | Q(data_fim__gte=hoje),
        perfil__admin_sistema=True,
    ).exists()


def _escolher_vinculo_padrao(vinculos):
    """Escolhe vínculo por visibilidade (TOTAL > DEPARTAMENTO > UNIDADE), depois data_inicio."""
    if not vinculos:
        return None

    def chave(vinculo):
        visibilidade = getattr(vinculo.perfil, "visibilidade", "UNIDADE") or "UNIDADE"
        ordem = ORDEM_VISIBILIDADE.get(visibilidade, 99)
        data_inicio = vinculo.data_inicio
        # Mais recente primeiro (ordena crescente via negativo de ordinal)
        data_key = -(data_inicio.toordinal() if data_inicio else 0)
        return (ordem, data_key, vinculo.pk)

    return sorted(vinculos, key=chave)[0]


def obter_vinculo_unidade_ativo(servidor: Servidor):
    """Retorna o ServidorUnidade ativo de maior hierarquia de visibilidade."""
    vinculos_ativos = list(_vinculos_unidade_ativos(servidor))
    return _escolher_vinculo_padrao(vinculos_ativos)


def obter_perfil_acesso_ativo(servidor: Servidor):
    """Retorna o PerfilAcesso do vínculo ativo de maior hierarquia."""
    vinculo = obter_vinculo_unidade_ativo(servidor)
    if vinculo is None:
        return None
    return vinculo.perfil


class PerfilAcessoMiddleware:
    """Anexa o perfil/vínculo ativo do servidor autenticado à requisição."""

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        request.perfil_acesso = None
        request.admin_sistema = False
        request.vinculo_ativo = None
        request.vinculos_disponiveis = []
        request.visibilidade = "UNIDADE"
        request.servidor = None

        if request.user.is_authenticated:
            try:
                servidor = request.user.servidor
            except Servidor.DoesNotExist:
                servidor = None

            if servidor is not None:
                request.servidor = servidor
                vinculos = list(_vinculos_unidade_ativos(servidor))
                request.vinculos_disponiveis = vinculos

                vinculo = None
                session_id = request.session.get("vinculo_ativo_id")
                if session_id:
                    try:
                        session_id = int(session_id)
                    except (TypeError, ValueError):
                        session_id = None
                    if session_id is not None:
                        vinculo = next(
                            (v for v in vinculos if v.pk == session_id),
                            None,
                        )

                if vinculo is None:
                    vinculo = _escolher_vinculo_padrao(vinculos)
                    if vinculo is not None:
                        request.session["vinculo_ativo_id"] = vinculo.pk

                request.vinculo_ativo = vinculo
                request.perfil_acesso = vinculo.perfil if vinculo else None
                request.admin_sistema = servidor_tem_admin_sistema(servidor)
                visibilidade = None
                if request.perfil_acesso is not None:
                    visibilidade = getattr(
                        request.perfil_acesso,
                        "visibilidade",
                        None,
                    )

                # Corrigir visibilidade DEPARTAMENTO para vínculos operacionais
                # Se o perfil é DEPARTAMENTO mas a unidade ativa é OPERACIONAL,
                # a visibilidade efetiva é UNIDADE
                if visibilidade == "DEPARTAMENTO" and request.vinculo_ativo:
                    unidade = request.vinculo_ativo.unidade
                    tipo_unidade = getattr(unidade, "tipo", "OPERACIONAL")
                    if tipo_unidade == "OPERACIONAL":
                        visibilidade = "UNIDADE"

                if visibilidade not in ("UNIDADE", "DEPARTAMENTO", "TOTAL"):
                    if request.perfil_acesso and getattr(
                        request.perfil_acesso,
                        "visibilidade_total",
                        False,
                    ):
                        visibilidade = "TOTAL"
                    else:
                        visibilidade = "UNIDADE"

                request.visibilidade = visibilidade

        return self.get_response(request)
