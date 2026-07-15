# Arquitetura do SGBD — Divisão de Avaliação de Imóveis (DAI)

## 1. Contexto e motivação

A Divisão de Avaliação de Imóveis (DAI) da Prefeitura Municipal de Porto Alegre utiliza o Sistema Eletrônico de Informações (SEI) como sistema oficial de gerenciamento de processos. O SEI trata o número do processo como entidade central, exigindo que um mesmo trabalho seja registrado individualmente para cada processo ao qual se vincula — gerando retrabalho quando uma produção atende a múltiplos processos simultaneamente. O sistema é denominado SIPRAC — Sistema de Processos, Acompanhamento e Cronogramas.

O SGBD da DAI foi concebido para operar em complemento ao SEI, oferecendo gerenciamento detalhado em nível operacional e gerencial, sem replicar o SEI nem substituí-lo. A integração com o SEI é indireta: números de processo, documentos e despachos são registrados manualmente no SGBD, sem leitura automática do SEI.

---

## 2. Estrutura organizacional

### 2.1 Estrutura organizacional
A DAI é composta por uma unidade administrativa e quatro
unidades operacionais:

| Sigla | Nome | Tipo |
|---|---|---|
| DEPARTAMENTO | Divisão de Avaliação de Imóveis | Administrativa |
| DAI | Divisão de Avaliação de Imóveis (unidade técnica) | Operacional |
| EAV | Equipe de Avaliações | Operacional |
| ESJL | Equipe de Suporte, Judiciais e Locações | Operacional |
| EPGV | Equipe Genérica da Planta de Valores | Operacional |

O DEPARTAMENTO é a entidade administrativa representativa do
conjunto — o "condomínio" que agrupa as unidades operacionais.
Não executa trabalho técnico. Suas atribuições são:
- Criar OSs
- Registrar processos (principal e relacionados)
- Vincular imóveis
- Realizar o primeiro encaminhamento para unidades operacionais
- Incluir processos relacionados em qualquer momento

[PENDENTE IMPLEMENTAÇÃO] O DEPARTAMENTO será criado como
UnidadeInterna própria no sistema, com campo tipo='ADMINISTRATIVA'.
As demais unidades terão tipo='OPERACIONAL'.

### 2.2 Vínculos e vigência
Um servidor pode estar lotado em mais de uma unidade simultaneamente, ou assumir cargo temporário (ex: substituição de coordenador em férias). Esses vínculos são registrados com data de início e data de fim.

Um servidor pode ter mais de um vínculo ativo simultaneamente.
Exemplo: Sabrina Ibeiro possui vínculo com DEPARTAMENTO (papel
administrativo) e com ESJL (papel operacional).

[PENDENTE IMPLEMENTAÇÃO] O sistema exibirá um seletor de
perfil ativo na interface para servidores com mais de um
vínculo. Ao trocar o perfil ativo:
- A fila de OSs exibida muda conforme a unidade
- As ações disponíveis mudam conforme o perfil
- O perfil ativo fica registrado na sessão do usuário
- O login e senha permanecem os mesmos

### 2.3 Permissões especiais
Permissões temporárias (ex: visibilidade cross-unidade)
são concedidas pelo gestor com data_inicio e data_fim,
registradas em PermissaoEspecial.

### 2.4 Perfil ativo no middleware
O middleware PerfilAcessoMiddleware carrega o vínculo ativo
do servidor logado e o disponibiliza em request.vinculo_ativo
e request.perfil_acesso para uso nas views e templates.
Quando há mais de um vínculo, o sistema usa o de maior
hierarquia ou o selecionado pelo usuário na sessão.

---

## 3. Entidade central — Ordem de Serviço (OS)

A Ordem de Serviço é a entidade central do SGBD. Ela representa o ciclo de vida completo de uma demanda dentro da DAI, desde a entrada até o encerramento. Uma OS nasce obrigatoriamente a partir de um Processo SEI, com exceção das OSs internas (ver seção 3.2).

### 3.1 Numeração

A OS recebe numeração automática incremental no SGBD (ex: `OS_00001_2026`). Essa numeração é independente do SEI e existe apenas no âmbito da DAI.

### 3.2 OS interna

Uma OS pode ser criada sem vínculo com processo SEI para atender demandas internas antecipadas (ex: atualizar um modelo de regressão antes da chegada formal do processo). Regras:

- Somente servidores com cargo hierárquico podem criar OS interna
- A OS interna fica com status `PENDENTE_CONFIRMACAO` até que um segundo usuário autorizado confirme que a ausência de processo SEI é intencional
- Ao vincular um processo SEI a uma OS interna, ela passa a ser tratada como OS normal
- OSs internas sem processo SEI por mais de X dias geram alerta para o gestor da unidade criadora (prazo a definir na implantação)

### 3.3 Classificação

Cada OS é classificada em três dimensões independentes, em cascata:

- **Natureza:** ex: Tributário – IPTU, Tributário – ITBI, Não tributário
- **Requerimento:** ex: Requerimento IPTU, Requerimento Desapropriação, Ofício
- **Finalidade:** ex: Desapropriação Parcial, Desapropriação Total, Revisão do Valor Venal

Há combinações inválidas entre as três dimensões (ex: Não tributário + IPTU é inválido). O controle é feito por uma tabela `COMBINACAO_VALIDA`, administrada pelo administrador do sistema. A interface apresenta as opções em cascata — ao selecionar a Natureza, os Requerimentos válidos são filtrados automaticamente, e assim por diante.

### 3.4 Prioridade

Campo simples com três valores: `NORMAL`, `PRIORITARIO`, `URGENTE`. Padrão: `NORMAL`. Alterações de prioridade são registradas em auditoria.

