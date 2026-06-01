# SGBD DAI — Sistema de Gerenciamento da Divisão de Avaliação de Imóveis

> **SIPRAC** — Sistema de Processos, Acompanhamento e Cronogramas

Sistema de gerenciamento de processos e produção técnica da Divisão de Avaliação de Imóveis (DAI) da Prefeitura Municipal de Porto Alegre. Desenvolvido para operar em complemento ao SEI, oferecendo rastreamento detalhado em nível operacional e gerencial.

---

## Problema que o sistema resolve

O SEI trata o número do processo como entidade central. Quando um trabalho técnico atende a múltiplos processos simultaneamente, ele precisa ser registrado individualmente para cada processo — gerando retrabalho. O SGBD DAI inverte essa lógica: a **Ordem de Serviço** é a entidade central, e pode se vincular a múltiplos processos SEI e imóveis ao mesmo tempo.

---

## Funcionalidades principais

- Gestão completa do ciclo de vida de Ordens de Serviço (OS)
- Rastreamento de encaminhamentos internos e externos com trilha de auditoria
- Registro de produção técnica (laudos, plantas, pareceres, despachos) vinculada a múltiplas OSs e imóveis
- Cadastro de imóveis com ou sem inscrição cadastral (ISIC), com integração via View do SIAT
- Dados técnicos por imóvel e por exercício, separados dos dados de referência
- Controle de acesso por perfil com permissões temporárias e vínculos com vigência
- Dashboard gerencial com indicadores de produtividade, prazos e processos abertos
- Módulo de pesquisa de dados com controle de metas semanais e mensais

---

## Stack tecnológica

| Componente | Tecnologia |
|---|---|
| Banco de dados | PostgreSQL |
| Backend | Python 3.12+ / Django 6+ |
| Servidor web | Nginx + Gunicorn |
| Protótipo / homologação | Railway |
| Produção | Servidor PROCEMPA (a definir) |
| Versionamento | GitHub |
| Gestão de tarefas | GitHub Projects |
| Codificação assistida | Cursor |

---

## Arquitetura

O modelo de dados é composto por **26 entidades** organizadas em cinco domínios:

| Domínio | Entidades |
|---|---|
| Estrutura e segurança | SERVIDOR, UNIDADE_INTERNA, SERVIDOR_UNIDADE, PERFIL_ACESSO, PERMISSAO_ESPECIAL |
| Externo | UNIDADE_EXTERNA |
| Classificação | NATUREZA, TIPO_DEMANDA, FINALIDADE, COMBINACAO_VALIDA |
| Imóveis | IMOVEL, OS_IMOVEL, PRODUCAO_IMOVEL, PRODUCAO_IMOVEL_DADOS |
| OS e ciclo de vida | OS, PROCESSO_SEI, OS_PROCESSO, MACROETAPA_LOG, ENCAMINHAMENTO, TAREFA_INTERNA |
| Produção | PRODUCAO, PRODUCAO_ATRIBUTO, TIPO_PRODUCAO |
| Pesquisa | REGISTRO_PESQUISA, META_PESQUISA |
| Auditoria | LOG_AUDITORIA |

Documentação detalhada:
- [`docs/ARQUITETURA.md`](docs/ARQUITETURA.md) — decisões, regras de negócio, perfis de acesso, política de datas e auditoria
- [`docs/DIAGRAMA_ER.md`](docs/DIAGRAMA_ER.md) — diagrama entidade-relacionamento completo em três blocos

---

## Unidades internas

| Sigla | Nome |
|---|---|
| DAI | Divisão de Avaliação de Imóveis |
| EAV | Equipe de Avaliações |
| ESJL | Equipe de Suporte, Judiciais e Locações |
| EPGV | Equipe Genérica da Planta de Valores |

---

## Roadmap de desenvolvimento

- [x] **Fase 1 — Fundação:** configuração do ambiente, modelagem Django ORM, Django Admin para entidades de domínio
- [ ] **Fase 2 — Núcleo operacional:** criação e tramitação de OS, macroetapas, encaminhamentos, controle de acesso
- [ ] **Fase 3 — Produção e imóveis:** cadastro de imóveis, integração SIAT, registro de produções, agrupamentos
- [ ] **Fase 4 — Dashboard e relatórios:** painéis gerenciais, produtividade, módulo de pesquisa e metas
- [ ] **Fase 5 — Auditoria e refinamentos:** log completo, revisão de regras de negócio, documentação de manutenção

---

## Questões pendentes para implantação

- [ ] Sistema operacional do servidor PROCEMPA
- [ ] Responsabilidades de infraestrutura (backup, atualizações, monitoramento)
- [ ] Prazo máximo de OS interna sem processo SEI antes de gerar alerta
- [ ] Catálogo completo de Naturezas, Tipos de Demanda e Finalidades
- [ ] Política de retenção dos logs de auditoria (verificar normativa municipal)
- [ ] Modelo de notificações de encaminhamento (além do painel)

---

## Contexto institucional

- **Órgão:** Prefeitura Municipal de Porto Alegre
- **Unidade:** Divisão de Avaliação de Imóveis (DAI)
- **Sistema complementar:** SEI — Sistema Eletrônico de Informações
- **Infraestrutura:** PROCEMPA — Companhia de Processamento de Dados do Município
- **Usuários previstos:** 28 servidores (expansão para 35)
- **Volume estimado:** ~1.000 processos/ano
