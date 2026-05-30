# Diagrama Entidade-Relacionamento — SGBD DAI

O diagrama está dividido em três blocos temáticos para facilitar a leitura.
O GitHub renderiza os blocos abaixo automaticamente.

---

## Bloco A — Estrutura organizacional e segurança

```mermaid
erDiagram
  SERVIDOR {
    int id PK
    string nome
    string login
    string senha_hash
    string salt
    date data_ultimo_acesso
    int tentativas_falhas
    bool bloqueado
    string token_reset_senha
  }
  PERFIL_ACESSO {
    int id PK
    string nome
    bool pode_criar_os
    bool pode_encerrar_os
    bool pode_criar_os_interna
    bool pode_homologar
    bool visibilidade_total
    bool admin_sistema
  }
  UNIDADE_INTERNA {
    int id PK
    string sigla
    string nome
  }
  SERVIDOR_UNIDADE {
    int id PK
    int servidor_id FK
    int unidade_id FK
    int perfil_id FK
    string cargo
    bool substituto
    date data_inicio
    date data_fim
  }
  PERMISSAO_ESPECIAL {
    int id PK
    int servidor_id FK
    string tipo_permissao
    date data_inicio
    date data_fim
    int concedida_por_id FK
  }

  SERVIDOR        ||--o{ SERVIDOR_UNIDADE   : "lotado em"
  UNIDADE_INTERNA ||--o{ SERVIDOR_UNIDADE   : "contém"
  PERFIL_ACESSO   ||--o{ SERVIDOR_UNIDADE   : "define acesso"
  SERVIDOR        ||--o{ PERMISSAO_ESPECIAL : "recebe"
  SERVIDOR        ||--o{ PERMISSAO_ESPECIAL : "concede"
```

---

## Bloco B — OS, classificação, ciclo de vida, imóveis e produção

```mermaid
erDiagram
  OS {
    int id PK
    string numero_os
    date data_criacao_sgbd
    date data_entrada_divisao
    bool os_interna
    bool pendente_confirmacao
    string prioridade
    int natureza_id FK
    int tipo_demanda_id FK
    int finalidade_id FK
    int criado_por FK
    string observacao
  }
  PROCESSO_SEI {
    int id PK
    string numero_processo
    date data_abertura_sei
    string situacao
  }
  OS_PROCESSO {
    int id PK
    int os_id FK
    int processo_sei_id FK
    string tipo_vinculo
    date data_entrada_divisao
    date data_encerramento
    string motivo_encerramento
    int encerrado_por FK
  }
  NATUREZA {
    int id PK
    string descricao
    bool ativa
  }
  TIPO_DEMANDA {
    int id PK
    string descricao
    bool ativa
  }
  FINALIDADE {
    int id PK
    string descricao
    bool ativa
  }
  COMBINACAO_VALIDA {
    int id PK
    int natureza_id FK
    int tipo_demanda_id FK
    int finalidade_id FK
  }
  MACROETAPA_LOG {
    int id PK
    int os_id FK
    string macroetapa
    datetime data_hora
    int servidor_id FK
    bool automatico
    string observacao
  }
  ENCAMINHAMENTO {
    int id PK
    int os_id FK
    int unidade_interna_origem_id FK
    int servidor_origem_id FK
    int unidade_interna_destino_id FK
    int servidor_destino_id FK
    int unidade_externa_destino_id FK
    string etapa_interna
    string tipo_acao
    bool aguarda_retorno
    date data_retorno_prevista
    date data_retorno_efetiva
    datetime data_hora
    string observacao
  }
  TAREFA_INTERNA {
    int id PK
    int os_id FK
    int encaminhamento_id FK
    int unidade_id FK
    int servidor_id FK
    string etapa_interna
    string status
    datetime data_inicio
    datetime data_conclusao
  }
  IMOVEL {
    int id PK
    string tipo_identificacao
    string inscricao_cadastral
    string codigo_isic
    string endereco
    string bairro
    float area_referencia
    int exercicio_referencia
    string origem_dados
    bool editado_manualmente
    date data_ultima_importacao
    string observacao_interna
  }
  OS_IMOVEL {
    int id PK
    int os_id FK
    int imovel_id FK
  }
  PRODUCAO {
    int id PK
    int os_id FK
    int tipo_producao_id FK
    string numero_producao
    string numero_sei
    int ano
    string status
    int criado_por FK
    int homologado_por FK
    date data_homologacao
    string observacao
  }
  TIPO_PRODUCAO {
    int id PK
    string prefixo
    string descricao
    bool ativo
  }
  PRODUCAO_IMOVEL {
    int id PK
    int producao_id FK
    int imovel_id FK
    string grupo_ref
    string papel_no_grupo
    string observacao
  }
  PRODUCAO_IMOVEL_DADOS {
    int id PK
    int producao_imovel_id FK
    int exercicio
    float area_trabalho
    string endereco_trabalho
    string fonte
    date data_referencia
    string observacao_tecnica
    int editado_por FK
    datetime data_edicao
  }
  PRODUCAO_ATRIBUTO {
    int id PK
    int producao_id FK
    string chave
    string valor
  }

  OS              ||--o{ OS_PROCESSO           : "vincula"
  PROCESSO_SEI    ||--o{ OS_PROCESSO           : "referenciado em"
  OS              }o--|| NATUREZA              : "classificada por"
  OS              }o--|| TIPO_DEMANDA          : "classificada por"
  OS              }o--|| FINALIDADE            : "classificada por"
  NATUREZA        ||--o{ COMBINACAO_VALIDA     : "restringe"
  TIPO_DEMANDA    ||--o{ COMBINACAO_VALIDA     : "restringe"
  FINALIDADE      ||--o{ COMBINACAO_VALIDA     : "restringe"
  OS              ||--o{ MACROETAPA_LOG        : "registra"
  OS              ||--o{ ENCAMINHAMENTO        : "tramita via"
  ENCAMINHAMENTO  ||--o{ TAREFA_INTERNA        : "origina"
  OS              ||--o{ OS_IMOVEL             : "envolve"
  OS_IMOVEL       }o--|| IMOVEL               : "referencia"
  OS              ||--o{ PRODUCAO              : "gera"
  TIPO_PRODUCAO   ||--o{ PRODUCAO              : "classifica"
  PRODUCAO        ||--o{ PRODUCAO_IMOVEL       : "abrange"
  PRODUCAO_IMOVEL }o--|| IMOVEL               : "referencia"
  PRODUCAO_IMOVEL ||--o{ PRODUCAO_IMOVEL_DADOS : "detalha por exercicio"
  PRODUCAO        ||--o{ PRODUCAO_ATRIBUTO     : "tem atributos"
```