### 3.5 Processos SEI vinculados

Uma OS pode estar vinculada a mais de um processo SEI. O primeiro vínculo é o processo principal (`tipo_vinculo = PRINCIPAL`). Demais vínculos são processos relacionados (`tipo_vinculo = RELACIONADO`), incluídos via macroetapa "Inclusão de Processo Relacionado".

Cada processo vinculado tem data de entrada na Divisão e data de encerramento próprias. Um processo relacionado pode ser encerrado antes da OS ser encerrada — situação relevante para o Dashboard na contagem de processos abertos.

---

## 4. Macroetapas

### 4.1 Implementação atual das macroetapas
O modelo MacroetapaLog foi eliminado e marcado como DEPRECATED.
A macroetapa atual da OS é derivada dos Encaminhamentos:
- Campo Encaminhamento.tipo_macroetapa registra a macroetapa
  de cada transição
- OS.encerrada (bool) e OS.data_encerramento substituem
  o log de encerramento
- A função macroetapa_atual_os() em core/os_service.py
  retorna a macroetapa atual derivada do último encaminhamento
- A função timeline_os() retorna a timeline unificada

### 4.2 Tabela de macroetapas
| # | Macroetapa | Código | Regra de transição | Situação |
|---|---|---|---|---|
| 1 | Entrada na Divisão | ENTRADA_DIVISAO | Estado inicial — criação da OS | ✓ Implementado |
| 2 | Atendimento Interno | ATENDIMENTO_INTERNO | Após encaminhamento para unidade interna | ✓ Implementado |
| 3 | Atendimento Externo | ATENDIMENTO_EXTERNO | Após encaminhamento para unidade externa | ✓ Implementado |
| 4 | Retorno Externo | RETORNO_EXTERNO | Somente após Atendimento Externo | ✓ Implementado |
| 5 | Inclusão de Processo | INCLUSAO_PROCESSO | Qualquer estado exceto Encerrada | ✓ Implementado |
| 6 | Reabertura | — | Somente após Encerrada | [PENDENTE IMPLEMENTAÇÃO] |
| 7 | Encerrado | OS.encerrada=True | Estado final | ✓ Implementado |

### 4.3 Reabertura
Distinguir claramente dois tipos:

Reabertura na unidade (já implementada):
- Modelo: OsUnidadeStatus.status = REABERTA
- Quem pode: chefia da unidade
- Efeito: OS volta a ser editável na unidade
- View: OSReabrirNaUnidadeView

Reabertura global da OS (pendente — ver §15.18):
- Significaria OS.encerrada = False
- Não implementada
- Perfil que poderá fazer: Direção/Administrador

### 4.4 Macroetapa automática ao registrar produção
A função ativar_atendimento_interno_se_necessario() em
core/os_service.py registra automaticamente um encaminhamento
com tipo_macroetapa=ATENDIMENTO_INTERNO quando uma produção
é criada e a OS ainda não tem macroetapa de atendimento.

### 4.5 Encaminhamento sem tipo_macroetapa
Quando tipo_macroetapa é nulo, a macroetapa é derivada
pelo destino do encaminhamento:
- unidade_interna_destino preenchida → ATENDIMENTO_INTERNO
- unidade_externa_destino preenchida → ATENDIMENTO_EXTERNO

---

## 5. Encaminhamentos e tarefas internas

### 5.1 Encaminhamentos

O encaminhamento é o mecanismo de tramitação da OS entre usuários e unidades. Cada encaminhamento é um registro imutável — forma a trilha de auditoria operacional da OS.

Campos relevantes:

- **Unidade origem** e **servidor origem**
- **Unidade interna destino** — preenchida em encaminhamentos internos
- **Servidor destino** — opcional; se ausente, o encaminhamento vai para a fila da unidade
- **Unidade externa destino** — preenchida em encaminhamentos externos (mutuamente exclusivo com unidade interna destino)
- **Etapa interna** — ver §5.2
- **Tipo de ação** — ver §5.3 (campo a eliminar)
- **Aguarda retorno** — booleano; quando verdadeiro, a OS fica com pendência rastreável
- **Data retorno prevista** e **data retorno efetiva** — para controle de encaminhamentos externos

Campo manter_aberta_na_unidade (bool, default False):
Ao encaminhar, por padrão a OS é concluída na unidade
de origem. Quando manter_aberta_na_unidade=True, a unidade
de origem permanece com OsUnidadeStatus=ABERTA mesmo após
o encaminhamento — útil quando a unidade ainda precisa
acompanhar a OS enquanto outra unidade também atua.

Origem vazia: o primeiro encaminhamento após ENTRADA_DIVISAO
ou INCLUSAO_PROCESSO tem unidade_interna_origem nula —
a função origem_encaminhamento(os, servidor_logado) em
core/os_service.py determina a origem com base no
OsUnidadeStatus=ABERTA do servidor logado.

### 5.2 Etapa na unidade (etapa_interna)

O campo Encaminhamento.etapa_interna registra em qual
etapa da OS a unidade se encontra. É o segundo nível
hierárquico, abaixo da macroetapa global.

[PENDENTE IMPLEMENTAÇÃO] Choices a implementar:

| Código | Label | Quem aciona |
|---|---|---|
| ENTRADA | Entrada | Automático ao receber encaminhamento |
| TRIAGEM | Triagem | Coordenação (ação explícita) |
| EM_ATENDIMENTO | Em atendimento | Automático ao criar produção |
| DEVOLUCAO | Devolução | Coordenação/Chefia |
| SOLICITACAO_AJUSTE | Solicitação de ajuste | Coordenação/Chefia |
| HOMOLOGACAO | Homologação | Coordenação/Chefia |
| CONCLUIDA | Concluída | Automático ao encaminhar para fora |

