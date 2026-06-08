# Arquitetura do SGBD — Divisão de Avaliação de Imóveis (DAI)

## 1. Contexto e motivação

A Divisão de Avaliação de Imóveis (DAI) da Prefeitura Municipal de Porto Alegre utiliza o Sistema Eletrônico de Informações (SEI) como sistema oficial de gerenciamento de processos. O SEI trata o número do processo como entidade central, exigindo que um mesmo trabalho seja registrado individualmente para cada processo ao qual se vincula — gerando retrabalho quando uma produção atende a múltiplos processos simultaneamente. O sistema é denominado SIPRAC — Sistema de Processos, Acompanhamento e Cronogramas.

O SGBD da DAI foi concebido para operar em complemento ao SEI, oferecendo gerenciamento detalhado em nível operacional e gerencial, sem replicar o SEI nem substituí-lo. A integração com o SEI é indireta: números de processo, documentos e despachos são registrados manualmente no SGBD, sem leitura automática do SEI.

---

## 2. Estrutura organizacional

A DAI é composta por quatro Unidades Internas:

| Sigla | Nome completo |
|---|---|
| DAI | Divisão de Avaliação de Imóveis (unidade técnica e de chefia) |
| EAV | Equipe de Avaliações |
| ESJL | Equipe de Suporte, Judiciais e Locações |
| EPGV | Equipe Genérica da Planta de Valores |

A "Divisão" como figura formal representa o agrupamento das quatro unidades. Para fins de encaminhamento e registro no SGBD, a DAI opera como unidade interna com plenos poderes de envio e recebimento de OSs.

Um servidor pode estar lotado em mais de uma unidade simultaneamente, ou assumir cargo temporário (ex: substituição de coordenador em férias). Esses vínculos são registrados com data de início e data de fim.

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
- **Tipo de demanda:** ex: Requerimento IPTU, Requerimento Desapropriação, Ofício
- **Finalidade:** ex: Desapropriação Parcial, Desapropriação Total, Revisão do Valor Venal

Há combinações inválidas entre as três dimensões (ex: Não tributário + IPTU é inválido). O controle é feito por uma tabela `COMBINACAO_VALIDA`, administrada pelo administrador do sistema. A interface apresenta as opções em cascata — ao selecionar a Natureza, os Tipos de Demanda válidos são filtrados automaticamente, e assim por diante.

### 3.4 Prioridade

Campo simples com três valores: `NORMAL`, `PRIORITARIO`, `URGENTE`. Padrão: `NORMAL`. Alterações de prioridade são registradas em auditoria.

### 3.5 Processos SEI vinculados

Uma OS pode estar vinculada a mais de um processo SEI. O primeiro vínculo é o processo principal (`tipo_vinculo = PRINCIPAL`). Demais vínculos são processos relacionados (`tipo_vinculo = RELACIONADO`), incluídos via macroetapa "Inclusão de Processo Relacionado".

Cada processo vinculado tem data de entrada na Divisão e data de encerramento próprias. Um processo relacionado pode ser encerrado antes da OS ser encerrada — situação relevante para o Dashboard na contagem de processos abertos.

---

## 4. Macroetapas

As macroetapas representam o estado atual da OS no seu ciclo de vida. Cada transição é registrada como um evento no `MACROETAPA_LOG`, formando um histórico completo de tramitação. O estado atual é sempre derivado do último registro.

| # | Macroetapa | Regra de transição |
|---|---|---|
| 1 | Entrada na Divisão | Estado inicial — criação da OS |
| 2 | Atendimento Interno | Livre após Entrada |
| 3 | Atendimento Externo | Livre após Entrada |
| 4 | Retorno Externo | Somente após Atendimento Externo |
| 5 | Inclusão de Processo Relacionado | Qualquer estado exceto Encerrada |
| 6 | Reabertura | Somente após Encerrada |
| 7 | Encerrado na Divisão | Estado final — reversível via Reabertura |

Algumas transições podem ser automáticas (ex: ao registrar o retorno de uma unidade externa com `aguarda_retorno = true`, o sistema propõe a transição para Retorno Externo). Outras são manuais.

---

## 5. Encaminhamentos e tarefas internas

### 5.1 Encaminhamentos

O encaminhamento é o mecanismo de tramitação da OS entre usuários e unidades. Cada encaminhamento é um registro imutável — forma a trilha de auditoria operacional da OS.

Campos relevantes:

- **Unidade origem** e **servidor origem** — sempre preenchidos
- **Unidade interna destino** — preenchida em encaminhamentos internos
- **Servidor destino** — opcional; se ausente, o encaminhamento vai para a fila da unidade
- **Unidade externa destino** — preenchida em encaminhamentos externos (mutuamente exclusivo com unidade interna destino)
- **Etapa interna** — Triagem, Análise, Revisão, Homologação, Conclusão
- **Tipo de ação** — Atribuição, Devolução, Solicitação de ajuste, Encaminhamento externo, Homologação, Conclusão
- **Aguarda retorno** — booleano; quando verdadeiro, a OS fica com pendência rastreável
- **Data retorno prevista** e **data retorno efetiva** — para controle de encaminhamentos externos

### 5.2 Etapas internas das unidades

Cada unidade processa a OS internamente em cinco etapas sequenciais:

`Triagem → Análise → Revisão → Homologação → Conclusão`

A homologação exige nível hierárquico mínimo de Auxiliar Técnico ou Coordenador (ou substituto vigente).

Um servidor só pode encaminhar para seu superior hierárquico se o superior solicitar.

### 5.3 Unidades externas

Encaminhamentos podem ter como destino unidades externas à DAI. Há dois casos:

- **Unidade externa identificada** (ex: SCIM) — rastreamento completo com retorno esperado
- **Unidade externa não identificada** — registro genérico quando a identificação é irrelevante

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

**Dados de referência** (entidade `IMOVEL`) — identificam e localizam o imóvel para fins de gerenciamento. Um exercício vigente. Podem ser atualizados pelo usuário via reimportação do SIAT quando conveniente.

**Dados de trabalho** (entidade `PRODUCAO_IMOVEL_DADOS`) — registram as características técnicas do imóvel na data-base do trabalho, com precisão revisada e homologada. Podem abranger múltiplos exercícios. Não são atualizados automaticamente. Após homologação, só podem ser editados de forma controlada, com registro obrigatório em auditoria e justificativa.

### 6.3 Agrupamentos

Imóveis podem ser agrupados dentro de uma produção para atendimento conjunto, evitando registro repetitivo do mesmo procedimento. O agrupamento é flexível — cada imóvel tem seu registro individualizado em `PRODUCAO_IMOVEL`, com um campo `grupo_ref` que identifica o agrupamento dentro daquela produção. Mover um imóvel de grupo não afeta os demais.

---

## 7. Produção

### 7.1 Tipos de produção

A produção é a entidade que registra o produto gerado pela OS — tanto trabalhos técnicos quanto despachos. Uma OS pode gerar zero, um ou múltiplos registros de produção, em qualquer combinação.

| Prefixo | Sequência | Exemplo |
|---|---|---|
| LA | Por tipo e ano, global da Divisão, máx. 999 | `LA_005_2026` |
| PT | Idem | `PT_002_2025` |
| PTF | Idem | `PTF_001_2026` |
| PF | Idem | `PF_003_2026` |
| PFF | Idem | `PFF_001_2026` |
| IT | Idem | `IT_007_2026` |
| PTJ | Idem | `PTJ_004_2026` |
| Despacho | Sem numeração própria | Número SEI: `000000` |

### 7.2 Campos comuns a todas as produções

- Número próprio (automático para trabalhos técnicos)
- Número SEI (obrigatório para despachos, presente em trabalhos quando aplicável)
- Status: Em elaboração, Concluído, Homologado, Cancelado
- Servidor criador e servidor homologador
- Data de homologação
- Observação

### 7.3 Cancelamento

Uma produção pode ser cancelada após criação. Cancelamento após homologação exige justificativa registrada em auditoria.

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

| Perfil | Cargo correspondente | Cria OS | Encerra OS | Homologa | Cria OS interna | Visibilidade |
|---|---|---|---|---|---|---|
| Administrador | Administrador do sistema | Sim | Sim | Sim | Sim | Total |
| Diretor | Diretor | Sim | Sim | Sim | Sim | Total |
| Aux. Téc. Direção | Eng./Arq./AF – FG Direção | Sim | Sim | Sim | Sim | Total |
| Coordenador | Coordenador | Sim | Sim (sua unidade) | Sim | Sim | Sua unidade + encaminhamentos |
| Aux. Téc. Coord. | Eng./Arq./AF – FG Coordenação | Sim | Não | Sim | Não | Sua unidade + encaminhamentos |
| Técnico | Eng./Arq./AF sem FG | Não | Não | Não | Não | Sua unidade + encaminhamentos |
| Aux. Adm. Gestão | Auxiliar Adm. – gestão | Sim | Não | Não | Não | Sua unidade + encaminhamentos |
| Aux. Adm. Pesquisa | Auxiliar Adm. – pesquisa | Não | Não | Não | Não | Somente imóveis (consulta) |

