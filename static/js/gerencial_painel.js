/**
 * Painel lateral da visão gerencial SIPRAC.
 * Depende de: bootstrap, painelDados (JSON), csrfToken, tiposProducao.
 */
(function (window) {
  'use strict';

  const STATUS_SUGESTOES = {
    data_entrega_avaliacao: { de: 'DISTRIBUIDO', para: 'REVISAR', msg: 'Entregar para revisão?' },
    data_entrega_revisao: { de: 'REVISAR', para: 'REVISADO', msg: 'Marcar como revisado?' },
    data_entrega_ajustes: { de: 'VER_AJUSTES', para: 'ENTREGA_AJUSTES', msg: 'Entregar ajustes?' },
    data_ajustes_ok: { de: 'ENTREGA_AJUSTES', para: 'HOMOLOGAR', msg: 'Aprovar ajustes?' },
    data_enviado: { de: 'HOMOLOGAR', para: 'ENVIADO', msg: 'Marcar como enviado?' },
  };

  const STATUS_LABELS = {
    REVISAR: 'Revisar',
    REVISADO: 'Revisado',
    ENTREGA_AJUSTES: 'Entrega ajustes',
    HOMOLOGAR: 'Homologar',
    ENVIADO: 'Enviado',
  };

  function escapeHtml(text) {
    const div = document.createElement('div');
    div.textContent = text == null ? '' : String(text);
    return div.innerHTML;
  }

  function hojeISO() {
    const d = new Date();
    return d.getFullYear() + '-' +
      String(d.getMonth() + 1).padStart(2, '0') + '-' +
      String(d.getDate()).padStart(2, '0');
  }

  function postJson(url, payload) {
    return fetch(url, {
      method: 'POST',
      credentials: 'same-origin',
      headers: {
        'Content-Type': 'application/json',
        'X-CSRFToken': window.gerencialCsrfToken,
        'X-Requested-With': 'XMLHttpRequest',
        'Accept': 'application/json',
      },
      body: JSON.stringify(payload || {}),
    }).then(function (r) {
      return r.json().then(function (data) {
        if (!r.ok || data.sucesso === false) {
          throw new Error(data.erro || 'Erro na operação.');
        }
        return data;
      });
    });
  }

  function postCampo(url, campo, valor) {
    const formData = new FormData();
    formData.append('campo', campo);
    formData.append('valor', valor || '');
    formData.append('csrfmiddlewaretoken', window.gerencialCsrfToken);
    return fetch(url, {
      method: 'POST',
      credentials: 'same-origin',
      headers: { 'X-Requested-With': 'XMLHttpRequest', 'Accept': 'application/json' },
      body: formData,
    }).then(function (r) {
      return r.json().then(function (data) {
        if (!r.ok || !data.sucesso) throw new Error(data.erro || 'Erro ao salvar.');
        return data;
      });
    });
  }

  function getJson(url) {
    return fetch(url, {
      credentials: 'same-origin',
      headers: { 'Accept': 'application/json', 'X-Requested-With': 'XMLHttpRequest' },
    }).then(function (r) {
      return r.json().then(function (data) {
        if (!r.ok) throw new Error(data.erro || 'Erro ao carregar.');
        return data;
      });
    });
  }

  function optionsHtml(lista, selected) {
    return (lista || []).map(function (item) {
      const sel = String(item.pk || item.id) === String(selected || '') ? ' selected' : '';
      return '<option value="' + (item.pk || item.id) + '"' + sel + '>' +
        escapeHtml(item.nome) + '</option>';
    }).join('');
  }

  function renderCampo(label, inner, extraId) {
    return '<div class="painel-campo"' + (extraId ? ' id="' + extraId + '"' : '') + '>' +
      '<label>' + escapeHtml(label) + '</label>' + inner +
      '</div>';
  }

  function renderCampoData(prodPk, campo, label, valor, secaoId) {
    return renderCampo(
      label,
      '<input type="date" data-prod="' + prodPk + '" data-campo="' + campo + '" value="' +
      escapeHtml(valor || '') + '">' +
      '<button type="button" class="btn btn-outline-primary btn-sm py-0 px-2" data-salvar-prod="' +
      prodPk + '" data-campo="' + campo + '">Salvar</button>',
      secaoId || '',
    );
  }

  function renderTransicoes(prod, osPk) {
    return (prod.transicoes || []).map(function (t) {
      const cls = t.botao_classe || 'btn-outline-secondary';
      return '<button type="button" class="btn painel-btn-transicao ' + cls +
        '" data-transicao-prod="' + prod.pk + '" data-status="' + t.destino + '">→ ' +
        escapeHtml(t.label) + '</button>';
    }).join(' ');
  }

  function renderProducaoAccordion(prod, data, expandido) {
    const bodyStyle = expandido ? '' : ' style="display:none;"';
    const arrow = expandido ? '▼' : '▶';
    let html = '<div class="painel-accordion" id="painel-prod-' + prod.pk + '">';
    html += '<div class="painel-accordion-header" data-toggle-prod="' + prod.pk + '">';
    html += '<span>' + arrow + '</span>';
    html += '<span class="flex-grow-1">' + escapeHtml(prod.prefixo + ' — ' + prod.label) + '</span>';
    html += '<span class="badge bg-' + prod.status_cor + '">' + escapeHtml(prod.status_label) + '</span>';
    html += '</div>';
    html += '<div class="painel-accordion-body"' + bodyStyle + ' id="painel-secao-prod-' + prod.pk + '">';
    html += '<div class="d-flex flex-wrap gap-1 mb-2" id="painel-transicoes-' + prod.pk + '">';
    html += renderTransicoes(prod, data.os_pk);
    html += '</div>';
    html += '<div id="painel-sugestao-' + prod.pk + '"></div>';

    html += '<div class="small fw-semibold text-muted mb-1">Triagem</div>';
    html += renderCampoData(prod.pk, 'prazo_interno', 'Prazo EAV', prod.prazo_eav_iso,
      'painel-campo-prazo-eav-' + prod.pk);
    html += renderCampo('Cronograma',
      '<input type="month" data-prod="' + prod.pk + '" data-campo="mes_cronograma" value="' +
      escapeHtml(prod.mes_cronograma_iso || '') + '">' +
      '<button type="button" class="btn btn-outline-primary btn-sm py-0 px-2" data-salvar-prod="' +
      prod.pk + '" data-campo="mes_cronograma">Salvar</button>');
    html += renderCampo('Modelo sug.',
      '<input type="text" data-prod="' + prod.pk + '" data-campo="modelo_sugerido" value="' +
      escapeHtml(prod.modelo_sugerido || '') + '">' +
      '<button type="button" class="btn btn-outline-primary btn-sm py-0 px-2" data-salvar-prod="' +
      prod.pk + '" data-campo="modelo_sugerido">Salvar</button>');

    html += '<div class="small fw-semibold text-muted mb-1 mt-2">Distribuição</div>';
    html += renderCampo('Avaliador',
      '<select data-prod="' + prod.pk + '" data-campo="servidor_responsavel">' +
      '<option value="">—</option>' + optionsHtml(data.servidores_unidade, prod.avaliador_id) +
      '</select>' +
      '<button type="button" class="btn btn-outline-primary btn-sm py-0 px-2" data-salvar-prod="' +
      prod.pk + '" data-campo="servidor_responsavel">Salvar</button>',
      'painel-campo-avaliador-' + prod.pk);
    html += renderCampoData(prod.pk, 'prazo_aval', 'Prazo aval', prod.prazo_aval_iso);
    html += renderCampoData(prod.pk, 'data_entrega_avaliacao', 'Entrega aval', prod.entrega_aval_iso);

    html += '<div class="small fw-semibold text-muted mb-1 mt-2">Revisão</div>';
    html += renderCampo('Revisor',
      '<select data-prod="' + prod.pk + '" data-campo="revisor">' +
      '<option value="">—</option>' + optionsHtml(data.revisores_unidade, prod.revisor_id) +
      '</select>' +
      '<button type="button" class="btn btn-outline-primary btn-sm py-0 px-2" data-salvar-prod="' +
      prod.pk + '" data-campo="revisor">Salvar</button>');
    html += renderCampoData(prod.pk, 'prazo_rev', 'Prazo rev', prod.prazo_rev_iso);
    html += renderCampoData(prod.pk, 'data_entrega_revisao', 'Entrega rev', prod.entrega_rev_iso);
    html += renderCampoData(prod.pk, 'data_entrega_ajustes', 'Entrega aju', prod.entrega_aju_iso);

    html += '<div class="small fw-semibold text-muted mb-1 mt-2">Homologação</div>';
    html += renderCampoData(prod.pk, 'data_ajustes_ok', 'Ajustes OK', prod.data_ajustes_ok_iso);
    html += renderCampo('Nº trabalho',
      '<input type="text" data-prod="' + prod.pk + '" data-campo="numero_producao" value="' +
      escapeHtml(prod.numero_producao || '') + '">' +
      '<button type="button" class="btn btn-outline-primary btn-sm py-0 px-2" data-salvar-prod="' +
      prod.pk + '" data-campo="numero_producao">Salvar</button>');
    html += renderCampo('DOC SEI',
      '<input type="text" data-prod="' + prod.pk + '" data-campo="numero_sei" value="' +
      escapeHtml(prod.numero_sei || '') + '">' +
      '<button type="button" class="btn btn-outline-primary btn-sm py-0 px-2" data-salvar-prod="' +
      prod.pk + '" data-campo="numero_sei">Salvar</button>');
    html += renderCampoData(prod.pk, 'data_enviado', 'Envio SEI', prod.enviado_iso);

    if (prod.status === 'ENVIADO' && prod.opcoes_pos_enviado && prod.opcoes_pos_enviado.length) {
      html += '<div class="mt-2 small">';
      prod.opcoes_pos_enviado.forEach(function (op) {
        if (op.acao === 'manter') {
          html += '<span class="text-muted me-2">Manter em atendimento</span>';
        } else if (op.url) {
          html += '<a href="' + escapeHtml(op.url) + '" class="btn btn-outline-primary btn-sm me-1">' +
            escapeHtml(op.label) + '</a>';
        }
      });
      html += '</div>';
    }

    html += '<div class="mt-2">';
    html += '<button type="button" class="btn btn-link btn-sm p-0 text-decoration-none" data-expand-coment="' +
      prod.pk + '">+ Comentários (' + (prod.total_comentarios || 0) + ')</button>';
    html += '<div id="painel-coment-prod-' + prod.pk + '" style="display:none;" class="mt-1"></div>';
    html += '</div>';
    html += '<div class="mt-1">';
    html += '<button type="button" class="btn btn-link btn-sm p-0 text-decoration-none" data-expand-log="' +
      prod.pk + '">+ Histórico de status (' + (prod.status_log || []).length + ')</button>';
    html += '<div id="painel-log-prod-' + prod.pk + '" style="display:none;" class="mt-1 small"></div>';
    html += '</div>';

    html += '</div></div>';
    return html;
  }

  function renderPanel(data) {
    let html = '';
    html += '<div class="painel-secao painel-cabecalho" id="painel-secao-topo">';
    html += '<div class="d-flex justify-content-between align-items-start mb-2">';
    html += '<div>';
    html += '<div class="fw-bold fs-6"><a href="/os/' + data.os_pk + '/" class="text-decoration-none">' +
      escapeHtml(data.numero_os) + '</a></div>';
    (data.processos || []).forEach(function (p) {
      html += '<div class="small text-muted">' + escapeHtml(p.numero) + '</div>';
    });
    if (!data.processos || !data.processos.length) {
      html += '<div class="small text-muted">' + escapeHtml(data.processo_sei || '—') + '</div>';
    }
    html += '</div>';
    html += '<button type="button" class="btn btn-sm btn-outline-secondary" id="painelBtnFechar">✕ Fechar</button>';
    html += '</div>';
    if (data.pode_criar_producao && data.os_editavel) {
      html += '<button type="button" class="btn btn-success btn-sm mb-2" id="painelBtnNovaProd">+ Nova produção</button>';
    }
    html += '<div id="painelNovaProdForm" style="display:none;" class="border rounded p-2 mb-2 bg-light"></div>';
    html += '<a href="/os/' + data.os_pk + '/" class="small">Ver OS completa →</a>';
    html += '</div>';

    html += '<div class="painel-secao" id="painel-secao-macroetapa">';
    html += '<div class="painel-secao-titulo">Macroetapa</div>';
    html += '<span class="badge bg-' + (data.macroetapa_cor || 'secondary') + '">' +
      escapeHtml(data.macroetapa_label || '—') + '</span>';
    html += '</div>';

    html += '<div class="painel-secao" id="painel-secao-etapa">';
    html += '<div class="painel-secao-titulo">① Etapa na unidade</div>';
    html += '<span class="badge bg-primary mb-2" id="painelEtapaBadge">' +
      escapeHtml(data.etapa_interna_label || data.etapa_interna || '—') + '</span>';
    if (data.os_editavel && (data.etapa_interna_choices || []).length) {
      html += '<div class="d-flex flex-wrap gap-1" id="painelEtapaTransicoes">';
      data.etapa_interna_choices.forEach(function (c) {
        html += '<button type="button" class="btn btn-outline-primary btn-sm painel-btn-transicao" data-etapa="' +
          c.valor + '">→ ' + escapeHtml(c.label) + '</button>';
      });
      html += '</div>';
    }
    html += '</div>';

    html += '<div class="painel-secao" id="painel-secao-producoes">';
    html += '<div class="d-flex justify-content-between align-items-center mb-2">';
    html += '<div class="painel-secao-titulo mb-0">② Produções</div>';
    if (data.pode_criar_producao && data.os_editavel) {
      html += '<button type="button" class="btn btn-success btn-sm py-0" id="painelBtnNovaProd2">+ Nova</button>';
    }
    html += '</div>';
    if (!(data.producoes || []).length) {
      html += '<p class="small text-muted mb-0">Nenhuma produção.</p>';
    }
    (data.producoes || []).forEach(function (prod) {
      const expandido = prod.pk === data.producao_pk_ativa;
      html += renderProducaoAccordion(prod, data, expandido);
    });
    html += '</div>';

    html += '<div class="painel-secao" id="painel-secao-comentarios">';
    html += '<div class="painel-secao-titulo">③ Comentários da OS</div>';
    html += '<div id="painelComentariosOs" class="small mb-2">';
    (data.comentarios_os || []).forEach(function (c) {
      html += '<div class="border-bottom pb-1 mb-1"><strong>' + escapeHtml(c.servidor) +
        '</strong> <span class="text-muted">' + escapeHtml(c.data_hora) + '</span><div>' +
        escapeHtml(c.texto) + '</div></div>';
    });
    if (!(data.comentarios_os || []).length) {
      html += '<em class="text-muted">Nenhum comentário.</em>';
    }
    html += '</div>';
    html += '<textarea class="form-control form-control-sm mb-1" id="painelComentarioOsTexto" rows="2" placeholder="Novo comentário…"></textarea>';
    html += '<button type="button" class="btn btn-primary btn-sm" id="painelComentarioOsBtn">Comentar</button>';
    html += '</div>';

    return html;
  }

  function mostrarSugestao(prodPk, campo, prod) {
    const regra = STATUS_SUGESTOES[campo];
    if (!regra || prod.status !== regra.de) return;
    const el = document.getElementById('painel-sugestao-' + prodPk);
    if (!el) return;
    el.innerHTML = '<div class="painel-sugestao-status">' +
      escapeHtml(regra.msg) +
      ' <button type="button" class="btn btn-warning btn-sm py-0" data-sugestao-prod="' + prodPk +
      '" data-status="' + regra.para + '">→ ' + (STATUS_LABELS[regra.para] || regra.para) +
      '</button> <button type="button" class="btn btn-link btn-sm py-0" data-dismiss-sugestao="' +
      prodPk + '">Não</button></div>';
  }

  function bindPanelEvents(data, ctx) {
    const osPk = data.os_pk;
    const conteudo = ctx.painelConteudo;

    conteudo.querySelector('#painelBtnFechar')?.addEventListener('click', ctx.fecharPainel);

    function abrirFormNovaProd() {
      const formEl = conteudo.querySelector('#painelNovaProdForm');
      if (!formEl) return;
      let fh = '<label class="form-label small">Tipo de produção</label>';
      fh += '<select class="form-select form-select-sm mb-2" id="painelTipoProd">';
      (window.gerencialTiposProducao || []).forEach(function (tp) {
        fh += '<option value="' + tp.id + '">' + escapeHtml(tp.label) + '</option>';
      });
      fh += '</select><label class="form-label small">Observação</label>';
      fh += '<textarea class="form-control form-control-sm mb-2" id="painelObsProd" rows="2"></textarea>';
      fh += '<button type="button" class="btn btn-success btn-sm me-1" id="painelSalvarNovaProd">Registrar</button>';
      fh += '<button type="button" class="btn btn-outline-secondary btn-sm" id="painelCancelNovaProd">Cancelar</button>';
      formEl.innerHTML = fh;
      formEl.style.display = 'block';
      formEl.querySelector('#painelCancelNovaProd').addEventListener('click', function () {
        formEl.style.display = 'none';
      });
      formEl.querySelector('#painelSalvarNovaProd').addEventListener('click', function () {
        postJson('/os/' + osPk + '/producao/nova/', {
          tipo_producao: formEl.querySelector('#painelTipoProd').value,
          observacao: formEl.querySelector('#painelObsProd').value,
        }).then(function () { location.reload(); })
          .catch(function (e) { alert(e.message); });
      });
    }

    conteudo.querySelector('#painelBtnNovaProd')?.addEventListener('click', abrirFormNovaProd);
    conteudo.querySelector('#painelBtnNovaProd2')?.addEventListener('click', abrirFormNovaProd);

    conteudo.querySelectorAll('[data-etapa]').forEach(function (btn) {
      btn.addEventListener('click', function () {
        postJson('/api/os/' + osPk + '/etapa/', { etapa_interna: btn.dataset.etapa })
          .then(function (resp) {
            const badge = conteudo.querySelector('#painelEtapaBadge');
            if (badge) badge.textContent = resp.etapa_label || btn.dataset.etapa;
            btn.closest('#painelEtapaTransicoes')?.removeChild(btn);
          })
          .catch(function (e) { alert(e.message); });
      });
    });

    conteudo.querySelectorAll('[data-toggle-prod]').forEach(function (hdr) {
      hdr.addEventListener('click', function () {
        const pk = hdr.dataset.toggleProd;
        const body = conteudo.querySelector('#painel-prod-' + pk + ' .painel-accordion-body');
        if (!body) return;
        const vis = body.style.display !== 'none';
        body.style.display = vis ? 'none' : 'block';
        hdr.querySelector('span').textContent = vis ? '▶' : '▼';
      });
    });

    conteudo.querySelectorAll('[data-transicao-prod]').forEach(function (btn) {
      btn.addEventListener('click', function (e) {
        e.stopPropagation();
        postJson('/api/producao/' + btn.dataset.transicaoProd + '/status/', {
          status: btn.dataset.status,
          data: hojeISO(),
        }).then(function () { location.reload(); })
          .catch(function (err) { alert(err.message); });
      });
    });

    conteudo.querySelectorAll('[data-salvar-prod]').forEach(function (btn) {
      btn.addEventListener('click', function () {
        const prodPk = btn.dataset.salvarProd;
        const campo = btn.dataset.campo;
        const input = conteudo.querySelector('[data-prod="' + prodPk + '"][data-campo="' + campo + '"]');
        const valor = input ? input.value : '';
        postCampo('/producoes/' + prodPk + '/editar-campo/', campo, valor)
          .then(function () {
            const prod = (data.producoes || []).find(function (p) { return String(p.pk) === String(prodPk); });
            if (prod && campo.endsWith('_iso') === false) {
              if (campo.indexOf('data_') === 0 || campo.indexOf('prazo_') === 0) {
                prod[campo.replace('data_', '').replace('prazo_', '') + '_iso'] = valor;
              }
              mostrarSugestao(prodPk, campo, prod);
            }
            if (prod && STATUS_SUGESTOES[campo]) {
              mostrarSugestao(prodPk, campo, prod);
            }
            if (ctx.atualizarCelula && ctx.colMap[campo]) {
              ctx.atualizarCelula(osPk, ctx.colMap[campo], escapeHtml(valor || '—'), prodPk);
            }
          })
          .catch(function (e) { alert(e.message); });
      });
    });

    conteudo.addEventListener('click', function (e) {
      const sug = e.target.closest('[data-sugestao-prod]');
      if (sug) {
        postJson('/api/producao/' + sug.dataset.sugestaoProd + '/status/', {
          status: sug.dataset.status,
          data: hojeISO(),
        }).then(function () { location.reload(); })
          .catch(function (err) { alert(err.message); });
      }
      const dismiss = e.target.closest('[data-dismiss-sugestao]');
      if (dismiss) {
        const el = document.getElementById('painel-sugestao-' + dismiss.dataset.dismissSugestao);
        if (el) el.innerHTML = '';
      }
    });

    conteudo.querySelectorAll('[data-expand-coment]').forEach(function (btn) {
      btn.addEventListener('click', function () {
        const pk = btn.dataset.expandComent;
        const box = conteudo.querySelector('#painel-coment-prod-' + pk);
        if (!box || box.style.display === 'block') {
          if (box) box.style.display = 'none';
          return;
        }
        box.style.display = 'block';
        box.innerHTML = 'Carregando…';
        getJson('/api/os/' + osPk + '/comentarios/?producao=' + pk).then(function (resp) {
          let ch = '';
          (resp.comentarios || []).forEach(function (c) {
            ch += '<div class="mb-1"><strong>' + escapeHtml(c.servidor) + '</strong> ' +
              escapeHtml(c.data_hora) + '<div>' + escapeHtml(c.texto) + '</div></div>';
          });
          ch += '<textarea class="form-control form-control-sm mt-1" rows="2" id="comentProdTxt' + pk + '"></textarea>';
          ch += '<button type="button" class="btn btn-sm btn-primary mt-1" id="comentProdBtn' + pk + '">Enviar</button>';
          box.innerHTML = ch;
          box.querySelector('#comentProdBtn' + pk).addEventListener('click', function () {
            postJson('/api/os/' + osPk + '/comentarios/', {
              texto: box.querySelector('#comentProdTxt' + pk).value,
              producao: pk,
            }).then(function (r) {
              box.innerHTML = '';
              (r.comentarios || []).forEach(function (c) {
                box.innerHTML += '<div class="mb-1"><strong>' + escapeHtml(c.servidor) +
                  '</strong> ' + escapeHtml(c.data_hora) + '<div>' + escapeHtml(c.texto) + '</div></div>';
              });
            }).catch(function (e) { alert(e.message); });
          });
        }).catch(function (e) { box.textContent = e.message; });
      });
    });

    conteudo.querySelectorAll('[data-expand-log]').forEach(function (btn) {
      btn.addEventListener('click', function () {
        const pk = btn.dataset.expandLog;
        const box = conteudo.querySelector('#painel-log-prod-' + pk);
        if (!box) return;
        if (box.style.display === 'block') {
          box.style.display = 'none';
          return;
        }
        const prod = (data.producoes || []).find(function (p) { return String(p.pk) === String(pk); });
        let lh = '';
        ((prod && prod.status_log) || []).forEach(function (log) {
          lh += '<div class="text-muted">' + escapeHtml(log.data_hora) + ': ' +
            escapeHtml(log.status_anterior_label || '—') + ' → ' +
            escapeHtml(log.status_novo_label) + '</div>';
        });
        box.innerHTML = lh || '<em>Sem histórico.</em>';
        box.style.display = 'block';
      });
    });

    conteudo.querySelector('#painelComentarioOsBtn')?.addEventListener('click', function () {
      const texto = conteudo.querySelector('#painelComentarioOsTexto')?.value || '';
      if (!texto.trim()) return;
      postJson('/api/os/' + osPk + '/comentarios/', { texto: texto })
        .then(function (resp) {
          const lista = conteudo.querySelector('#painelComentariosOs');
          if (lista) {
            lista.innerHTML = (resp.comentarios || []).map(function (c) {
              return '<div class="border-bottom pb-1 mb-1"><strong>' + escapeHtml(c.servidor) +
                '</strong> <span class="text-muted">' + escapeHtml(c.data_hora) + '</span><div>' +
                escapeHtml(c.texto) + '</div></div>';
            }).join('') || '<em class="text-muted">Nenhum comentário.</em>';
          }
          conteudo.querySelector('#painelComentarioOsTexto').value = '';
        })
        .catch(function (e) { alert(e.message); });
    });
  }

  function scrollParaSecao(secao, data) {
    const map = {
      topo: 'painel-secao-topo',
      etapa: 'painel-secao-etapa',
      producoes: 'painel-secao-producoes',
      comentarios: 'painel-secao-comentarios',
      avaliador: data.producao_pk_ativa ? 'painel-campo-avaliador-' + data.producao_pk_ativa : 'painel-secao-producoes',
      'prazo-eav': data.producao_pk_ativa ? 'painel-campo-prazo-eav-' + data.producao_pk_ativa : 'painel-secao-producoes',
    };
    const id = map[secao] || map.topo;
    document.getElementById(id)?.scrollIntoView({ behavior: 'smooth', block: 'start' });
  }

  window.GerencialPainel = {
    renderPanel: renderPanel,
    bindPanelEvents: bindPanelEvents,
    scrollParaSecao: scrollParaSecao,
  };
})(window);