Atualmente o campo é CharField livre sem choices definidos.

### 5.3 Tipo de ação (tipo_acao)

[PENDENTE IMPLEMENTAÇÃO — ELIMINAÇÃO]
O campo Encaminhamento.tipo_acao será eliminado.
As informações que ele carregava serão migradas para:
- etapa_interna: DEVOLUCAO, SOLICITACAO_AJUSTE, HOMOLOGACAO
- Campo automatico (bool): substitui tipo_acao=AUTOMATICO
- unidade_externa_destino preenchida: substitui tipo_acao=EXTERNO
- etapa_interna=ENTRADA: substitui tipo_acao=ENTRADA
- etapa_interna=CONCLUIDA: substitui tipo_acao=CONCLUSAO

Choices atuais ainda no código (a remover):
ENTRADA, DEVOLUCAO, SOLICITACAO_AJUSTE, EXTERNO,
HOMOLOGACAO, CONCLUSAO, AUTOMATICO

### 5.4 Hierarquia das três camadas

| Camada | Campo | Descrição |
|---|---|---|
| Macroetapa | Encaminhamento.tipo_macroetapa | Estado da OS no âmbito da Divisão |
| Etapa na unidade | Encaminhamento.etapa_interna | Estado da OS dentro de uma unidade |
| Status da produção | Producao.status | Estado do trabalho técnico |

### 5.5 OsUnidadeStatus

Modelo OsUnidadeStatus registra o estado da OS em cada
unidade operacional que a recebeu:

| Status | Descrição |
|---|---|
| ABERTA | OS recebida e em atendimento na unidade |
| CONCLUIDA | Unidade finalizou sua parte |
| REABERTA | OS devolvida à unidade após conclusão |
| SOMENTE_LEITURA | OS encerrada globalmente — apenas consulta |

Regras:
- OS chega na unidade → OsUnidadeStatus=ABERTA (automático)
- Encaminhar (padrão) → OsUnidadeStatus=CONCLUIDA (automático)
- Encaminhar com manter_aberta=True → permanece ABERTA
- Reabrir na unidade → REABERTA (chefia da unidade)

### 5.6 Bloqueio de encerramento
A OS só pode ser encerrada quando está ABERTA em apenas
uma unidade operacional. Se estiver ABERTA em mais de uma,
o sistema exibe mensagem:
"OS não pode ser encerrada pois também está aberta
na unidade X"

Quem pode encerrar:
- Chefia da unidade onde a OS está ABERTA
- Servidores com papel DEPARTAMENTO

### 5.7 Tarefas internas
TarefaInterna é criada automaticamente a cada encaminhamento,
registrando a unidade destino, servidor destino (opcional),
etapa interna e status (PENDENTE/CONCLUIDA).

O campo etapa_interna em TarefaInterna receberá os mesmos
choices de Encaminhamento.etapa_interna
[PENDENTE IMPLEMENTAÇÃO].

---

## 6. Imóveis

### 6.1 Tipos de imóvel

| Tipo | Identificação | Origem dos dados |
|---|---|---|
| Com inscrição cadastral | Número de inscrição SIAT | Importado via View do SIAT |
| Sem inscrição cadastral | Código ISIC (ex: `ISIC_0001`) | Inserção manual |

Os ISICs são reutilizáveis entre OSs — uma vez cadastrado, o imóvel sem inscrição pode ser vinculado a novas OSs sem re-cadastramento.

Quando um ISIC for regularizado e receber inscrição cadastral no SIAT, o sistema deve permitir a conversão do registro, preservando todos os vínculos históricos com OSs e produções anteriores.

### 6.2 Dados de referência vs. dados de trabalho

Os dados do imóvel existem em dois contextos com propósitos distintos:

**Identidade** (entidade `IMOVEL`) — inscrição cadastral ou código ISIC, mais observação interna. Não armazena dados cadastrais.

**Dados cadastrais no vínculo** (entidade `OS_IMOVEL`) — CTM, endereço, áreas, região homogênea e coordenadas registrados no momento em que o imóvel é vinculado à OS, a partir do SIAT ou de cadastro manual (ISIC). Cada vínculo preserva o snapshot dos dados daquele momento.

**Produção** (entidade `PRODUCAO_IMOVEL`) — referencia o `OS_IMOVEL` correspondente, reutilizando os dados cadastrais já capturados na OS.

### 6.3 Agrupamentos

Imóveis podem ser agrupados dentro de uma produção para atendimento conjunto, evitando registro repetitivo do mesmo procedimento. O agrupamento é flexível — cada imóvel tem seu registro individualizado em `PRODUCAO_IMOVEL`, com um campo `grupo_ref` que identifica o agrupamento dentro daquela produção. Mover um imóvel de grupo não afeta os demais.

### 6.4 Distinção fundamental: View SIAT vs. tabela Imovel

**View SIAT** (`data/siat_view.txt`) — fonte de consulta externa:
- Arquivo exportado mensalmente do SIAT, armazenado no servidor
- Contém dados cadastrais atuais de todas as inscrições do município
- É uma fonte de referência, NÃO um espelho do banco SIPRAC
- NUNCA deve ser importada em massa para a tabela Imovel
- Acesso: somente leitura, sob demanda explícita do usuário

**Tabela Imovel** (banco SIPRAC) — registros de trabalho:
- Contém apenas imóveis que foram explicitamente consultados
  e vinculados a Ordens de Serviço pela equipe da DAI
- Cada registro foi trazido da View SIAT por ação do usuário,
  ou cadastrado manualmente como ISIC
- Representa o universo de imóveis que já passaram pela DAI,
  não o cadastro completo do município

