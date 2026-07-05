# Manutenção do SIPRAC no Railway

## Acesso ao assistente do Railway

Acesse o projeto em: https://railway.com/project/51e0818d-389d-4e67-9d27-9dc299be1187

Para executar comandos, use o chat do assistente do Railway.

---

## 1. Novo deploy (atualização de código)

Após qualquer push para o main, disparar deploy manualmente.
Cole no chat do Railway:

    Please trigger a new deployment for the siprac-web service using
    the latest commit from the main branch.

As migrações Django rodam automaticamente via start.sh.
Os dados existentes no banco são preservados.

---

## 2. Atualizar usuários e vínculos

Quando houver novo servidor, alteração de perfil ou unidade.

### Passo 1 — Gerar arquivos localmente

    $env:DATABASE_URL = "postgres://postgres:SENHA@127.0.0.1:5432/siprac"
    $env:PGCLIENTENCODING = "UTF8"
    python gerar_servidores_config.py
    python manage.py exportar_hashes_senha --output hashes_senha.json

### Passo 2 — Verificar encoding (deve começar com 91 13 10)

    $bytes = [System.IO.File]::ReadAllBytes("servidores_config.json")
    $bytes[0..2]
    $bytes = [System.IO.File]::ReadAllBytes("hashes_senha.json")
    $bytes[0..2]

### Passo 3 — Commitar e fazer push

    git add servidores_config.json hashes_senha.json
    git commit -m "chore: atualiza configuração de usuários"
    git push origin main

### Passo 4 — Cole no chat do Railway

    Please add preDeployCommand: python manage.py setup_railway
    Then trigger a new deployment for the siprac-web service using
    the latest commit from the main branch.

### Passo 5 — Após confirmar sucesso nos Deploy Logs

    Please remove the preDeployCommand from the siprac-web service configuration.

### Passo 6 — Remover arquivos temporários

    git rm servidores_config.json hashes_senha.json
    git commit -m "chore: remove arquivos temporários de usuários"
    git push origin main

---

## 3. Resetar dados operacionais (preserva configuração)

Apaga OS, produções, imóveis, encaminhamentos etc.
Preserva: perfis, unidades, naturezas, requerimentos, finalidades,
tipos de produção, usuários e vínculos.

### Passo 1 — Cole no chat do Railway

    Please add preDeployCommand: python manage.py resetar_banco_railway --confirmar
    Then trigger a new deployment for the siprac-web service using
    the latest commit from the main branch.

### Passo 2 — Após confirmar sucesso

    Please remove the preDeployCommand from the siprac-web service configuration.

---

## 4. Reset completo do banco (domínio + usuários + dados)

Use apenas quando necessário recriar tudo do zero.

### Passo 1 — Gerar dumps localmente

    $env:DATABASE_URL = "postgres://postgres:SENHA@127.0.0.1:5432/siprac"
    $env:PGCLIENTENCODING = "UTF8"
    python -c "
    import os, django
    from django.core import serializers
    os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'siprac.settings')
    django.setup()
    from core.models import (Natureza, TipoDemanda, Finalidade, CombinacaoValida,
        TipoProducao, UnidadeInterna, UnidadeExterna, PerfilAcesso)
    queryset = (list(PerfilAcesso.objects.all()) +
        list(UnidadeInterna.objects.all()) +
        list(UnidadeExterna.objects.all()) +
        list(Natureza.objects.all()) +
        list(TipoDemanda.objects.all()) +
        list(Finalidade.objects.all()) +
        list(CombinacaoValida.objects.all()) +
        list(TipoProducao.objects.all()))
    with open('dump_dominio.json', 'w', encoding='utf-8') as f:
        f.write(serializers.serialize('json', queryset, indent=2))
    print(f'Gerado: {len(queryset)} objetos')
    "
    python gerar_servidores_config.py
    python manage.py exportar_hashes_senha --output hashes_senha.json

### Passo 2 — Verificar encodings

    foreach ($f in @("dump_dominio.json","servidores_config.json","hashes_senha.json")) {
        $b = [System.IO.File]::ReadAllBytes($f)
        Write-Host "$f : $($b[0]) $($b[1]) $($b[2]) (deve ser 91 13 10)"
    }

### Passo 3 — Commitar

    git add dump_dominio.json servidores_config.json hashes_senha.json
    git commit -m "chore: dumps para reset completo do Railway"
    git push origin main

### Passo 4 — Cole no chat do Railway

    Please add preDeployCommand: python manage.py loaddata dump_dominio.json && python manage.py resetar_banco_railway --confirmar --incluir-usuarios
    Then trigger a new deployment for the siprac-web service using
    the latest commit from the main branch.

### Passo 5 — Após confirmar sucesso

    Please remove the preDeployCommand from the siprac-web service configuration.

### Passo 6 — Remover arquivos temporários

    git rm dump_dominio.json servidores_config.json hashes_senha.json
    git commit -m "chore: remove dumps temporários após reset"
    git push origin main

---

## 5. Carregar arquivo SIAT após novo deploy

O arquivo siat_view.txt fica no volume persistente do Railway
(siprac-web-data, montado em /app/data).

Se o volume foi recriado ou o arquivo foi perdido:

1. Acesse: https://siprac-web-production.up.railway.app/admin-siprac/carregar-siat/
2. Faça upload do arquivo SIAT completo
3. Aguarde a mensagem de confirmação e o índice carregar (~1-2 min)

Verifique se o índice carregou:

    https://siprac-web-production.up.railway.app/api/siat/status-indice/

---

## 6. Variáveis de ambiente configuradas no Railway

| Variável | Descrição |
|---|---|
| DATABASE_URL | Gerada automaticamente pelo PostgreSQL do Railway |
| SECRET_KEY | Chave secreta do Django |
| DEBUG | False (produção) |
| ALLOWED_HOSTS | siprac-web-production.up.railway.app |
| SIAT_INDEX_LOGRADOURO | False (economiza memória) |

---

## 7. Senhas padrão

Após setup_railway, todos os usuários usam a senha exportada
do ambiente local via hashes_senha.json.

Para redefinir todas as senhas para um valor temporário:

    Please add environment variable SENHA_PADRAO=NovaSenha123!
    Please add preDeployCommand: python manage.py redefinir_senhas
    Then trigger a new deployment for the siprac-web service using
    the latest commit from the main branch.

Após confirmar, remover preDeployCommand e variável SENHA_PADRAO.