---

## Bloco C — Referências cruzadas, pesquisa e auditoria

```mermaid
erDiagram
  SERVIDOR {
    int id PK
    string nome
    string login
  }
  UNIDADE_INTERNA {
    int id PK
    string sigla
    string nome
  }
  UNIDADE_EXTERNA {
    int id PK
    string sigla
    string nome
    bool espera_retorno_padrao
    bool ativa
  }
  IMOVEL {
    int id PK
    string tipo_identificacao
    string inscricao_cadastral
    string codigo_isic
  }
  OS {
    int id PK
    string numero_os
    int criado_por FK
  }
  MACROETAPA_LOG {
    int id PK
    int os_id FK
    int servidor_id FK
    string macroetapa
    datetime data_hora
  }
  ENCAMINHAMENTO {
    int id PK
    int os_id FK
    int unidade_interna_origem_id FK
    int servidor_origem_id FK
    int unidade_interna_destino_id FK
    int servidor_destino_id FK
    int unidade_externa_destino_id FK
  }
  TAREFA_INTERNA {
    int id PK
    int os_id FK
    int unidade_id FK
    int servidor_id FK
    string etapa_interna
    string status
  }
  PRODUCAO {
    int id PK
    int os_id FK
    int criado_por FK
    int homologado_por FK
  }
  PRODUCAO_IMOVEL_DADOS {
    int id PK
    int producao_imovel_id FK
    int editado_por FK
    int exercicio
  }
  OS_PROCESSO {
    int id PK
    int os_id FK
    int encerrado_por FK
  }
  REGISTRO_PESQUISA {
    int id PK
    int servidor_id FK
    int imovel_id FK
    string numero_registro
    string tipo_fonte
    date data_registro
    date data_encaminhamento
    string tipo_pesquisa
    int semana_referencia
    int mes_referencia
    int ano_referencia
    string observacao
  }
  META_PESQUISA {
    int id PK
    int servidor_id FK
    int unidade_id FK
    int criado_por FK
    string tipo_meta
    string tipo_pesquisa
    int mes
    int ano
    int quantidade_meta
  }
  LOG_AUDITORIA {
    int id PK
    int servidor_id FK
    string entidade
    int entidade_id
    string operacao
    string campo_alterado
    string valor_anterior
    string valor_novo
    datetime data_hora
    string justificativa
  }

  SERVIDOR         ||--o{ OS                    : "cria"
  SERVIDOR         ||--o{ MACROETAPA_LOG         : "registra"
  SERVIDOR         ||--o{ ENCAMINHAMENTO         : "origina"
  SERVIDOR         ||--o{ ENCAMINHAMENTO         : "recebe"
  SERVIDOR         ||--o{ TAREFA_INTERNA         : "executa"
  SERVIDOR         ||--o{ PRODUCAO               : "cria"
  SERVIDOR         ||--o{ PRODUCAO               : "homologa"
  SERVIDOR         ||--o{ PRODUCAO_IMOVEL_DADOS  : "edita"
  SERVIDOR         ||--o{ OS_PROCESSO            : "encerra"
  SERVIDOR         ||--o{ REGISTRO_PESQUISA      : "realiza"
  SERVIDOR         ||--o{ META_PESQUISA          : "tem meta"
  SERVIDOR         ||--o{ META_PESQUISA          : "cria meta"
  SERVIDOR         ||--o{ LOG_AUDITORIA          : "gera"
  UNIDADE_INTERNA  ||--o{ ENCAMINHAMENTO         : "origem"
  UNIDADE_INTERNA  ||--o{ ENCAMINHAMENTO         : "destino interno"
  UNIDADE_INTERNA  ||--o{ TAREFA_INTERNA         : "responsavel"
  UNIDADE_INTERNA  ||--o{ META_PESQUISA          : "meta coletiva"
  UNIDADE_EXTERNA  ||--o{ ENCAMINHAMENTO         : "destino externo"
  IMOVEL           ||--o{ REGISTRO_PESQUISA      : "objeto de pesquisa"
```