Permissões especiais temporárias (ex: visibilidade cross-unidade por prazo determinado) são concedidas pelo gestor e registradas com data de início e fim.

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
- Edição de `PRODUCAO_IMOVEL_DADOS` após homologação (com justificativa obrigatória)
- Concessão e revogação de permissões especiais
- Alteração de prioridade da OS
- Confirmação de OS interna sem processo SEI
- Tentativas de acesso negado acima de 3 por sessão

Campos livres como observações e anotações internas não são auditados.

---

## 12. Inventário de entidades — 28 entidades

### Estrutura e segurança
`SERVIDOR` · `UNIDADE_INTERNA` · `SERVIDOR_UNIDADE` · `PERFIL_ACESSO` · `PERMISSAO_ESPECIAL`

### Externo
`UNIDADE_EXTERNA`

### Classificação
`NATUREZA` · `TIPO_DEMANDA` · `FINALIDADE` · `COMBINACAO_VALIDA`

### Imóveis
`IMOVEL` · `OS_IMOVEL` · `PRODUCAO_IMOVEL` · `PRODUCAO_IMOVEL_DADOS`

### OS e ciclo de vida
`OS` · `PROCESSO_SEI` · `OS_PROCESSO` · `MACROETAPA_LOG` · `ENCAMINHAMENTO` · `TAREFA_INTERNA`

### Produção
`PRODUCAO` · `PRODUCAO_ATRIBUTO` · `PRODUCAO_STATUS_LOG` · `TIPO_PRODUCAO` · `TIPO_PRODUCAO_UNIDADE`

### Pesquisa
`REGISTRO_PESQUISA` · `META_PESQUISA`

### Auditoria
`LOG_AUDITORIA`

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
Os campos latitude, longitude, coord_x e coord_y armazenados na entidade Imovel
permitem a implementação futura de um mapa interativo para gerenciamento visual
dos imóveis vinculados a OSs e produções. Bibliotecas candidatas: Leaflet.js
(coordenadas geográficas) ou mapa base TM POA (coordenadas UTM locais).
A implementação será definida após a conclusão das fases principais do sistema.

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
Módulo independente para gerenciamento de pesquisas de dados de mercado
(ofertas de venda, ofertas de aluguel, guias de ITBI). Funciona em paralelo
às Ordens de Serviço mas com ciclo de vida próprio, centrado na
Demanda de Pesquisa como entidade principal.

**Entidade central: Demanda de Pesquisa**
- Pode ter ou não vínculo com processo SEI
- Pode ter ou não vínculo com imóveis específicos
- Tem um solicitante (qualquer servidor, inclusive de outra unidade)
- Passa pelo Supervisor de Pesquisa antes de chegar ao pesquisador
- Pode ser recorrente (proposta pela chefia) ou pontual

**Fluxo:**
Solicitação (qualquer servidor ou chefia) → Supervisor analisa e distribui
→ Pesquisador(es) executam → Supervisor homologa/encerra

**Tipos de demanda:**
- Sem demanda específica: pesquisador decide dentro da meta
- Com demanda específica da chefia: recorrente ou pontual
- Com demanda de outro servidor/unidade: obrigatório passar pelo Supervisor

**Perfis envolvidos:**
- Solicitante: qualquer servidor, inclusive de outras unidades
- Supervisor de Pesquisa: Técnico com FG (atualmente cargo de Supervisor na ESJL)
- Pesquisador: Auxiliar Administrativo — Pesquisa (ESJL)

**Visão do pesquisador:**
- Número do processo SEI e dados dos imóveis vinculados (inscrição, endereço, área)
- Visualização restrita a processos com inscrições do SIAT
- Futuramente: lista de finalidades que necessitam dados de mercado como filtro

**Metas:**
- Definidas pelo Supervisor de Pesquisa (Técnico com FG ou substituto)
- Individual e coletiva, por tipo de pesquisa ou agregada
- Relatório semanal de entrega e apuração mensal vs. meta (exportável em Excel)

**Tipos de pesquisa:** Guia de ITBI, Ofertas — Aluguel, Ofertas — Vendas

**Implementação prevista para Fase 5 ou posterior.**

### 15.7 Otimização do mapa geral de imóveis
Com volume de 280mil+ imóveis no banco, carregar todos os marcadores
no mapa geral (/imoveis/mapa/) causa timeout e experiência ruim.

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