**Fluxo correto de uso da View SIAT:**
1. Usuário vincula imóvel a uma OS → sistema busca inscrição
   no arquivo siat_view.txt → dados são trazidos para Imovel
2. Usuário clica "Atualizar da View" em imóvel existente →
   sistema relê o arquivo para aquela inscrição específica
3. Arquivo siat_view.txt é atualizado mensalmente via upload
   na tela Carregar View SIAT → apenas substitui o arquivo,
   sem processar ou importar registros

**O que NÃO fazer:**
- Não importar todos os registros do arquivo para o banco
- Não sincronizar automaticamente a tabela Imovel com o SIAT
- Não tratar a tabela Imovel como cópia do cadastro municipal

---

## 7. Produção

### 7.1 Conceito
A entidade Producao registra o produto gerado pela OS —
tanto trabalhos técnicos quanto despachos. Uma OS pode
gerar zero, um ou múltiplos registros de produção, em
qualquer combinação. Cada produção pertence a uma unidade
operacional específica (campo unidade).

### 7.2 Tipos de produção

| Prefixo | Sequência | Exemplo |
|---|---|---|
| LA | Por tipo e ano, global da Divisão, máx. 999 | LA_005_2026 |
| PT | Idem | PT_002_2025 |
| PTF | Idem | PTF_001_2026 |
| PF | Idem | PF_003_2026 |
| PFF | Idem | PFF_001_2026 |
| IT | Idem | IT_007_2026 |
| PTJ | Idem | PTJ_004_2026 |
| Despacho | Sem numeração própria | Número SEI: 000000 |

### 7.3 Campos principais

| Campo | Tipo | Descrição |
|---|---|---|
| os | FK → OS | OS à qual pertence |
| unidade | FK → UnidadeInterna | Unidade responsável pela produção |
| tipo_producao | FK → TipoProducao | Prefixo e descrição |
| numero_producao | CharField | Gerado na homologação (ex: LA_005_2026) |
| numero_sei | CharField | Número do documento no SEI |
| servidor_responsavel | FK → Servidor | Avaliador/executor |
| revisor | FK → Servidor | Responsável pela revisão |
| autor_trabalho | CharField | Autor do trabalho técnico |
| modelo_sugerido | CharField | Modelo de regressão sugerido |
| prazo_interno | DateField | Prazo definido pela chefia |
| mes_cronograma | DateField | Mês de referência no cronograma |
| status | CharField | Status atual (ver 7.4) |
| numero_revisao | PositiveIntegerField | Contador de revisões |
| numero_ajustes | PositiveIntegerField | Contador de ajustes |

### 7.4 Status da produção

Fluxo sequencial sem volta (política da EAV):

| Status | Código | Quem aciona | Descrição |
|---|---|---|---|
| Não distribuído | NAO_DISTRIBUIDO | Automático | Criada sem responsável |
| Distribuído | DISTRIBUIDO | Chefia | Responsável atribuído |
| Revisar | REVISAR | Responsável | Entregue para revisão |
| Revisado | REVISADO | Revisor | Revisado sem ajustes relevantes |
| Ver ajustes | VER_AJUSTES | Revisor | Ajustes relevantes solicitados |
| Entrega ajustes | ENTREGA_AJUSTES | Responsável | Ajustes entregues para revisão final |
| Ajustes OK | AJUSTES_OK | Revisor | Ajustes aprovados |
| Homologar | HOMOLOGAR | Responsável | Apto à homologação |
| Enviado | ENVIADO | Chefia | Concluído no SEI |
| Cancelado | CANCELADO | Chefia | Cancelado |

### 7.5 Datas do fluxo

| Campo | Preenchimento | Corresponde a |
|---|---|---|
| prazo_interno | Manual (chefia) | Prazo do avaliador (PRAZO_AVAL) |
| data_entrega_avaliacao | Automático → REVISAR | Entrega para revisão (ENTREGA_AVAL) |
| data_entrega_revisao | Automático → REVISADO | Revisão concluída (ENTREGA_REV) |
| data_entrega_ajustes | Automático → ENTREGA_AJUSTES | Ajustes entregues (ENTREGA_AJU) |
| data_ajustes_ok | Automático → AJUSTES_OK | Ajustes aprovados |
| data_homologar | Automático → HOMOLOGAR | Apto à homologação |
| data_enviado | Automático → ENVIADO | Conclusão no SEI |

Todas as datas automáticas são editáveis pela chefia
via ProducaoEditarCampoView.

### 7.6 Cancelamento
Uma produção pode ser cancelada em qualquer etapa.
Cancelamento após ENVIADO exige justificativa registrada
em auditoria.

### 7.7 Imóveis da produção
Os imóveis de uma produção são registrados em ProducaoImovel
(N:M). Uma produção pode abranger um subconjunto dos imóveis
da OS. Cada vínculo tem campo grupo_ref para agrupamento
dentro da produção.

### 7.8 Log de status
Cada transição de status é registrada em ProducaoStatusLog
com data/hora, status anterior, status novo e servidor
que realizou a transição.

### 7.9 Visibilidade
Na tela gerencial, cada linha corresponde a uma produção.
OSs sem produção aparecem com uma linha "Sem produção".
A filtragem de produções na tela gerencial considera
apenas as produções da unidade do usuário logado
(campo Producao.unidade).

---

## 8. Pesquisa de dados

O perfil Auxiliar Administrativo – Pesquisa opera um módulo próprio, independente do fluxo de OSs. O pesquisador tem meta mensal de produção e entrega semanal de registros.

### 8.1 Tipos de pesquisa

- Guia de ITBI
- Ofertas – Aluguel
- Ofertas – Vendas

