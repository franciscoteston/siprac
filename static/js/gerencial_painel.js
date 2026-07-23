/**
 * Painel lateral da visão gerencial SIPRAC.
 * Depende de: bootstrap, painelDados (JSON), csrfToken, tiposProducao.
 */
(function (window) {
  'use strict';

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

  function postCampo(url, campo, valor, extras) {
    const formData = new FormData();
    formData.append('campo', campo);
    formData.append('valor', valor || '');
    formData.append('csrfmiddlewaretoken', window.gerencialCsrfToken);
    if (extras) {
      Object.keys(extras).forEach(function (k) {
        if (extras[k] != null) formData.append(k, extras[k]);
      });
    }
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

  function postForm(url, fields) {
    const formData = new FormData();
    formData.append('csrfmiddlewaretoken', window.gerencialCsrfToken);
    Object.keys(fields || {}).forEach(function (k) {
      if (fields[k] != null) formData.append(k, fields[k]);
    });
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

  function formatarDataIsoBr(iso) {
    if (!iso) return '—';
    const m = String(iso).match(/^(\d{4})-(\d{2})-(\d{2})/);
    if (m) return m[3] + '/' + m[2] + '/' + m[1];
    return String(iso);
  }

  function renderHistoricoHtml(itens) {
    if (!(itens || []).length) {
      return '<em class="text-muted small">Nenhuma alteração neste ciclo.</em>';
    }
    return itens.map(function (h) {
      return '<div class="border-bottom py-1" style="font-size:11px;color:#495057;">' +
        '<div style="font-weight:600;color:#1a3a5c;font-size:10px;">' +
        escapeHtml(h.data_hora) + ' · ' + escapeHtml(h.servidor || '—') + '</div>' +
        '<div>' + escapeHtml(formatarDataIsoBr(h.valor_anterior) || '—') +
        ' → ' + escapeHtml(formatarDataIsoBr(h.valor_novo) || '—') + '</div>' +
        (h.justificativa
          ? '<div class="text-muted" style="font-size:10px;">' + escapeHtml(h.justificativa) + '</div>'
          : '') +
        '</div>';
    }).join('');
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

  function secaoTitulo(texto) {
    return '<div style="font-size:10px;font-weight:700;text-transform:uppercase;' +
      'color:#6c757d;letter-spacing:0.8px;margin-bottom:8px;">' +
      escapeHtml(texto) + '</div>';
  }

  function renderCampo(label, inputHtml, extraId) {
    return '<div class="d-flex align-items-center gap-2 mb-2"' +
      (extraId ? ' id="' + extraId + '"' : '') + '>' +
      '<label style="font-size:11px;color:#6c757d;min-width:85px;flex-shrink:0;">' +
      escapeHtml(label) + '</label>' + inputHtml + '</div>';
  }

  function btnSalvar(prodPk, campo) {
    return '<button type="button" class="btn btn-sm btn-outline-primary"' +
      ' style="font-size:11px;white-space:nowrap;padding:2px 8px;"' +
      ' data-salvar-prod="' + prodPk + '" data-campo="' + campo + '">Salvar</button>';
  }

  function renderCampoData(prodPk, campo, label, valor, secaoId) {
    return renderCampo(
      label,
      '<input type="date" class="form-control form-control-sm" style="font-size:11px;"' +
      ' data-prod="' + prodPk + '" data-campo="' + campo + '" value="' +
      escapeHtml(valor || '') + '">' + btnSalvar(prodPk, campo),
      secaoId || '',
    );
  }

  function renderCampoTexto(prodPk, campo, label, valor, tipo) {
    tipo = tipo || 'text';
    return renderCampo(
      label,
      '<input type="' + tipo + '" class="form-control form-control-sm" style="font-size:11px;"' +
      ' data-prod="' + prodPk + '" data-campo="' + campo + '" value="' +
      escapeHtml(valor || '') + '">' + btnSalvar(prodPk, campo),
    );
  }

  function renderCampoSelect(prodPk, campo, label, optionsHtmlStr, secaoId) {
    return renderCampo(
      label,
      '<select class="form-select form-select-sm" style="font-size:11px;"' +
      ' data-prod="' + prodPk + '" data-campo="' + campo + '">' + optionsHtmlStr + '</select>' +
      btnSalvar(prodPk, campo),
      secaoId || '',
    );
  }

  function renderProducaoAccordion(prod, data, expandido) {
    const bodyStyle = expandido ? '' : ' style="display:none;"';
    let html = '<div class="card mb-2 border" id="painel-prod-' + prod.pk + '">';
    html += '<div class="card-header p-2 d-flex align-items-center gap-2"' +
      ' style="cursor:pointer;background:#f0f4f8;" data-toggle-prod="' + prod.pk + '">';
    html += '<span style="font-size:12px;font-weight:600;color:#1a3a5c;flex:1;">' +
      escapeHtml(prod.label || '') + '</span>';
    html += '<span class="badge bg-' + prod.status_cor + '">' + escapeHtml(prod.status_label) + '</span>';
    html += '<i class="bi bi-chevron-' + (expandido ? 'up' : 'down') + '" style="font-size:10px;"></i>';
    html += '</div>';
    html += '<div class="card-body p-2" id="painel-secao-prod-' + prod.pk + '"' + bodyStyle + '>';

    if (prod.pode_cancelar && data.os_editavel) {
      html += '<div class="d-flex gap-1 flex-wrap mb-2" id="painel-transicoes-' + prod.pk + '">' +
        '<button type="button" class="btn btn-sm btn-outline-danger"' +
        ' style="font-size:11px;padding:2px 8px;"' +
        ' data-cancelar-prod="' + prod.pk + '">Cancelar</button></div>';
    }

    html += '<div class="text-muted mb-1" style="font-size:11px;font-weight:600;">Dados</div>';
    html += renderCampoTexto(prod.pk, 'numero_producao', 'Nº trabalho', prod.numero_producao);
    html += renderCampoTexto(prod.pk, 'numero_sei', 'DOC SEI', prod.numero_sei);
    if (prod.enviado_iso) {
      const partes = prod.enviado_iso.split('-');
      const enviadoBr = partes.length === 3
        ? (partes[2] + '/' + partes[1] + '/' + partes[0])
        : prod.enviado_iso;
      html += renderCampo('Envio SEI', '<span style="font-size:11px;">' + escapeHtml(enviadoBr) + '</span>');
    } else {
      html += renderCampo('Envio SEI', '<span style="font-size:11px;">—</span>');
    }

    html += '<button type="button" class="btn btn-link btn-sm p-0 mt-2 text-decoration-none"' +
      ' style="font-size:11px;" data-expand-coment="' + prod.pk +
      '">+ Comentários (' + (prod.total_comentarios || 0) + ')</button>';
    html += '<div id="painel-coment-prod-' + prod.pk + '" class="mt-1" style="display:none;"></div>';
    html += '<button type="button" class="btn btn-link btn-sm p-0 mt-1 text-decoration-none d-block"' +
      ' style="font-size:11px;" data-expand-log="' + prod.pk +
      '">+ Histórico de status (' + (prod.status_log || []).length + ')</button>';
    html += '<div id="painel-log-prod-' + prod.pk + '" class="mt-1 small" style="display:none;"></div>';

    html += '</div></div>';
    return html;
  }

  function renderPanel(data) {
    const btnHeaderStyle = 'font-size:11px;padding:3px 10px;border-radius:4px;' +
      'background:rgba(255,255,255,0.15);color:white;' +
      'border:1px solid rgba(255,255,255,0.3);text-decoration:none;cursor:pointer;';

    let header = '';
    header += '<div class="d-flex justify-content-between align-items-start">';
    header += '<div>';
    header += '<a href="/os/' + data.os_pk + '/" class="painel-os-numero"' +
      ' style="color:white;font-weight:700;font-size:14px;text-decoration:none;">' +
      escapeHtml(data.numero_os) + '</a>';
    (data.processos || []).forEach(function (p) {
      header += '<div style="font-size:11px;color:#adb5bd;">' + escapeHtml(p.numero) + '</div>';
    });
    if (!data.processos || !data.processos.length) {
      header += '<div style="font-size:11px;color:#adb5bd;">' +
        escapeHtml(data.processo_sei || '—') + '</div>';
    }
    header += '</div>';
    header += '<button type="button" id="painelBtnFechar" title="Fechar"' +
      ' style="background:transparent;border:none;color:#adb5bd;font-size:20px;' +
      'cursor:pointer;line-height:1;padding:0;">×</button>';
    header += '</div>';
    header += '<div class="mt-2 d-flex gap-2 flex-wrap">';
    header += '<a href="/os/' + data.os_pk + '/" style="' + btnHeaderStyle + '">Ver OS completa →</a>';
    if (data.pode_criar_producao && data.os_editavel) {
      header += '<button type="button" id="painelBtnNovaProd" style="' + btnHeaderStyle +
        '">+ Nova produção</button>';
    }
    header += '</div>';

    let body = '';
    body += '<div id="painelNovaProdForm" class="painel-nova-producao m-2" style="display:none;"></div>';

    body += '<div class="p-3 border-bottom bg-white">';
    body += secaoTitulo('Macroetapa');
    body += '<span class="badge rounded-pill" style="background:#e8eef5;color:#1a3a5c;' +
      'font-size:12px;font-weight:600;padding:5px 12px;">' +
      escapeHtml(data.macroetapa_label || '—') + '</span>';
    body += '</div>';

    body += '<div class="p-3 border-bottom bg-white mt-1" id="painel-secao-etapa">';
    body += secaoTitulo('① Etapa na unidade');
    body += '<span class="badge bg-primary" id="painelEtapaBadge">' +
      escapeHtml(data.etapa_interna_label || data.etapa_interna || '—') + '</span>';
    if (data.os_editavel && (data.etapa_interna_choices || []).length) {
      body += '<div class="d-flex gap-1 flex-wrap mt-2" id="painelEtapaTransicoes">';
      data.etapa_interna_choices.forEach(function (c) {
        body += '<button type="button" class="btn btn-sm btn-outline-secondary"' +
          ' style="font-size:11px;padding:2px 8px;" data-etapa="' + c.valor +
          '">→ ' + escapeHtml(c.label) + '</button>';
      });
      body += '</div>';
    }
    body += '</div>';

    const prazos = data.prazos || {};
    body += '<div class="p-3 border-bottom bg-white mt-1" id="painel-secao-prazos">';
    body += secaoTitulo('Prazos');
    body += '<div class="mb-2" style="font-size:12px;">';
    body += '<div class="d-flex justify-content-between align-items-center gap-2 flex-wrap">';
    body += '<div><span class="text-muted">Prazo OS:</span> ';
    body += '<strong id="painelPrazoOsDisplay">' +
      escapeHtml(prazos.prazo_data_display || '—') + '</strong></div>';
    body += '<div class="d-flex gap-1">';
    if (prazos.pode_editar_prazo_global) {
      body += '<input type="date" class="form-control form-control-sm" id="painelPrazoOsInput"' +
        ' value="' + escapeHtml(prazos.prazo_data || '') +
        '" style="width:140px;font-size:11px;">';
      body += '<button type="button" class="btn btn-sm btn-outline-primary" id="painelPrazoOsSalvar"' +
        ' style="font-size:11px;padding:2px 8px;">Salvar</button>';
    }
    body += '<button type="button" class="btn btn-sm btn-outline-secondary" id="painelPrazoOsHist"' +
      ' style="font-size:11px;padding:2px 8px;">Histórico</button>';
    body += '</div></div>';
    body += '<div id="painelPrazoOsHistLista" class="mt-2" style="display:none;"></div>';
    body += '</div>';

    if (!(prazos.unidades || []).length) {
      body += '<p class="small text-muted mb-0">Nenhuma unidade ativa.</p>';
    }
    (prazos.unidades || []).forEach(function (u) {
      body += '<div class="border rounded p-2 mb-2" style="font-size:12px;"' +
        ' data-unidade-id="' + u.unidade_id + '">';
      body += '<div class="d-flex justify-content-between align-items-center gap-2 flex-wrap">';
      body += '<div><span class="badge bg-secondary me-1">' + escapeHtml(u.sigla) + '</span>';
      body += '<strong class="painel-prazo-unid-display">' +
        escapeHtml(u.prazo_previsto_display || '—') + '</strong></div>';
      body += '<div class="d-flex gap-1">';
      if (u.pode_editar) {
        body += '<input type="date" class="form-control form-control-sm painel-prazo-unid-input"' +
          ' value="' + escapeHtml(u.prazo_previsto || '') +
          '" style="width:140px;font-size:11px;">';
        body += '<button type="button" class="btn btn-sm btn-outline-primary painel-prazo-unid-salvar"' +
          ' style="font-size:11px;padding:2px 8px;">Salvar</button>';
      }
      body += '<button type="button" class="btn btn-sm btn-outline-secondary painel-prazo-unid-hist"' +
        ' style="font-size:11px;padding:2px 8px;">Histórico</button>';
      body += '</div></div>';
      body += '<div class="painel-prazo-unid-hist-lista mt-2" style="display:none;"></div>';
      body += '</div>';
    });
    body += '</div>';

    body += '<div class="p-3 border-bottom bg-white mt-1" id="painel-secao-producoes">';
    body += '<div class="d-flex justify-content-between align-items-center mb-2">';
    body += secaoTitulo('② Produções');
    if (data.pode_criar_producao && data.os_editavel) {
      body += '<button type="button" class="btn btn-sm btn-outline-success"' +
        ' style="font-size:11px;padding:2px 8px;" id="painelBtnNovaProd2">+ Nova</button>';
    }
    body += '</div>';
    if (!(data.producoes || []).length) {
      body += '<p class="small text-muted mb-0">Nenhuma produção.</p>';
    }
    (data.producoes || []).forEach(function (prod) {
      body += renderProducaoAccordion(prod, data, prod.pk === data.producao_pk_ativa);
    });
    body += '</div>';

    body += '<div class="p-3 bg-white mt-1" id="painel-secao-comentarios">';
    body += secaoTitulo('③ Comentários da OS');
    body += '<div id="painelComentariosOs" class="mb-2">';
    (data.comentarios_os || []).forEach(function (c) {
      body += '<div class="border-bottom py-1" style="font-size:11px;color:#495057;">' +
        '<div style="font-weight:600;color:#1a3a5c;font-size:10px;">' +
        escapeHtml(c.servidor) + ' · ' + escapeHtml(c.data_hora) + '</div>' +
        '<div>' + escapeHtml(c.texto) + '</div></div>';
    });
    if (!(data.comentarios_os || []).length) {
      body += '<em class="text-muted small">Nenhum comentário.</em>';
    }
    body += '</div>';
    body += '<textarea class="form-control form-control-sm mb-1" id="painelComentarioOsTexto"' +
      ' rows="2" placeholder="Novo comentário…" style="font-size:11px;"></textarea>';
    body += '<button type="button" class="btn btn-sm btn-primary" id="painelComentarioOsBtn"' +
      ' style="font-size:11px;">Comentar</button>';
    body += '</div>';

    return { header: header, body: body };
  }

  function bindPanelEvents(data, ctx) {
    const osPk = data.os_pk;
    const root = ctx.painelRoot || ctx.painelConteudo;
    const conteudo = ctx.painelConteudo;

    root.querySelector('#painelBtnFechar')?.addEventListener('click', ctx.fecharPainel);

    function abrirFormNovaProd() {
      const formEl = conteudo.querySelector('#painelNovaProdForm');
      if (!formEl) return;
      let fh = '<label class="form-label small mb-0">Tipo de produção</label>';
      fh += '<select class="form-select form-select-sm mb-2" id="painelTipoProd">';
      (window.gerencialTiposProducao || []).forEach(function (tp) {
        fh += '<option value="' + tp.id + '">' + escapeHtml(tp.label) + '</option>';
      });
      fh += '</select><label class="form-label small mb-0">Observação</label>';
      fh += '<textarea class="form-control form-control-sm mb-2" id="painelObsProd" rows="2"></textarea>';
      fh += '<button type="button" class="btn btn-sm btn-primary me-1" id="painelSalvarNovaProd"' +
        ' style="font-size:11px;">Registrar</button>';
      fh += '<button type="button" class="btn btn-sm btn-outline-secondary" id="painelCancelNovaProd"' +
        ' style="font-size:11px;">Cancelar</button>';
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

    root.querySelector('#painelBtnNovaProd')?.addEventListener('click', abrirFormNovaProd);
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

    const prazoOsSalvar = conteudo.querySelector('#painelPrazoOsSalvar');
    if (prazoOsSalvar) {
      prazoOsSalvar.addEventListener('click', function () {
        const input = conteudo.querySelector('#painelPrazoOsInput');
        const valor = input ? input.value : '';
        const justificativa = window.prompt(
          'Justificativa (obrigatória se já houver prazo neste ciclo):',
          '',
        );
        if (justificativa === null) return;
        postCampo('/os/' + osPk + '/editar-campo/', 'prazo_data', valor, {
          justificativa: justificativa || '',
        }).then(function (resp) {
          const display = conteudo.querySelector('#painelPrazoOsDisplay');
          if (display) display.textContent = resp.valor_display || '—';
        }).catch(function (e) { alert(e.message); });
      });
    }

    const prazoOsHist = conteudo.querySelector('#painelPrazoOsHist');
    if (prazoOsHist) {
      prazoOsHist.addEventListener('click', function () {
        const lista = conteudo.querySelector('#painelPrazoOsHistLista');
        if (!lista) return;
        if (lista.style.display !== 'none' && lista.dataset.loaded === '1') {
          lista.style.display = 'none';
          return;
        }
        lista.style.display = 'block';
        lista.innerHTML = '<em class="text-muted small">Carregando…</em>';
        getJson('/os/' + osPk + '/prazo-historico/')
          .then(function (resp) {
            lista.dataset.loaded = '1';
            lista.innerHTML = renderHistoricoHtml(resp.historico);
          })
          .catch(function (e) {
            lista.innerHTML = '<em class="text-danger small">' + escapeHtml(e.message) + '</em>';
          });
      });
    }

    conteudo.querySelectorAll('[data-unidade-id]').forEach(function (box) {
      const unidadeId = box.getAttribute('data-unidade-id');
      const btnSalvar = box.querySelector('.painel-prazo-unid-salvar');
      if (btnSalvar) {
        btnSalvar.addEventListener('click', function () {
          const input = box.querySelector('.painel-prazo-unid-input');
          const valor = input ? input.value : '';
          const justificativa = window.prompt(
            'Justificativa (obrigatória se já houver prazo neste ciclo):',
            '',
          );
          if (justificativa === null) return;
          postForm('/os/' + osPk + '/prazo-unidade/', {
            unidade_id: unidadeId,
            valor: valor,
            justificativa: justificativa || '',
          }).then(function (resp) {
            const display = box.querySelector('.painel-prazo-unid-display');
            if (display) display.textContent = resp.valor_display || '—';
          }).catch(function (e) { alert(e.message); });
        });
      }
      const btnHist = box.querySelector('.painel-prazo-unid-hist');
      if (btnHist) {
        btnHist.addEventListener('click', function () {
          const lista = box.querySelector('.painel-prazo-unid-hist-lista');
          if (!lista) return;
          if (lista.style.display !== 'none' && lista.dataset.loaded === '1') {
            lista.style.display = 'none';
            return;
          }
          lista.style.display = 'block';
          lista.innerHTML = '<em class="text-muted small">Carregando…</em>';
          getJson('/os/' + osPk + '/prazo-historico/?unidade_id=' + encodeURIComponent(unidadeId))
            .then(function (resp) {
              lista.dataset.loaded = '1';
              lista.innerHTML = renderHistoricoHtml(resp.historico);
            })
            .catch(function (e) {
              lista.innerHTML = '<em class="text-danger small">' + escapeHtml(e.message) + '</em>';
            });
        });
      }
    });

    conteudo.querySelectorAll('[data-toggle-prod]').forEach(function (hdr) {
      hdr.addEventListener('click', function () {
        const pk = hdr.dataset.toggleProd;
        const body = conteudo.querySelector('#painel-prod-' + pk + ' .card-body');
        if (!body) return;
        const vis = body.style.display !== 'none';
        body.style.display = vis ? 'none' : 'block';
        const icon = hdr.querySelector('i.bi');
        if (icon) {
          icon.className = vis ? 'bi bi-chevron-down' : 'bi bi-chevron-up';
          icon.style.fontSize = '10px';
        }
      });
    });

    conteudo.querySelectorAll('[data-cancelar-prod]').forEach(function (btn) {
      btn.addEventListener('click', function (e) {
        e.stopPropagation();
        if (!window.confirm('Cancelar esta produção?')) return;
        postJson('/api/producao/' + btn.dataset.cancelarProd + '/status/', {
          status: 'CANCELADO',
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
            if (ctx.atualizarCelula && ctx.colMap[campo]) {
              ctx.atualizarCelula(osPk, ctx.colMap[campo], escapeHtml(valor || '—'), prodPk);
            }
          })
          .catch(function (e) { alert(e.message); });
      });
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
              return '<div class="border-bottom py-1" style="font-size:11px;color:#495057;">' +
                '<div style="font-weight:600;color:#1a3a5c;font-size:10px;">' +
                escapeHtml(c.servidor) + ' · ' + escapeHtml(c.data_hora) + '</div>' +
                '<div>' + escapeHtml(c.texto) + '</div></div>';
            }).join('') || '<em class="text-muted small">Nenhum comentário.</em>';
          }
          conteudo.querySelector('#painelComentarioOsTexto').value = '';
        })
        .catch(function (e) { alert(e.message); });
    });
  }

  function scrollParaSecao(secao, data) {
    const body = document.getElementById('gerencialPainelConteudo');
    if (!body) return;
    if (secao === 'topo') {
      body.scrollTo({ top: 0, behavior: 'smooth' });
      return;
    }
    const map = {
      etapa: 'painel-secao-etapa',
      prazos: 'painel-secao-prazos',
      producoes: 'painel-secao-producoes',
      comentarios: 'painel-secao-comentarios',
      'prazo-eav': 'painel-secao-prazos',
    };
    const id = map[secao];
    const el = id ? document.getElementById(id) : null;
    if (!el || !body.contains(el)) {
      body.scrollTo({ top: 0, behavior: 'smooth' });
      return;
    }
    const top = el.getBoundingClientRect().top - body.getBoundingClientRect().top + body.scrollTop;
    body.scrollTo({ top: Math.max(0, top - 8), behavior: 'smooth' });
  }

  window.GerencialPainel = {
    renderPanel: renderPanel,
    bindPanelEvents: bindPanelEvents,
    scrollParaSecao: scrollParaSecao,
  };
})(window);
