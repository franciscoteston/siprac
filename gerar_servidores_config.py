import os, sys, django, json
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'siprac.settings')
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
django.setup()

from core.models import Servidor, ServidorUnidade

dados = []
for srv in Servidor.objects.all().order_by('login'):
    vinculos = (
        ServidorUnidade.objects.filter(servidor=srv, data_fim__isnull=True)
        .select_related('unidade', 'perfil')
        .order_by('unidade__sigla')
    )

    if vinculos.exists():
        for vinculo in vinculos:
            dados.append({
                'login': srv.login,
                'nome': srv.nome,
                'unidade': vinculo.unidade.sigla,
                'perfil': vinculo.perfil.nome,
                'cargo': vinculo.cargo or '',
                'data_inicio': (
                    vinculo.data_inicio.isoformat()
                    if vinculo.data_inicio
                    else '2026-01-01'
                ),
            })
    else:
        dados.append({
            'login': srv.login,
            'nome': srv.nome,
            'unidade': '',
            'perfil': '',
            'cargo': '',
            'data_inicio': '2026-01-01',
        })

with open('servidores_config.json', 'w', encoding='utf-8') as f:
    json.dump(dados, f, indent=2, ensure_ascii=False)
    f.write('\n')

print(f'Gerado: {len(dados)} vinculos em servidores_config.json')