### 8.2 Fontes de registro

- **SIAT/PMI** — numeração automática do módulo PMI do SIAT
- **Tabela específica** — numeração sequencial por tabela

### 8.3 Metas

As metas podem ser individuais (por servidor) ou coletivas (por unidade), e por tipo de pesquisa ou agregadas. Todas as combinações são válidas e podem coexistir.

---

## 9. Perfis de acesso

### 9.1 Flags de permissão em PerfilAcesso

| Flag | Descrição |
|---|---|
| pode_criar_os | Pode criar novas OSs |
| pode_encerrar_os | Pode encerrar OSs |
| pode_homologar | Pode homologar produções |
| pode_criar_os_interna | Pode criar OS sem processo SEI |
| visibilidade_total | Acesso total a todas as OSs |
| admin_sistema | Acesso ao painel de administração e SIAT |

### 9.2 Visibilidade

[PENDENTE IMPLEMENTAÇÃO] Três níveis de visibilidade:

| Nível | Código | Quem | O que vê |
|---|---|---|---|
| Total | TOTAL | Diretor, Administrador | Todas as OSs, edição completa |
| Departamento | DEPARTAMENTO | Aux. Adm. Gestão (papel DEPARTAMENTO) | Todas as OSs, consulta e entrada |
| Unidade | UNIDADE | Demais servidores | Apenas OSs da própria unidade |

Atualmente a visibilidade é controlada pelo flag
visibilidade_total (bool). O campo visibilidade com
três níveis está definido conceitualmente mas não
implementado.

### 9.3 Tabela de perfis

| Perfil | Cargo | Cria OS | Encerra OS | Homologa | Visibilidade | Admin |
|---|---|---|---|---|---|---|
| Administrador | Administrador do sistema | Sim | Sim | Sim | TOTAL | Sim |
| Diretor | Diretor | Sim | Sim | Sim | TOTAL | Não |
| Aux. Téc. Direção | Eng./Arq./AF — FG Direção | Sim | Sim | Sim | TOTAL | Não |
| Coordenador | Coordenador | Sim | Sim (sua unidade) | Sim | UNIDADE | Não |
| Aux. Téc. Coord. | Eng./Arq./AF — FG Coordenação | Sim | Não | Sim | UNIDADE | Não |
| Técnico | Eng./Arq./AF sem FG | Não | Não | Não | UNIDADE | Não |
| Aux. Adm. Gestão | Auxiliar Adm. — gestão | Sim | Não | Não | DEPARTAMENTO | Não |
| Aux. Adm. Pesquisa | Auxiliar Adm. — pesquisa | Não | Não | Não | UNIDADE | Não |

### 9.4 Níveis de dashboard

O dashboard adapta sua visão conforme o perfil ativo:

- SISTÊMICA: usuários com visibilidade_total=True —
  visão consolidada de todas as unidades
- UNIDADE: coordenadores e aux. técnicos —
  visão da própria unidade
- PESSOAL: técnicos —
  visão das próprias produções e tarefas

### 9.5 Permissões especiais temporárias

Concedidas pelo gestor via modelo PermissaoEspecial,
com data_inicio e data_fim. Exemplo: visibilidade
cross-unidade por prazo determinado.

### 9.6 Middleware e perfil ativo

O PerfilAcessoMiddleware carrega o vínculo ativo do
servidor logado e disponibiliza em request.vinculo_ativo
e request.perfil_acesso. Os mixins de permissão
(RequerLoginMixin, RequerAdminMixin, etc.) em
core/mixins.py utilizam esses valores para controle
de acesso nas views.

Navbar: exibe cargo e sigla da unidade do vínculo ativo,
não o nome do perfil.

### 9.7 Pendências de perfil
- [PENDENTE] Restrição de encerramento por escopo de
  unidade no Coordenador (atualmente gate é apenas
  pode_encerrar_os, sem verificação de unidade)
- [PENDENTE] Restrição dedicada para Aux. Adm. Pesquisa
  (somente tela de imóveis)
- [PENDENTE §15.8] Visão sistêmica mínima para todos
- [PENDENTE §15.9] Função Gratificada na interface
- [PENDENTE §15.10] Cargo e perfil na navbar

---

## 10. Datas — política de preenchimento

| Campo | Comportamento |
|---|---|
| Data de criação da OS no SGBD | Automática, bloqueada |
| Data de entrada do processo SEI na Divisão | Manual obrigatória |
| Data de abertura/fechamento do processo SEI | Manual obrigatória |
| Data de encaminhamentos internos | Automática, editável |
| Data de retorno externo efetivo | Manual |
| Data de encerramento da OS | Automática, editável |
| Data de início/fim de vínculos de servidor | Manual obrigatória |
| Data-base dos dados de trabalho | Manual obrigatória |

Para campos com data editável, o log de auditoria registra a data original automática, a data corrigida, e o servidor que fez a correção.

---

## 11. Auditoria

Escopo do log de auditoria:

- Criação, encerramento e reabertura de OS
- Vinculação e desvinculação de processo SEI
- Mudança de macroetapa
- Criação, edição e cancelamento de produção
- Edição de dados de imóvel em produção homologada (com justificativa obrigatória)
- Concessão e revogação de permissões especiais
- Alteração de prioridade da OS
- Confirmação de OS interna sem processo SEI
- Tentativas de acesso negado acima de 3 por sessão

Campos livres como observações e anotações internas não são auditados.

---

## 12. Inventário de entidades — 31 entidades

### Estrutura e segurança
`Servidor` · `UnidadeInterna` · `ServidorUnidade` · `PerfilAcesso` · `PermissaoEspecial`

### Externo
`UnidadeExterna`

### Classificação
`Natureza` · `TipoDemanda` · `Finalidade` · `CombinacaoValida`

### Imóveis
`Imovel` · `OsImovel` · `ProducaoImovel` · `ProducaoImovelDados`

### OS e ciclo de vida
`OS` · `OsProcesso` · `MacroetapaLog` *(DEPRECATED — substituído
por Encaminhamento.tipo_macroetapa e OS.encerrada)* ·
`Encaminhamento` · `TarefaInterna` · `OsUnidadeStatus`

### Produção
`Producao` · `ProducaoAtributo` · `TipoProducao` · `ProducaoStatusLog`

### Pesquisa
`RegistroPesquisa` · `MetaPesquisa`
*(modelos implementados — interface pendente, ver §15.6)*

### Preferências
`PreferenciaGerencial`

### Auditoria
`LogAuditoria`

---

### Campos relevantes adicionados após arquitetura inicial

**OS:**
- `encerrada` (bool) — substitui MacroetapaLog para encerramento
- `data_encerramento` (DateTimeField)

**OsProcesso:**
- `registrado_por` (FK → Servidor) — [PENDENTE IMPLEMENTAÇÃO]
- `tipo_vinculo` com choices: PRINCIPAL / RELACIONADO —
  [PENDENTE IMPLEMENTAÇÃO]
- `aguardando_redistribuicao` (bool) — bloqueio de processos
  incluídos enquanto OS estava em outra unidade

**Encaminhamento:**
- `tipo_macroetapa` — macroetapa registrada no encaminhamento
- `automatico` (bool) — encaminhamento gerado pelo sistema
- `manter_aberta_na_unidade` (bool) — mantém OsUnidadeStatus=ABERTA
  na unidade de origem ao encaminhar
- `tipo_acao` — [PENDENTE ELIMINAÇÃO — ver §5.3]

**Producao:**
- `unidade` (FK → UnidadeInterna) — unidade responsável
- `servidor_responsavel` (FK → Servidor) — executor
- `revisor` (FK → Servidor)
- `autor_trabalho` (CharField)
- `modelo_sugerido` (CharField)
- `prazo_interno` (DateField)
- `mes_cronograma` (DateField)
- `numero_revisao` (PositiveIntegerField)
- `numero_ajustes` (PositiveIntegerField)
- `data_entrega_avaliacao`, `data_entrega_revisao`,
  `data_entrega_ajustes`, `data_ajustes_ok`,
  `data_homologar`, `data_enviado`

**OsUnidadeStatus** *(novo):*
- `os`, `unidade`, `status` (ABERTA/CONCLUIDA/REABERTA/SOMENTE_LEITURA)
- `data_abertura`, `data_conclusao`
- `aberta_por`, `concluida_por`
- `manter_aberta` (bool)

**PreferenciaGerencial** *(novo):*
- `servidor` (OneToOne → Servidor)
- `colunas_visiveis` (JSONField)

---

## 13. Decisões tecnológicas

| Componente | Escolha | Justificativa |
|---|---|---|
| Banco de dados | PostgreSQL | Gratuito, robusto, multiusuário, familiar à PROCEMPA |
| Backend | Python + Django | ORM maduro, Django Admin, documentação extensa em português |
| Frontend | Django Templates (inicial) | Sem necessidade de framework JS separado na fase inicial |
| Servidor web | Nginx + Gunicorn | Padrão Django em produção |
| Protótipo/homologação | Railway | Deploy Django + PostgreSQL sem configuração complexa |
| Produção definitiva | Servidor PROCEMPA | Dentro da rede interna da Prefeitura |
| Versionamento | GitHub | Com GitHub Projects para gestão de tarefas |
| Codificação assistida | Cursor | IA integrada ao ambiente de desenvolvimento |
| Autenticação | Própria (hash bcrypt) | Com caminho previsto para migração futura ao AD da Prefeitura |

---

## 14. Questões pendentes para implantação

- Sistema operacional do servidor PROCEMPA (impacta configuração de ambiente)
- Responsabilidades de infraestrutura: backup, atualizações, monitoramento (DAI vs. PROCEMPA)
- Prazo máximo de OS interna sem processo SEI antes de gerar alerta
- Lista completa de Naturezas, Tipos de Demanda e Finalidades válidos (catálogo mínimo necessário antes do primeiro uso em produção)
- Política de retenção dos logs de auditoria (verificar normativa municipal aplicável)
- Notificações de encaminhamento além do painel (a definir em fase posterior)

---

## 15. Funcionalidades futuras previstas

### 15.1 Visualização geográfica de imóveis
A tela /imoveis/mapa/ já existe com marcadores para imóveis
com coordenadas. [IMPLEMENTADO PARCIALMENTE]
Pendente: carregar mapa sem marcadores iniciais (ver 15.7),
histórico georreferenciado, otimização de performance.

### 15.2 Deduplicação e reaproveitamento de ISICs
Imóveis sem inscrição cadastral (ISIC) tendem a ser recadastrados por diferentes
usuários ao longo do tempo, mesmo representando o mesmo imóvel físico. Para garantir
histórico consistente e evitar duplicidades, será necessário implementar:
- Busca por similaridade ao criar novo ISIC: verificar NUM_BLOCO, cod_logradouro,
  num_endereco e coordenadas antes de criar novo registro
- Alerta ao usuário quando um ISIC similar já existir, sugerindo reaproveitamento
- Ferramenta administrativa de mesclagem de ISICs duplicados, preservando todos
  os vínculos históricos com OSs e produções
- Identificador estável de imóvel físico (independente da inscrição cadastral)
  para garantir rastreabilidade mesmo quando o imóvel receber inscrição futuramente

### 15.3 Histórico visual georreferenciado
Com as coordenadas (latitude, longitude, coord_x, coord_y) armazenadas em Imovel
e nos snapshots de OsImovel, será possível implementar:
- Mapa interativo mostrando imóveis vinculados a uma OS
- Linha do tempo visual por imóvel: quais OSs o atenderam e quando
- Visualização de clusters de imóveis por bairro ou região homogênea
- Histórico de alterações cadastrais plotado no mapa (área, finalidade, RH)
- Base para análises espaciais de mercado imobiliário pela EPGV
Bibliotecas candidatas: Leaflet.js (coordenadas geográficas WGS84)
e/ou sistema TM POA (coord_x, coord_y) para mapas municipais.

### 15.4 Informação de frentes por Lote Fiscal na View SIAT
Atualmente a View SIAT não informa se um Lote Fiscal (NUM_BLOCO) possui uma ou mais
frentes (logradouros). Isso impede o preenchimento automático seguro de logradouro,
bairro e região homogênea ao criar um ISIC a partir de um NUM_BLOCO, pois um lote
com múltiplas frentes pode ter mais de um logradouro, bairro e RH associados.

Ação necessária: alterar os procedimentos de geração da View SIAT para incluir
um campo indicando a quantidade de frentes do Lote Fiscal (ex: QTD_FRENTES).
Com essa informação disponível:
- QTD_FRENTES = 1: preenchimento automático seguro de logradouro, bairro e RH
  ao informar NUM_BLOCO na criação de ISIC
- QTD_FRENTES > 1: sistema alerta o usuário que há múltiplas frentes e solicita
  preenchimento manual dos campos de endereço

As coordenadas (latitude, longitude, coord_x, coord_y) podem ser preenchidas
automaticamente a partir do NUM_BLOCO independentemente do número de frentes,
pois representam o centroide do lote fiscal.

### 15.5 Marcador de acompanhamento especial
Permitir que coordenadores e técnicos marquem OSs para acompanhamento especial,
mesmo após encaminhamento para outra unidade. Funcionaria como filtro adicional
nas listagens, permitindo:
- Coordenação acompanhar OSs que passaram pela unidade mesmo após encaminhamento
- Técnicos acompanharem OSs de seu interesse pessoal
- Prazo interno em encaminhamentos entre unidades (data_retorno_prevista interno)
A implementação seguirá o modelo de marcadores customizáveis por equipe,
similar ao existente no SEI.

### 15.6 Módulo de Pesquisa de Dados
Os modelos RegistroPesquisa e MetaPesquisa já estão
implementados no banco. [MODELOS IMPLEMENTADOS]
Pendente: interface completa do módulo de pesquisa,
telas de registro semanal e apuração mensal de metas.

### 15.7 Otimização do mapa geral de imóveis
Com volume de 280mil+ imóveis no banco, carregar todos os marcadores
no mapa geral (/imoveis/mapa/) causa timeout e experiência ruim.
Relacionado a 15.1 — mapa já existe mas carrega todos
os marcadores sem paginação.

Melhorias previstas:
- Mapa inicia vazio, sem marcadores
- Usuário pesquisa por inscrição, ISIC, logradouro, bairro ou lote fiscal
- Resultados da pesquisa são plotados no mapa (máximo 200 marcadores por busca)
- Implementar clustering de marcadores (Leaflet.MarkerCluster) para
  visualização de grandes volumes sem degradação de performance
- Paginação ou lazy loading dos resultados
- Índices no banco PostgreSQL nos campos latitude, longitude,
  nom_logradouro e bairro para acelerar as consultas geoespaciais
- Considerar futuramente PostGIS para consultas geoespaciais avançadas

### 15.8 Visão sistêmica mínima para todos os servidores
Servidores com perfil operacional (Técnico, Aux. Adm.) devem ter acesso
mínimo de visualização a informações gerais da Divisão, promovendo
integração e colaboração. Funcionalidades previstas:
- Painel público interno: OSs encerradas com produções homologadas
  (sem dados sensíveis de tramitação interna)
- Busca por imóvel: qualquer servidor pode consultar o histórico de
  OSs que envolveram determinada inscrição ou ISIC
- Mural de produções: listagem de trabalhos homologados, filtráveis
  por tipo, período e unidade — sem detalhes de tramitação interna
- Configurável pelo administrador: quais informações ficam visíveis
  para perfis operacionais

### 15.9 Função Gratificada e identificação de cargo na interface
Adicionar ao modelo ServidorUnidade um campo para identificar
se o vínculo possui Função Gratificada (FG) e qual é a função:
- fg_ativa: BooleanField (default False)
- descricao_fg: CharField opcional (ex: Coordenador, Supervisor,
  Auxiliar Técnico)
- Exibir na interface: nome do usuário + cargo + FG quando aplicável
- Útil para rastreio de responsabilidades em homologações e revisões

### 15.10 Exibição de cargo e perfil na navbar
Atualmente a navbar exibe o cargo e unidade do vínculo ativo de maior
hierarquia do servidor logado. Refinamento previsto:
- Para servidores com múltiplos vínculos ativos, avaliar se é mais
  informativo exibir o cargo operacional ou o perfil de maior hierarquia
- Exemplo: franciscoteston aparece como "Engenheiro — DAI" mas seu
  perfil de maior hierarquia é "Administrador"
- Opções a avaliar:
  * Exibir perfil do sistema: "Administrador — DAI"
  * Exibir cargo + perfil: "Engenheiro — DAI (Administrador)"
  * Permitir que o usuário escolha qual vínculo exibir quando tiver múltiplos
- Considerar também exibir indicação de Função Gratificada (FG)
  quando o vínculo ativo tiver fg_ativa=True (ver seção 15.9)

### 15.11 Campo Origem — unidade externa solicitante
O campo Origem identifica a unidade externa que originou a demanda
(ex: ATENDIMENTO-SMF, PPDP-PGM, RM-SMF, CEFH-SMAMUS).
Atualmente não implementado no SIPRAC. Avaliar futuramente se deve
ser um campo texto livre, uma lista de Unidades Externas já cadastradas,
ou uma lista separada de "unidades solicitantes" distinta das unidades
externas de encaminhamento.
Referência: campo Origem da planilha gerencial EAV (SIGA).

### 15.12 Revisão dos status de produção
[IMPLEMENTADO] Os status REVISADO e HOMOLOGAR foram
implementados. O modelo final de status da produção
está documentado na seção 7.4.
Os status intermediários adicionais (VER_AJUSTES,
ENTREGA_AJUSTES, AJUSTES_OK, ENVIADO) também foram
implementados conforme definição da EAV.

### 15.13 Prazo Recompra ou ITBI
Campo calculado presente na planilha gerencial EAV:
- Finalidade RECURSO ITBI: data de entrada na unidade + 120 dias
- Finalidade RECOMPRA: data de entrada na unidade + 60 dias

Pendente definir se RECOMPRA e RECURSO ITBI serão tratados como
valores de "Requerimento" ou de "Finalidade" no SIPRAC antes de
implementar o cálculo automático. Campo calculado — não precisa
ser armazenado no banco.

### 15.14 Observação por imóvel na OS
O campo OBSERVAÇÃO_IMÓVEL da planilha gerencial EAV registra observações
específicas sobre um imóvel no contexto de uma OS (ex: "Imóvel em área de
regularização fundiária", "Acesso restrito — agendar vistoria").

No SIPRAC, OsImovel não possui campo de observação. Avaliar futuramente
se é mais adequado:
- Adicionar campo observacao em OsImovel (observação por imóvel por OS)
- Usar o modelo Comentario com referência ao OsImovel
- Manter apenas a observacao_interna em Imovel (observação permanente
  independente de OS)

### 15.15 Metas por tipo de produção técnica
A planilha gerencial EAV possui dois campos relacionados a metas:
- metaTargets: metas mensais por tipo de trabalho (LA, PT, PTF, etc.)
  definidas pela chefia para a equipe
- metaWeightedOverrides: ajuste de peso por tipo de trabalho
  (ex: LA vale 2 pontos, PT vale 1 ponto) para cálculo ponderado
  de produtividade

No SIPRAC, MetaPesquisa cobre apenas o módulo de pesquisa de dados.
Avaliar futuramente se faz sentido criar MetaProducao — metas mensais
por tipo de produção técnica por unidade — considerando:
- Se a Direção estabelece metas formais por tipo de trabalho
- Se o peso ponderado por tipo é relevante para avaliação de desempenho
- Integração com o dashboard gerencial e relatórios de produtividade

### 15.16 Correção de encoding nos dropdowns do formulário de OS
[RESOLVIDO] O problema de encoding foi corrigido com
geração de dumps UTF-8 sem BOM para carga no Railway.
Procedimento documentado em docs/RAILWAY_MANUTENCAO.md.

### 15.17 Acesso a OSs que nunca passaram pela unidade
Servidores só podem acessar OSs que estejam ou já estiveram em sua unidade
(OsUnidadeStatus existente). OSs que nunca passaram pela unidade ficam
invisíveis, exceto para perfis com visibilidade_total=True (DAI/Direção).
Pendente definir: onde e como exibir essas OSs para perfis com
visibilidade_total, sem misturar com a fila operacional da unidade.
Relacionado à implementação da unidade DEPARTAMENTO (§15.21)
e ao nível de visibilidade DEPARTAMENTO (§9.2).

### 15.18 Reabertura global da OS
Reabertura na unidade: [IMPLEMENTADO] via OsUnidadeStatus
e OSReabrirNaUnidadeView. Apenas a chefia da unidade
pode reabrir. OS volta ao status REABERTA na unidade.

Reabertura global (OS.encerrada → False): [PENDENTE]
Avaliar futuramente. Perfil provável: Direção/Administrador.

### 15.19 Módulo de Notificações
Estrutura separada do fluxo de OSs, acessível por item
próprio no menu lateral, com visibilidade controlada
por perfil. Usuários sem habilitação não veem o item
no menu. Sabrina e Vanessa (ESJL) são as usuárias
principais. Detalhar futuramente: tipos de notificação,
fluxo, campos, integração com produção da ESJL.

### 15.20 Painel de Consulta Geral
Acessível a todos os usuários em modo somente leitura.
Exibe informações resumidas de todas as OSs independente
da unidade. Visão a definir. Implementar após
consolidação das telas principais.

### 15.21 Unidade DEPARTAMENTO no sistema
O DEPARTAMENTO será criado como UnidadeInterna com
tipo='ADMINISTRATIVA'. As unidades operacionais
(DAI, EAV, ESJL, EPGV) terão tipo='OPERACIONAL'.
Servidores com papel DEPARTAMENTO (ex: Sabrina, Vanessa,
Francisco) terão visibilidade de todas as OSs para
consulta e gestão administrativa de entrada.
Inclui implementação do seletor de perfil ativo
para servidores com mais de um vínculo.
Relacionado a §9.2 (visibilidade DEPARTAMENTO).

### 15.22 Painel de administração de usuários
Tela própria no SIPRAC (/administracao/usuarios/) para
gestão de servidores, perfis e vínculos com checkboxes
intuitivos, sem depender do Django Admin.
Implementar após consolidação das telas principais.
Atualmente gerenciado via Django Admin (/admin/).
