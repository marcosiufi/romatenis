'use strict'

const API = '/api/v1'
let _token = localStorage.getItem('token')
let _players = []   // cache para lookup de nomes
let _matches = []   // cache para filtro client-side
let _seasons = []

// ── Utils ─────────────────────────────────────────────────────────────────────

function fmtDH(iso) {
  if (!iso) return '–'
  const d = new Date(iso)
  return d.toLocaleString('pt-BR', { day: '2-digit', month: '2-digit', year: '2-digit', hour: '2-digit', minute: '2-digit' })
}

function fmtD(iso) {
  if (!iso) return '–'
  const d = new Date(iso)
  return d.toLocaleDateString('pt-BR')
}

function nivelBadge(nivel) {
  const map = { A: 'ba', B: 'bb', C: 'bc', D: 'bd', nao_classificado: 'bnc' }
  const cls = map[nivel] || 'bnc'
  const txt = nivel === 'nao_classificado' ? 'NC' : (nivel || '?')
  return `<span class="badge ${cls}">${txt}</span>`
}

function statusBadge(status) {
  const map = {
    agendado: ['b-agendado', 'Agendado'],
    realizado: ['b-realizado', 'Realizado'],
    wo: ['b-wo', 'W.O.'],
    cancelado_sem_placar: ['b-cancelado', 'Cancelado'],
  }
  const [cls, lbl] = map[status] || ['bnc', status]
  return `<span class="badge ${cls}">${lbl}</span>`
}

function seasonBadge(status) {
  const map = { ativa: ['b-ativa', 'Ativa'], encerrada: ['b-encerrada', 'Encerrada'] }
  const [cls, lbl] = map[status] || ['bnc', status]
  return `<span class="badge ${cls}">${lbl}</span>`
}

function conviteBadge(status) {
  const map = {
    aguardando: ['b-pendente', 'Aguardando'],
    confirmada: ['b-confirmado', 'Confirmada'],
    falhou: ['b-falhou', 'Falhou'],
  }
  const [cls, lbl] = map[status] || ['bnc', status]
  return `<span class="badge ${cls}">${lbl}</span>`
}

let _toastTimer
function toast(msg, isErr = false) {
  const el = document.getElementById('toast')
  el.textContent = msg
  el.className = 'show' + (isErr ? ' err' : '')
  clearTimeout(_toastTimer)
  _toastTimer = setTimeout(() => { el.className = '' }, 3000)
}
function showToast(msg, type) { toast(msg, type === 'error') }

function showErr(id, msg) {
  const el = document.getElementById(id)
  if (!el) return
  el.textContent = msg
  el.style.display = msg ? '' : 'none'
}

// ── API ───────────────────────────────────────────────────────────────────────

async function api(path, opts = {}) {
  const headers = { 'Content-Type': 'application/json', ...(opts.headers || {}) }
  if (_token) headers['Authorization'] = `Bearer ${_token}`
  const res = await fetch(API + path, { ...opts, headers })
  if (res.status === 204) return null
  const data = await res.json().catch(() => ({}))
  if (!res.ok) throw new Error(data.detail || `Erro ${res.status}`)
  return data
}

// ── Auth ──────────────────────────────────────────────────────────────────────

async function init() {
  if (!_token) return showLogin()
  try {
    const me = await api('/auth/me')
    if (!me.is_admin) {
      _token = null
      localStorage.removeItem('token')
      return showLogin()
    }
    document.getElementById('admin-nome').textContent = me.nome
    document.getElementById('tela-login').style.display = 'none'
    document.getElementById('admin-app').style.display = ''
    // Set default matchmaking date to today
    const today = new Date().toISOString().slice(0, 10)
    document.getElementById('mm-data').value = today
    await loadDashboard()
  } catch {
    showLogin()
  }
}

function showLogin() {
  document.getElementById('tela-login').style.display = ''
  document.getElementById('admin-app').style.display = 'none'
}

function logout() {
  localStorage.removeItem('token')
  _token = null
  showLogin()
}

document.getElementById('form-login').addEventListener('submit', async e => {
  e.preventDefault()
  showErr('login-erro', '')
  const btn = e.submitter
  btn.disabled = true
  btn.textContent = 'Entrando…'
  try {
    const data = await api('/auth/login', {
      method: 'POST',
      body: JSON.stringify({
        email: document.getElementById('inp-email').value,
        senha: document.getElementById('inp-senha').value,
      }),
    })
    _token = data.access_token
    localStorage.setItem('token', _token)
    await init()
  } catch (err) {
    showErr('login-erro', err.message || 'Credenciais inválidas')
  } finally {
    btn.disabled = false
    btn.textContent = 'Entrar'
  }
})

// ── Tab navigation ─────────────────────────────────────────────────────────────

function switchTab(tab) {
  document.querySelectorAll('.admin-nav button').forEach(b => {
    b.classList.toggle('active', b.dataset.tab === tab)
  })
  document.querySelectorAll('.admin-section').forEach(s => s.classList.remove('active'))
  document.getElementById(`sec-${tab}`).classList.add('active')
  switch (tab) {
    case 'dashboard':    loadDashboard(); break
    case 'jogadores':    loadPlayers(); break
    case 'partidas':     loadMatches(); break
    case 'temporada':    loadSeasons(); break
    case 'assinaturas':    loadAssinaturas(); break
    case 'locacoes':       loadLocacoes(); break
    case 'matchmaking':    loadInvitations(); break
    case 'configuracoes':  loadConfiguracoes(); loadSlotsRanking(); loadHorariosEspeciais(); loadHorarios(); break
    case 'lista-espera':   loadListaEspera(); break
    case 'contrato':       loadContrato(); break
    case 'empresa':        loadEmpresa(); break
  }
}

// ── Dashboard ─────────────────────────────────────────────────────────────────

async function loadDashboard() {
  try {
    const d = await api('/admin/dashboard')
    document.getElementById('st-jogadores').textContent = d.total_jogadores
    document.getElementById('st-subs').textContent = d.assinaturas_ativas
    document.getElementById('st-sem-placar').textContent = d.partidas_sem_placar
    document.getElementById('st-hoje').textContent = d.reservas_hoje

    const extra = document.getElementById('dash-extra')
    const tempInfo = d.temporada_ativa
      ? `Temporada ativa: ${fmtD(d.temporada_ativa.data_inicio)} → ${fmtD(d.temporada_ativa.data_fim)}`
      : 'Nenhuma temporada ativa'
    const liderInfo = d.lider_ranking
      ? `${escHtml(d.lider_ranking.nome)} (${d.lider_ranking.pontos} pts)`
      : 'Sem pontuações ainda'
    const pausaCard = d.pausas_pendentes > 0
      ? `<div class="dash-card" style="border-left:3px solid #e0a040;cursor:pointer" onclick="switchTab('assinaturas');filtrarPausasPendentes()">
           <div class="dc-label">⏸ Solicitações de Pausa</div>
           <div class="dc-val" style="color:#e0a040">${d.pausas_pendentes} aguardando aprovação →</div>
         </div>`
      : ''
    // Pagou mas a Autentique nunca enviou o contrato: fica bloqueado em silêncio
    const contratoCard = d.contratos_nao_enviados > 0
      ? `<div class="dash-card" style="border-left:3px solid #c0392b;cursor:pointer" onclick="switchTab('jogadores')">
           <div class="dc-label">🚨 Contrato não enviado</div>
           <div class="dc-val" style="color:#e06060">${d.contratos_nao_enviados} jogador(es) pagos e bloqueados →</div>
         </div>`
      : ''
    extra.innerHTML = `
      ${contratoCard}
      ${pausaCard}
      <div class="dash-card">
        <div class="dc-label">Temporada</div>
        <div class="dc-val">${tempInfo}</div>
      </div>
      <div class="dash-card">
        <div class="dc-label">Líder do Ranking</div>
        <div class="dc-val">${liderInfo}</div>
      </div>
    `
  } catch (err) {
    toast('Erro ao carregar dashboard: ' + err.message, true)
  }
}

// ── Jogadores ─────────────────────────────────────────────────────────────────

async function loadPlayers() {
  try {
    _players = await api('/admin/players')
    renderJogadores(_players)
  } catch (err) {
    toast('Erro ao carregar jogadores: ' + err.message, true)
  }
}

function filtrarJogadores() {
  const q = document.getElementById('busca-jogador').value.toLowerCase()
  const lista = q ? _players.filter(p =>
    p.nome.toLowerCase().includes(q) ||
    p.email.toLowerCase().includes(q) ||
    (p.apelido || '').toLowerCase().includes(q) ||
    (p.cpf || '').includes(q)
  ) : _players
  renderJogadores(lista)
}

function _nomeExibicao(p) {
  return p.apelido ? `${escHtml(p.apelido)} <span style="opacity:.55;font-size:.75em">(${escHtml(p.nome)})</span>` : escHtml(p.nome)
}

function _statusBadge(status) {
  const map = {
    ativo:      '<span class="badge ba" style="background:#2a6e3a">ATIVO</span>',
    assinatura: '<span class="badge ba" style="background:#7a5c00">ASSINATURA</span>',
    pagamento:  '<span class="badge ba" style="background:#1a3d6e">PAGAMENTO</span>',
    renovacao:  '<span class="badge ba" style="background:#7a3c00">RENOVAÇÃO</span>',
    inativo:    '<span class="badge ba" style="background:#555">INATIVO</span>',
  }
  return map[status] || `<span class="badge ba" style="background:#555">${status || 'N/D'}</span>`
}

function _contratoBadge(p) {
  if (p.contrato_assinado) return '<span class="badge ba" style="background:#2a6e3a">✓ assinado</span>'
  if (p.contrato_enviado_em) return '<span class="badge ba" style="background:#7a6a10">aguardando</span>'
  return '<span class="badge ba" style="background:#555">não enviado</span>'
}

function renderJogadores(lista) {
  const tb = document.getElementById('tbody-jogadores')
  if (!lista.length) {
    tb.innerHTML = '<tr><td colspan="9" class="empty">Nenhum jogador encontrado</td></tr>'
    return
  }
  tb.innerHTML = lista.map(p => `
    <tr>
      <td>${_nomeExibicao(p)}${p.is_admin ? ' <span class="badge ba">admin</span>' : ''}</td>
      <td style="color:var(--clr-text-muted)">${escHtml(p.email)}</td>
      <td>${nivelBadge(p.nivel)}</td>
      <td>${p.rating_atual.toFixed(0)}</td>
      <td>${p.pontos_ranking_temporada_atual}</td>
      <td>${p.aceita_convites_sistema ? '✓' : '–'}</td>
      <td>${_statusBadge(p.status)}</td>
      <td>${_contratoBadge(p)}</td>
      <td style="white-space:nowrap">
        <button class="btn-xs sec" onclick="abrirModalJogador(${p.id})">Editar</button>
        <button class="btn-xs sec" onclick="enviarContrato(${p.id})" title="${p.contrato_enviado_em ? 'Reenviar' : 'Enviar'} contrato">
          ${p.contrato_enviado_em ? '↺' : '📄'}
        </button>
        ${!p.contrato_assinado ? `<button class="btn-xs sec" onclick="marcarContratoAssinado(${p.id})" title="Marcar como assinado manualmente">✓</button>` : ''}
      </td>
    </tr>
  `).join('')
}

async function enviarContrato(playerId) {
  if (!confirm('Enviar Termo de Adesão via Autentique para este jogador?')) return
  try {
    await api(`/admin/players/${playerId}/enviar-contrato`, { method: 'POST' })
    toast('Contrato enviado')
    loadPlayers()
  } catch (err) {
    toast('Erro ao enviar contrato: ' + err.message, true)
  }
}

async function marcarContratoAssinado(playerId) {
  if (!confirm('Marcar o contrato como assinado manualmente?')) return
  try {
    await api(`/admin/players/${playerId}/marcar-contrato-assinado`, { method: 'POST' })
    toast('Contrato marcado como assinado')
    loadPlayers()
  } catch (err) {
    toast('Erro: ' + err.message, true)
  }
}

function _setVal(id, val) { document.getElementById(id).value = val || '' }

function abrirModalJogador(playerId = null) {
  document.getElementById('modal-jogador-titulo').textContent = playerId ? 'Editar Jogador' : 'Criar Jogador'
  document.getElementById('jog-id').value = playerId || ''
  // Limpa todos os campos
  ['jog-nome','jog-apelido','jog-email','jog-telefone','jog-senha',
   'jog-cpf','jog-nascimento','jog-rua','jog-numero','jog-complemento',
   'jog-bairro','jog-cidade','jog-cep'].forEach(id => _setVal(id, ''))
  document.getElementById('jog-estado').value = ''
  document.getElementById('jog-pais').value = 'Brasil'
  document.getElementById('jog-convites').checked = true
  document.getElementById('jog-is-admin').checked = false
  document.getElementById('jog-status').value = 'ativo'
  document.getElementById('row-nivel').style.display = playerId ? '' : 'none'
  document.getElementById('row-is-admin').style.display = playerId ? '' : 'none'
  document.getElementById('row-status').style.display = playerId ? '' : 'none'
  document.getElementById('row-senha').style.display = playerId ? 'none' : ''
  showErr('jog-erro', '')

  if (playerId) {
    const p = _players.find(x => x.id === playerId)
    if (p) {
      _setVal('jog-nome', p.nome)
      _setVal('jog-apelido', p.apelido)
      _setVal('jog-email', p.email)
      _setVal('jog-telefone', p.telefone)
      _setVal('jog-cpf', p.cpf)
      _setVal('jog-nascimento', p.data_nascimento)
      _setVal('jog-rua', p.rua)
      _setVal('jog-numero', p.numero)
      _setVal('jog-complemento', p.complemento)
      _setVal('jog-bairro', p.bairro)
      _setVal('jog-cidade', p.cidade)
      _setVal('jog-cep', p.cep)
      document.getElementById('jog-estado').value = p.estado || ''
      document.getElementById('jog-pais').value = p.pais || 'Brasil'
      document.getElementById('jog-convites').checked = p.aceita_convites_sistema
      document.getElementById('jog-is-admin').checked = p.is_admin
      document.getElementById('jog-nivel').value = p.nivel
      document.getElementById('jog-status').value = p.status || 'ativo'
    }
  }
  document.getElementById('modal-jogador').classList.add('open')
}

function fecharModalJogador() {
  document.getElementById('modal-jogador').classList.remove('open')
}

function _coletarDadosJogador() {
  return {
    nome:        document.getElementById('jog-nome').value,
    apelido:     document.getElementById('jog-apelido').value || null,
    email:       document.getElementById('jog-email').value,
    telefone:    document.getElementById('jog-telefone').value,
    cpf:         document.getElementById('jog-cpf').value || null,
    data_nascimento: document.getElementById('jog-nascimento').value || null,
    rua:         document.getElementById('jog-rua').value || null,
    numero:      document.getElementById('jog-numero').value || null,
    complemento: document.getElementById('jog-complemento').value || null,
    bairro:      document.getElementById('jog-bairro').value || null,
    cidade:      document.getElementById('jog-cidade').value || null,
    estado:      document.getElementById('jog-estado').value || null,
    pais:        document.getElementById('jog-pais').value || 'Brasil',
    cep:         document.getElementById('jog-cep').value || null,
    aceita_convites_sistema: document.getElementById('jog-convites').checked,
  }
}

async function salvarJogador(e) {
  e.preventDefault()
  showErr('jog-erro', '')
  const id = document.getElementById('jog-id').value
  const btn = e.submitter
  btn.disabled = true

  try {
    if (id) {
      const body = {
        ..._coletarDadosJogador(),
        nivel:    document.getElementById('jog-nivel').value,
        is_admin: document.getElementById('jog-is-admin').checked,
      }
      body.status = document.getElementById('jog-status').value
      await api(`/admin/players/${id}`, { method: 'PATCH', body: JSON.stringify(body) })
      toast('Jogador atualizado')
    } else {
      const senha = document.getElementById('jog-senha').value
      if (!senha) { showErr('jog-erro', 'Senha obrigatória ao criar jogador'); return }
      await api('/players', { method: 'POST', body: JSON.stringify({ ..._coletarDadosJogador(), senha }) })
      toast('Jogador criado')
    }
    fecharModalJogador()
    loadPlayers()
  } catch (err) {
    showErr('jog-erro', err.message)
  } finally {
    btn.disabled = false
  }
}

// ── Partidas ──────────────────────────────────────────────────────────────────

async function loadMatches() {
  try {
    // Garante que o cache de jogadores está populado para exibir nomes
    if (!_players.length) await loadPlayers()
    _matches = await api('/matches')
    filtrarPartidas()
  } catch (err) {
    toast('Erro ao carregar partidas: ' + err.message, true)
  }
}

function filtrarPartidas() {
  const filtro = document.getElementById('filtro-status').value
  const lista = filtro ? _matches.filter(m => m.status === filtro) : _matches
  renderPartidas(lista)
}

function playerNome(playerId) {
  const p = _players.find(x => x.id === playerId)
  return p ? p.nome.split(' ')[0] : `#${playerId}`
}

function nomesSide(parts, lado) {
  return parts
    .filter(p => p.lado === lado)
    .map(p => playerNome(p.player_id))
    .join(' / ') || '–'
}

function placarStr(match) {
  if (!match.placar) return '–'
  const { games_A, games_B, tiebreak_A, tiebreak_B } = match.placar
  const tb = tiebreak_A != null ? ` (TB ${tiebreak_A}-${tiebreak_B})` : ''
  return `${games_A}-${games_B}${tb}`
}

function renderPartidas(lista) {
  const tb = document.getElementById('tbody-partidas')
  if (!lista.length) {
    tb.innerHTML = '<tr><td colspan="8" class="empty">Nenhuma partida</td></tr>'
    return
  }
  tb.innerHTML = lista.map(m => {
    const parts = m.participantes || []
    const podeAcao = m.status === 'agendado'
    const acoes = podeAcao
      ? `<button class="btn-xs primary" onclick="abrirModalPlacar(${m.id})">Placar</button>
         <button class="btn-xs warn"    onclick="abrirModalWO(${m.id})">W.O.</button>
         <button class="btn-xs danger"  onclick="cancelarPartida(${m.id})">Cancelar</button>`
      : '–'
    return `
      <tr>
        <td>${m.id}</td>
        <td style="white-space:nowrap">${fmtDH(m.data_hora)}</td>
        <td>${m.tipo === 'simples' ? 'S' : 'D'}</td>
        <td>${escHtml(nomesSide(parts, 'A'))}</td>
        <td>${escHtml(nomesSide(parts, 'B'))}</td>
        <td>${statusBadge(m.status)}</td>
        <td>${escHtml(placarStr(m))}</td>
        <td style="white-space:nowrap">${acoes}</td>
      </tr>
    `
  }).join('')
}

// Modal Placar
function abrirModalPlacar(matchId) {
  const m = _matches.find(x => x.id === matchId)
  document.getElementById('placar-match-id').value = matchId
  document.getElementById('placar-info').textContent = m
    ? `Partida #${m.id} · ${fmtDH(m.data_hora)}`
    : `Partida #${matchId}`
  const parts = m?.participantes || []
  document.getElementById('lbl-a').textContent = `Games – ${nomesSide(parts, 'A')}`
  document.getElementById('lbl-b').textContent = `Games – ${nomesSide(parts, 'B')}`
  document.getElementById('adm-ga').value = ''
  document.getElementById('adm-gb').value = ''
  document.getElementById('adm-ta').value = ''
  document.getElementById('adm-tb').value = ''
  document.getElementById('row-tb').style.display = 'none'
  showErr('placar-erro', '')
  document.getElementById('modal-placar').classList.add('open')
}

function fecharModalPlacar() {
  document.getElementById('modal-placar').classList.remove('open')
}

// Show tiebreak when both games are 8
;['adm-ga', 'adm-gb'].forEach(id => {
  document.getElementById(id)?.addEventListener('input', () => {
    const ga = +document.getElementById('adm-ga').value
    const gb = +document.getElementById('adm-gb').value
    document.getElementById('row-tb').style.display = (ga === 8 && gb === 8) ? '' : 'none'
  })
})

async function submitPlacar(e) {
  e.preventDefault()
  showErr('placar-erro', '')
  const btn = e.submitter
  btn.disabled = true
  const matchId = document.getElementById('placar-match-id').value
  const ga = parseInt(document.getElementById('adm-ga').value)
  const gb = parseInt(document.getElementById('adm-gb').value)
  const ta = document.getElementById('adm-ta').value !== '' ? parseInt(document.getElementById('adm-ta').value) : null
  const tb = document.getElementById('adm-tb').value !== '' ? parseInt(document.getElementById('adm-tb').value) : null

  try {
    await api(`/matches/${matchId}/placar`, {
      method: 'POST',
      body: JSON.stringify({ games_a: ga, games_b: gb, tiebreak_a: ta, tiebreak_b: tb }),
    })
    toast('Placar lançado com sucesso')
    fecharModalPlacar()
    await loadMatches()
  } catch (err) {
    showErr('placar-erro', err.message)
  } finally {
    btn.disabled = false
  }
}

// Modal W.O.
function abrirModalWO(matchId) {
  const m = _matches.find(x => x.id === matchId)
  document.getElementById('wo-match-id').value = matchId
  const parts = m?.participantes || []
  document.getElementById('wo-info').textContent = m
    ? `Partida #${m.id} · ${fmtDH(m.data_hora)} · Lado A: ${nomesSide(parts, 'A')} · Lado B: ${nomesSide(parts, 'B')}`
    : `Partida #${matchId}`
  document.getElementById('modal-wo').classList.add('open')
}

function fecharModalWO() {
  document.getElementById('modal-wo').classList.remove('open')
}

async function confirmarWO(lado) {
  const matchId = document.getElementById('wo-match-id').value
  try {
    await api(`/matches/${matchId}/wo`, {
      method: 'POST',
      body: JSON.stringify({ lado_wo: lado }),
    })
    toast('W.O. registrado')
    fecharModalWO()
    await loadMatches()
  } catch (err) {
    toast(err.message, true)
  }
}

async function cancelarPartida(matchId) {
  if (!confirm(`Cancelar partida #${matchId}?`)) return
  try {
    await api(`/matches/${matchId}/cancelar`, { method: 'POST' })
    toast('Partida cancelada')
    await loadMatches()
  } catch (err) {
    toast(err.message, true)
  }
}

async function recalcularClassificacao() {
  if (!confirm('Recalcular classificação A/B/C/D de todos os jogadores?')) return
  try {
    const r = await api('/matches/recalcular-classificacao', { method: 'POST' })
    toast(`Classificação recalculada (${r.elegíveis ?? r.elegiveis ?? '?'} jogadores)`)
    loadPlayers()
  } catch (err) {
    toast(err.message, true)
  }
}

// ── Temporadas ────────────────────────────────────────────────────────────────

async function loadSeasons() {
  try {
    _seasons = await api('/seasons')
    renderSeasons(_seasons)
  } catch (err) {
    toast('Erro ao carregar temporadas: ' + err.message, true)
  }
}

function renderSeasons(lista) {
  const container = document.getElementById('seasons-lista')
  if (!lista.length) {
    container.innerHTML = '<div class="empty">Nenhuma temporada cadastrada</div>'
    return
  }
  container.innerHTML = lista.map(s => {
    const isAtiva = s.status === 'ativa'
    const top3 = (s.ranking_final || []).slice(0, 3)
    const rankHtml = top3.length
      ? `<div class="ranking-top">
           <span>Top 3 finais:</span>
           <ol>${top3.map(r => `<li>${escHtml(r.nome)} – ${r.pontos} pts</li>`).join('')}</ol>
         </div>`
      : ''
    const acoes = isAtiva
      ? `<button class="btn-xs danger" onclick="encerrarTemporada(${s.id})">Encerrar</button>`
      : ''
    return `
      <div class="season-card ${s.status}">
        <div class="s-header">
          <div>
            <div class="s-title">Temporada #${s.id} ${seasonBadge(s.status)}</div>
            <div class="s-dates">${fmtD(s.data_inicio)} → ${fmtD(s.data_fim)}</div>
          </div>
          <div>${acoes}</div>
        </div>
        ${rankHtml}
      </div>
    `
  }).join('')
}

async function encerrarTemporada(seasonId) {
  if (!confirm('Encerrar temporada? Esta ação irá salvar o ranking final e zerar os pontos de todos os jogadores.')) return
  try {
    await api(`/seasons/${seasonId}/encerrar`, { method: 'POST' })
    toast('Temporada encerrada e ranking salvo')
    await loadSeasons()
  } catch (err) {
    toast(err.message, true)
  }
}

function abrirModalTemporada() {
  document.getElementById('temp-inicio').value = ''
  document.getElementById('temp-fim').value = ''
  showErr('temp-erro', '')
  document.getElementById('modal-temporada').classList.add('open')
}

function fecharModalTemporada() {
  document.getElementById('modal-temporada').classList.remove('open')
}

async function criarTemporada(e) {
  e.preventDefault()
  showErr('temp-erro', '')
  const btn = e.submitter
  btn.disabled = true
  try {
    const body = {
      data_inicio: document.getElementById('temp-inicio').value + 'T00:00:00',
      data_fim: document.getElementById('temp-fim').value + 'T23:59:59',
    }
    await api('/seasons', { method: 'POST', body: JSON.stringify(body) })
    toast('Temporada criada')
    fecharModalTemporada()
    await loadSeasons()
  } catch (err) {
    showErr('temp-erro', err.message)
  } finally {
    btn.disabled = false
  }
}

// ── Matchmaking ───────────────────────────────────────────────────────────────

async function executarMatchmaking() {
  const data = document.getElementById('mm-data').value
  const tipo = document.getElementById('mm-tipo').value
  if (!data) { toast('Selecione uma data', true); return }
  try {
    const r = await api(`/matchmaking/executar?data=${data}&tipo=${tipo}`, { method: 'POST' })
    const el = document.getElementById('mm-resultado')
    el.innerHTML = `
      <div class="mm-row"><span>Slots livres</span><strong class="mm-val">${r.slots_livres}</strong></div>
      <div class="mm-row"><span>Convites enviados</span><strong class="mm-val">${r.convites_enviados}</strong></div>
      <div class="mm-row"><span>Slots sem jogadores</span><strong class="mm-val">${r.slots_sem_jogadores}</strong></div>
    `
    el.classList.add('show')
    toast(`Matchmaking concluído: ${r.convites_enviados} convite(s) enviado(s)`)
    await loadInvitations()
  } catch (err) {
    toast(err.message, true)
  }
}

async function loadInvitations() {
  try {
    if (!_players.length) await loadPlayers()
    const data = await api('/matchmaking/convites')
    renderInvitations(data)
  } catch (err) {
    toast('Erro ao carregar convites: ' + err.message, true)
  }
}

function renderInvitations(lista) {
  const tb = document.getElementById('tbody-convites')
  if (!lista.length) {
    tb.innerHTML = '<tr><td colspan="5" class="empty">Nenhum convite encontrado</td></tr>'
    return
  }
  tb.innerHTML = lista.map(inv => {
    const jogadores = (inv.jogadores || [])
      .map(jp => {
        const statusMap = { pendente: '⏳', confirmado: '✓', recusado: '✗', expirado: '–', cancelado: '–' }
        return `${playerNome(jp.player_id)} ${statusMap[jp.status] || ''}`
      })
      .join(', ')
    return `
      <tr>
        <td style="white-space:nowrap">${fmtDH(inv.slot_data_hora)}</td>
        <td>${inv.tipo === 'simples' ? 'Simples' : 'Duplas'}</td>
        <td>${conviteBadge(inv.status)}</td>
        <td style="font-size:0.78rem">${escHtml(jogadores)}</td>
        <td style="white-space:nowrap;color:var(--clr-text-muted)">${fmtDH(inv.expira_em)}</td>
      </tr>
    `
  }).join('')
}

// ── Assinaturas ───────────────────────────────────────────────────────────────

let _subs = []
let _precos = { mensal: 89.90, trimestral: 239.90, semestral: 449.90, anual: 839.90 }

const SUB_STATUS_MAP = {
  ativa:        ['b-ativa',     'Ativa'],
  pausada:      ['b-pendente',  'Pausada'],
  expirada:     ['b-expirado',  'Expirada'],
  inadimplente: ['b-falhou',    'Inadimplente'],
  cancelada:    ['b-cancelado', 'Cancelada'],
}
const PLANO_LABEL = { mensal: 'Mensal', trimestral: 'Trimestral', semestral: 'Semestral', anual: 'Anual' }

function subBadge(status) {
  const [cls, lbl] = SUB_STATUS_MAP[status] || ['bnc', status]
  return `<span class="badge ${cls}">${lbl}</span>`
}

function diasRestantes(iso) {
  const diff = Math.ceil((new Date(iso) - Date.now()) / 86400000)
  if (diff < 0)  return `<span style="color:#e74c3c">${Math.abs(diff)}d atrás</span>`
  if (diff <= 7) return `<span style="color:#e67e22">${diff}d</span>`
  return `<span style="color:#27ae60">${diff}d</span>`
}

async function loadAssinaturas() {
  try {
    _precos = await api('/subscriptions/precos').catch(() => _precos)
    _subs   = await api('/subscriptions')
    renderAssinaturas(_subs)
    atualizarStatsSubs(_subs)
  } catch (err) {
    toast('Erro ao carregar assinaturas: ' + err.message, true)
  }
}

function atualizarStatsSubs(list) {
  const hoje = Date.now()
  const em7d = new Date(hoje + 7 * 86400000)
  const pendentes = list.filter(s => s.pausa_solicitada).length
  document.getElementById('sub-st-ativas').textContent    = list.filter(s => s.status === 'ativa').length
  document.getElementById('sub-st-pausadas').textContent  = list.filter(s => s.status === 'pausada').length
  document.getElementById('sub-st-expiradas').textContent = list.filter(s => s.status === 'expirada').length
  document.getElementById('sub-st-7d').textContent        = list.filter(s =>
    s.status === 'ativa' && new Date(s.data_expiracao) <= em7d && new Date(s.data_expiracao) > hoje
  ).length
  document.getElementById('sub-st-pausas-pendentes').textContent = pendentes
  document.getElementById('sub-st-pausas-card').style.opacity = pendentes > 0 ? '1' : '0.4'
}

function filtrarPausasPendentes() {
  document.getElementById('filtro-sub-status').value = ''
  document.getElementById('filtro-sub-nome').value = ''
  const filtrados = _subs.filter(s => s.pausa_solicitada)
  renderAssinaturas(filtrados)
}

function filtrarAssinaturas() {
  const statusFiltro = document.getElementById('filtro-sub-status').value
  const nomeFiltro   = document.getElementById('filtro-sub-nome').value.toLowerCase()
  const filtrados = _subs.filter(s =>
    (!statusFiltro || s.status === statusFiltro) &&
    (!nomeFiltro   || (s.player_nome || '').toLowerCase().includes(nomeFiltro))
  )
  renderAssinaturas(filtrados)
}

function renderAssinaturas(list) {
  const tbody = document.getElementById('tbody-assinaturas')
  if (!list.length) {
    tbody.innerHTML = '<tr><td colspan="7" class="empty">Nenhuma assinatura encontrada</td></tr>'
    return
  }
  tbody.innerHTML = list.map(s => `
    <tr${s.pausa_solicitada ? ' style="background:rgba(224,160,64,.07)"' : ''}>
      <td>
        <strong>${escHtml(s.player_nome || '–')}</strong>
        <div style="font-size:0.72rem;color:var(--clr-text-muted)">${escHtml(s.player_email || '')}</div>
      </td>
      <td>${PLANO_LABEL[s.plano] || s.plano}</td>
      <td>
        ${subBadge(s.status)}
        ${s.pausa_solicitada ? '<span class="badge b-pendente" style="margin-left:3px">⏸ Pausa</span>' : ''}
        ${s.status === 'pausada' && s.data_retorno_prevista
          ? `<div style="font-size:0.68rem;color:var(--clr-text-muted);margin-top:2px">retorno: ${fmtD(s.data_retorno_prevista)}</div>` : ''}
      </td>
      <td>${fmtD(s.data_inicio_ciclo)}</td>
      <td>${fmtD(s.data_expiracao)}<br>${diasRestantes(s.data_expiracao)}</td>
      <td>R$ ${Number(s.valor_total_ciclo).toFixed(2)}</td>
      <td>
        <button class="btn-xs sec" onclick="abrirModalSubStatus(${s.id})">Status</button>
        ${s.gateway_subscription_id
          ? `<button class="btn-xs primary" onclick="verPixSub(${s.id}, '${s.gateway_subscription_id}')">PIX</button>`
          : ''}
      </td>
    </tr>`).join('')
}

// ── Modal Nova Assinatura ─────────────────────────────────────────────────────

async function abrirModalNovaAssinatura() {
  // popula select de jogadores
  const sel = document.getElementById('sub-player-id')
  if (!_players.length) await loadPlayers()
  sel.innerHTML = _players.map(p =>
    `<option value="${p.id}">${escHtml(p.nome)}</option>`).join('')

  document.getElementById('sub-pix-result').style.display = 'none'
  document.getElementById('sub-btn-salvar').style.display = ''
  showErr('sub-err', '')
  atualizarPrecoSub()
  document.getElementById('modal-assinatura').classList.add('open')
}

function fecharModalAssinatura() {
  document.getElementById('modal-assinatura').classList.remove('open')
  document.getElementById('form-assinatura').reset()
  document.getElementById('sub-pix-result').style.display = 'none'
}

function atualizarPrecoSub() {
  const plano = document.getElementById('sub-plano').value
  const formaEl = document.getElementById('sub-forma')
  const p = _precos[plano]
  if (!p || typeof p !== 'object') return

  const isPix = formaEl.value === 'pix_avista'
  document.getElementById('sub-valor-mensal').value = p.valor_mensal ?? ''
  const totalBruto = p.valor_total ?? (p.valor_mensal * (p.parcelas ?? 1))
  let info
  if (isPix) {
    const totalPix = Math.round(totalBruto * 0.95 * 100) / 100
    info = `R$ ${fmtR$(totalPix)} à vista com PIX (5% de desconto)`
  } else {
    const parcelas = p.parcelas ?? 1
    info = parcelas > 1
      ? `${parcelas}× R$ ${fmtR$(p.valor_mensal)} = R$ ${fmtR$(totalBruto)} total`
      : `R$ ${fmtR$(totalBruto)} à vista`
  }
  document.getElementById('sub-preco-info').textContent = info
}

function fmtR$(v) {
  return Number(v).toLocaleString('pt-BR', { minimumFractionDigits: 2, maximumFractionDigits: 2 })
}

async function salvarAssinatura(e) {
  e.preventDefault()
  showErr('sub-err', '')
  const btn = document.getElementById('sub-btn-salvar')
  btn.disabled = true; btn.textContent = 'Gerando…'
  try {
    const plano = document.getElementById('sub-plano').value
    const forma = document.getElementById('sub-forma').value
    const isPix = forma === 'pix_avista'
    const p = _precos[plano]
    const parcelas = (!isPix && p?.parcelas) ? p.parcelas : 1
    const body = {
      player_id:       parseInt(document.getElementById('sub-player-id').value),
      plano,
      forma_pagamento: forma,
      valor_mensal:    parseFloat(document.getElementById('sub-valor-mensal').value),
      parcelas,
    }
    const res = await api('/subscriptions', { method: 'POST', body: JSON.stringify(body) })
    toast('✅ Assinatura criada!')
    btn.style.display = 'none'
    if (res.pix_copia_e_cola) {
      document.getElementById('sub-pix-code').value = res.pix_copia_e_cola
      document.getElementById('sub-pix-result').style.display = ''
    } else if (res.payment_link) {
      document.getElementById('sub-pix-code').value = res.payment_link
      document.getElementById('sub-pix-result').style.display = ''
    }
    await loadAssinaturas()
  } catch (err) {
    showErr('sub-err', err.message)
  } finally {
    btn.disabled = false; btn.textContent = 'Criar e Gerar PIX'
  }
}

// ── Modal Status ──────────────────────────────────────────────────────────────

function abrirModalSubStatus(id) {
  const s = _subs.find(x => x.id === id)
  if (!s) return
  document.getElementById('sub-status-id').value = id
  document.getElementById('sub-novo-status').value = s.status
  document.getElementById('sub-notas').value = ''
  showErr('sub-status-err', '')

  const infoEl = document.getElementById('pausa-request-info')
  const motivoEl = document.getElementById('pausa-request-motivo')
  if (s.pausa_solicitada && s.pausa_motivo) {
    const dataInicio = s.data_pausa ? s.data_pausa.split('T')[0] : ''
    const dataRetorno = s.data_retorno_prevista ? s.data_retorno_prevista.split('T')[0] : ''
    const dias = dataInicio && dataRetorno
      ? Math.ceil((new Date(dataRetorno) - new Date(dataInicio)) / 86400000)
      : ''
    motivoEl.textContent = `Motivo: "${s.pausa_motivo}"${dias ? ` · ${dataInicio} → ${dataRetorno} (${dias} dias)` : ''}`
    infoEl.style.display = ''
    document.getElementById('sub-novo-status').value = 'pausada'
    document.getElementById('sub-data-pausa').value = dataInicio
    document.getElementById('sub-data-retorno').value = dataRetorno
  } else {
    infoEl.style.display = 'none'
    document.getElementById('sub-data-pausa').value = ''
    document.getElementById('sub-data-retorno').value = ''
  }

  togglePausaFields()
  document.getElementById('modal-sub-status').classList.add('open')
}

function fecharModalSubStatus() {
  document.getElementById('modal-sub-status').classList.remove('open')
}

function togglePausaFields() {
  const isPausa = document.getElementById('sub-novo-status').value === 'pausada'
  document.getElementById('pausa-fields').style.display = isPausa ? '' : 'none'
}

async function confirmarSubStatus() {
  showErr('sub-status-err', '')
  const id     = document.getElementById('sub-status-id').value
  const status = document.getElementById('sub-novo-status').value
  const pausa  = document.getElementById('sub-data-pausa').value
  const retorno= document.getElementById('sub-data-retorno').value
  const notas  = document.getElementById('sub-notas').value

  if (status === 'pausada' && pausa && retorno) {
    const dias = Math.ceil((new Date(retorno) - new Date(pausa)) / 86400000)
    if (dias > 15) {
      showErr('sub-status-err', 'A pausa máxima é de 15 dias.')
      return
    }
  }

  try {
    await api(`/subscriptions/${id}/status`, {
      method: 'PATCH',
      body: JSON.stringify({
        status,
        data_pausa: pausa || null,
        data_retorno_prevista: retorno || null,
        notas: notas || null,
      }),
    })
    toast('✅ Status atualizado')
    fecharModalSubStatus()
    await loadAssinaturas()
  } catch (err) {
    showErr('sub-status-err', err.message)
  }
}

// ── Ver PIX ───────────────────────────────────────────────────────────────────

async function verPixSub(subId, gatewayId) {
  const body = document.getElementById('ver-pix-body')
  body.innerHTML = '<p style="color:var(--clr-text-muted);font-size:0.85rem">Buscando…</p>'
  document.getElementById('modal-ver-pix').classList.add('open')
  try {
    const res = await api('/subscriptions/pix-pendente')
    if (res && res.pix_copia_e_cola) {
      body.innerHTML = `
        <p style="font-size:0.82rem;color:var(--clr-text-muted);margin-bottom:0.5rem">Copia-e-cola PIX:</p>
        <div style="display:flex;gap:0.4rem;align-items:flex-start">
          <textarea id="ver-pix-code" readonly style="flex:1;background:var(--clr-surface);border:1px solid var(--clr-border);border-radius:0.35rem;color:var(--clr-text);font-size:0.72rem;padding:0.4rem;resize:none;height:60px;font-family:monospace">${escHtml(res.pix_copia_e_cola)}</textarea>
          <button class="btn-xs primary" onclick="copiarPix('ver-pix-code')">Copiar</button>
        </div>
        ${res.payment_link ? `<p style="margin-top:0.5rem;font-size:0.8rem"><a href="${escHtml(res.payment_link)}" target="_blank" style="color:var(--clr-accent)">Abrir link de cobrança ↗</a></p>` : ''}
      `
    } else {
      body.innerHTML = '<p style="color:var(--clr-text-muted);font-size:0.85rem">Nenhum PIX pendente encontrado para este jogador.</p>'
    }
  } catch (err) {
    body.innerHTML = `<p style="color:#e74c3c;font-size:0.85rem">${escHtml(err.message)}</p>`
  }
}

function copiarPix(inputId) {
  const el = document.getElementById(inputId)
  if (!el) return
  navigator.clipboard.writeText(el.value).then(() => toast('✅ PIX copiado!'))
}

// ── Security util ─────────────────────────────────────────────────────────────

function escHtml(str) {
  if (!str) return ''
  return String(str)
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;')
    .replace(/'/g, '&#39;')
}

// ── Configurações ─────────────────────────────────────────────────────────────

const _PLANO_MESES = { mensal: 1, trimestral: 3, semestral: 6, anual: 12 }
const _PLANO_LABEL2 = { mensal: 'Mensal', trimestral: 'Trimestral', semestral: 'Semestral', anual: 'Anual' }

async function loadConfiguracoes() {
  try {
    const cfg = await api('/admin/configuracoes')
    document.getElementById('cfg-mensal').value      = cfg.preco_mensal
    document.getElementById('cfg-trimestral').value  = cfg.preco_trimestral
    document.getElementById('cfg-semestral').value   = cfg.preco_semestral
    document.getElementById('cfg-anual').value       = cfg.preco_anual
    document.getElementById('cfg-locacao').value = cfg.preco_locacao_hora
    document.getElementById('cfg-jogo-avulso').value = cfg.preco_jogo_avulso

    document.getElementById('cfg-planos-ativa').checked   = cfg.contratacao_planos_ativa
    document.getElementById('cfg-reservas-ativa').checked = cfg.reservas_ativas
    document.getElementById('cfg-msg-planos').value       = cfg.msg_planos_desabilitado
    document.getElementById('cfg-msg-reservas').value     = cfg.msg_reservas_desabilitado

    document.getElementById('cfg-ant-ranking-min').value    = cfg.ranking_antecedencia_minima_horas
    document.getElementById('cfg-ant-ranking-ultima').value = cfg.ranking_ultima_hora_horas
    document.getElementById('cfg-ant-jogo-avulso').value    = cfg.jogo_avulso_ultima_hora_horas
    document.getElementById('cfg-ant-locacao').value        = cfg.locacao_libera_slot_ranking_horas

    // Mantém a explicação da seção de slots do ranking coerente com a config
    const srHoras = document.getElementById('sr-horas-libera')
    if (srHoras) srHoras.textContent = cfg.locacao_libera_slot_ranking_horas

    _atualizarInfoPrecos(cfg)
    _renderTabelaParcelas(cfg)
  } catch (err) {
    toast('Erro ao carregar configurações: ' + err.message, true)
  }
}

function _atualizarInfoPrecos(cfg) {
  const planos = {
    mensal: { total: cfg.preco_mensal, meses: 1 },
    trimestral: { total: cfg.preco_trimestral, meses: 3 },
    semestral: { total: cfg.preco_semestral, meses: 6 },
    anual: { total: cfg.preco_anual, meses: 12 },
  }
  for (const [key, { total, meses }] of Object.entries(planos)) {
    const el = document.getElementById(`cfg-${key}-info`)
    if (!el) continue
    if (meses > 1) {
      el.textContent = `= R$ ${fmtR$(total / meses)}/mês · ${meses}× parcelas`
    } else {
      el.textContent = `= R$ ${fmtR$(total)} à vista`
    }
  }
}

function _renderTabelaParcelas(cfg) {
  const planos = [
    { key: 'mensal',      total: cfg.preco_mensal,      meses: 1  },
    { key: 'trimestral',  total: cfg.preco_trimestral,  meses: 3  },
    { key: 'semestral',   total: cfg.preco_semestral,   meses: 6  },
    { key: 'anual',       total: cfg.preco_anual,       meses: 12 },
  ]
  document.getElementById('tbody-parcelas').innerHTML = planos.map(({ key, total, meses }) => {
    const porParcela = meses > 1 ? fmtR$(total / meses) : '—'
    const parcLabel  = meses > 1 ? `${meses}×` : '1× (à vista)'
    return `<tr>
      <td>${_PLANO_LABEL2[key]}</td>
      <td>${parcLabel}</td>
      <td>${meses > 1 ? 'R$ ' + porParcela : '—'}</td>
      <td>R$ ${fmtR$(total)}</td>
    </tr>`
  }).join('')
}

async function salvarConfiguracoes(e) {
  e.preventDefault()
  showErr('cfg-erro', '')

  const antMin    = parseInt(document.getElementById('cfg-ant-ranking-min').value, 10)
  const antUltima = parseInt(document.getElementById('cfg-ant-ranking-ultima').value, 10)
  if (antUltima >= antMin) {
    showErr('cfg-erro', 'A janela de última hora do ranking deve ser menor que a antecedência mínima.')
    return
  }
  if (!document.getElementById('cfg-msg-planos').value.trim() ||
      !document.getElementById('cfg-msg-reservas').value.trim()) {
    showErr('cfg-erro', 'As mensagens de aviso não podem ficar vazias.')
    return
  }

  const btn = e.submitter
  btn.disabled = true
  try {
    const resp = await api('/admin/configuracoes', {
      method: 'PUT',
      body: JSON.stringify({
        preco_mensal:      parseFloat(document.getElementById('cfg-mensal').value),
        preco_trimestral:  parseFloat(document.getElementById('cfg-trimestral').value),
        preco_semestral:   parseFloat(document.getElementById('cfg-semestral').value),
        preco_anual:       parseFloat(document.getElementById('cfg-anual').value),
        preco_locacao_hora: parseFloat(document.getElementById('cfg-locacao').value),
        preco_jogo_avulso: parseFloat(document.getElementById('cfg-jogo-avulso').value),

        contratacao_planos_ativa:  document.getElementById('cfg-planos-ativa').checked,
        reservas_ativas:           document.getElementById('cfg-reservas-ativa').checked,
        msg_planos_desabilitado:   document.getElementById('cfg-msg-planos').value,
        msg_reservas_desabilitado: document.getElementById('cfg-msg-reservas').value,

        ranking_antecedencia_minima_horas: parseInt(document.getElementById('cfg-ant-ranking-min').value, 10),
        ranking_ultima_hora_horas:         parseInt(document.getElementById('cfg-ant-ranking-ultima').value, 10),
        jogo_avulso_ultima_hora_horas:     parseInt(document.getElementById('cfg-ant-jogo-avulso').value, 10),
        locacao_libera_slot_ranking_horas: parseInt(document.getElementById('cfg-ant-locacao').value, 10),
      }),
    })
    // Recarrega _precos para atualizar o modal de assinatura
    _precos = await api('/subscriptions/precos').catch(() => _precos)
    // Atualiza infos visuais
    const cfg = {
      preco_mensal:      parseFloat(document.getElementById('cfg-mensal').value),
      preco_trimestral:  parseFloat(document.getElementById('cfg-trimestral').value),
      preco_semestral:   parseFloat(document.getElementById('cfg-semestral').value),
      preco_anual:       parseFloat(document.getElementById('cfg-anual').value),
      preco_locacao_hora: parseFloat(document.getElementById('cfg-locacao').value),
    }
    _atualizarInfoPrecos(cfg)
    _renderTabelaParcelas(cfg)
    const avisados = resp?.lista_espera_avisada || 0
    toast(avisados > 0
      ? `Configurações salvas · ${avisados} pessoa(s) da lista de espera avisada(s) da abertura`
      : 'Configurações salvas')
  } catch (err) {
    showErr('cfg-erro', err.message)
  } finally {
    btn.disabled = false
  }
}

// Atualiza info ao digitar novo valor
;['cfg-mensal','cfg-trimestral','cfg-semestral','cfg-anual','cfg-locacao'].forEach(id => {
  document.addEventListener('DOMContentLoaded', () => {
    document.getElementById(id)?.addEventListener('input', () => {
      _atualizarInfoPrecos({
        preco_mensal:       parseFloat(document.getElementById('cfg-mensal').value)     || 0,
        preco_trimestral:   parseFloat(document.getElementById('cfg-trimestral').value) || 0,
        preco_semestral:    parseFloat(document.getElementById('cfg-semestral').value)  || 0,
        preco_anual:        parseFloat(document.getElementById('cfg-anual').value)      || 0,
        preco_locacao_hora: parseFloat(document.getElementById('cfg-locacao').value)    || 0,
      })
    })
  })
})

// ── Locações de Quadra ───────────────────────────────────────────────────────

async function loadLocacoes() {
  const lista = document.getElementById('lista-locacoes')
  lista.innerHTML = '<p style="opacity:.5;text-align:center;padding:1rem">Carregando…</p>'
  try {
    const locacoes = await api('/admin/locacoes')
    if (!locacoes.length) {
      lista.innerHTML = '<p style="opacity:.5;text-align:center;padding:1rem">Nenhuma locação registrada.</p>'
      return
    }

    const _stMap = {
      confirmada:            { cls: 'b-confirmado', label: 'Confirmada' },
      aguardando_pagamento:  { cls: 'b-aguardando', label: 'Ag. Pagamento' },
      cancelada:             { cls: 'b-cancelado',  label: 'Cancelada' },
    }
    const _pgMap = {
      pago:    { cls: 'b-confirmado', label: 'Pago' },
      pendente:{ cls: 'b-pendente',   label: 'Pendente' },
      falhou:  { cls: 'b-falhou',     label: 'Falhou' },
    }

    lista.innerHTML = locacoes.map(l => {
      const ini   = new Date(l.data_hora_inicio)
      const fim   = new Date(l.data_hora_fim)
      const dia   = ini.toLocaleDateString('pt-BR', { day: '2-digit', month: '2-digit', year: '2-digit' })
      const hIni  = ini.toLocaleTimeString('pt-BR', { hour: '2-digit', minute: '2-digit' })
      const hFim  = fim.toLocaleTimeString('pt-BR', { hour: '2-digit', minute: '2-digit' })

      const st  = _stMap[l.status]  || { cls: 'bnc', label: l.status }
      const pg  = l.pagamento_status ? (_pgMap[l.pagamento_status] || { cls: 'bnc', label: l.pagamento_status }) : null
      const pgMetodo = l.pagamento_metodo ? `<small style="opacity:.6"> · ${l.pagamento_metodo}</small>` : ''

      const cancelBtn = l.status !== 'cancelada'
        ? `<button class="btn-xs" style="background:var(--clr-danger,#c0392b);color:#fff;white-space:nowrap" onclick="cancelarLocacao(${l.id})">Cancelar</button>`
        : ''

      return `<div class="locacao-card">
        <div class="lc-data">
          <div class="lc-dia">${dia}</div>
          <div class="lc-hora">${hIni} – ${hFim}</div>
        </div>
        <div class="lc-jogador">
          <div class="lc-nome">${l.jogador_nome || '—'}</div>
          <div class="lc-email">${l.jogador_email || ''}</div>
        </div>
        <div class="lc-valor">R$ ${Number(l.valor).toFixed(2).replace('.', ',')}</div>
        <div class="lc-badges">
          <span class="badge ${st.cls}">${st.label}</span>
          ${pg ? `<span class="badge ${pg.cls}">${pg.label}${pgMetodo}</span>` : '<span class="badge bnc">Sem pgto</span>'}
        </div>
        <div class="lc-actions">${cancelBtn}</div>
      </div>`
    }).join('')
  } catch (e) {
    lista.innerHTML = `<p style="color:var(--clr-danger,red);padding:.5rem">Erro ao carregar: ${e.message}</p>`
  }
}

async function cancelarLocacao(id) {
  if (!confirm('Cancelar esta locação de quadra?')) return
  try {
    await api(`/admin/locacoes/${id}/cancelar`, { method: 'PATCH' })
    toast('Locação cancelada.')
    loadLocacoes()
  } catch (e) {
    toast(e.message || 'Erro ao cancelar.', true)
  }
}

// ── Slots de Ranking ─────────────────────────────────────────────────────────

const DIAS_SEMANA = ['Segunda','Terça','Quarta','Quinta','Sexta','Sábado','Domingo']

async function loadSlotsRanking() {
  const tbody = document.getElementById('tbody-slots-ranking')
  if (!tbody) return
  tbody.innerHTML = '<tr><td colspan="5" style="text-align:center;opacity:.5;padding:1rem">Carregando…</td></tr>'
  try {
    const slots = await api('/admin/slots-ranking')
    if (!slots.length) {
      tbody.innerHTML = '<tr><td colspan="5" style="text-align:center;opacity:.5;padding:1rem">Nenhum horário cadastrado.</td></tr>'
      return
    }
    tbody.innerHTML = slots.map(s => `
      <tr>
        <td>${DIAS_SEMANA[s.dia_semana] ?? s.dia_semana}</td>
        <td>${s.hora_inicio.slice(0,5)}</td>
        <td>${s.hora_fim.slice(0,5)}</td>
        <td>
          <span style="font-size:.78rem;padding:.2rem .5rem;border-radius:.35rem;background:${s.ativo ? 'rgba(111,207,151,.15)' : 'rgba(240,80,80,.12)'};color:${s.ativo ? '#6fcf97' : '#f08080'}">
            ${s.ativo ? 'Ativo' : 'Inativo'}
          </span>
        </td>
        <td style="display:flex;gap:.4rem">
          <button class="btn-xs" onclick='abrirModalSlotRanking(${JSON.stringify(s)})'>Editar</button>
          <button class="btn-xs" onclick="toggleSlotRanking(${s.id},${s.ativo})" title="${s.ativo ? 'Desativar' : 'Ativar'}">${s.ativo ? 'Pausar' : 'Ativar'}</button>
          <button class="btn-xs danger" onclick="deletarSlotRanking(${s.id})">Excluir</button>
        </td>
      </tr>`).join('')
  } catch {
    tbody.innerHTML = '<tr><td colspan="5" style="text-align:center;color:#f08080;padding:1rem">Erro ao carregar.</td></tr>'
  }
}

let _srEditId = null

function abrirModalSlotRanking(slot = null) {
  _srEditId = slot ? slot.id : null
  document.getElementById('sr-modal-titulo').textContent = slot ? 'Editar Horário de Ranking' : 'Adicionar Horário de Ranking'
  document.getElementById('sr-dia').value    = slot ? slot.dia_semana : 0
  document.getElementById('sr-inicio').value = slot ? slot.hora_inicio.slice(0, 5) : '07:00'
  document.getElementById('sr-fim').value    = slot ? slot.hora_fim.slice(0, 5)    : '09:00'
  document.getElementById('sr-erro').style.display = 'none'
  document.getElementById('modal-slot-ranking').style.display = 'flex'
}
function fecharModalSlotRanking() {
  document.getElementById('modal-slot-ranking').style.display = 'none'
  _srEditId = null
}

async function salvarSlotRanking() {
  const erEl = document.getElementById('sr-erro')
  erEl.style.display = 'none'
  const dia = parseInt(document.getElementById('sr-dia').value)
  const inicio = document.getElementById('sr-inicio').value
  const fim = document.getElementById('sr-fim').value
  if (!inicio || !fim) { erEl.textContent = 'Informe horário de início e fim.'; erEl.style.display = 'block'; return }
  if (inicio >= fim) { erEl.textContent = 'Hora de início deve ser anterior à hora de fim.'; erEl.style.display = 'block'; return }
  try {
    const url = _srEditId ? `/admin/slots-ranking/${_srEditId}` : '/admin/slots-ranking'
    const method = _srEditId ? 'PUT' : 'POST'
    await api(url, { method, body: JSON.stringify({ dia_semana: dia, hora_inicio: inicio, hora_fim: fim }) })
    fecharModalSlotRanking()
    loadSlotsRanking()
    toast(_srEditId ? 'Horário atualizado!' : 'Horário de ranking adicionado!')
  } catch(e) {
    erEl.textContent = e?.message || 'Erro ao salvar.'; erEl.style.display = 'block'
  }
}

async function toggleSlotRanking(id, ativo) {
  if (!confirm(ativo ? 'Desativar este horário de ranking?' : 'Ativar este horário de ranking?')) return
  try {
    await api(`/admin/slots-ranking/${id}/toggle`, { method: 'PATCH' })
    loadSlotsRanking()
  } catch { toast('Erro ao atualizar.', true) }
}

async function deletarSlotRanking(id) {
  if (!confirm('Excluir este horário de ranking?')) return
  try {
    await api(`/admin/slots-ranking/${id}`, { method: 'DELETE' })
    loadSlotsRanking()
    toast('Horário excluído.')
  } catch { toast('Erro ao excluir.', true) }
}

// ── Feriados e Horários Especiais ────────────────────────────────────────────

let _heEditId = null

async function loadHorariosEspeciais() {
  const tbody = document.getElementById('tbody-horarios-especiais')
  if (!tbody) return
  try {
    const items = await api('/admin/horarios-especiais')
    if (!items.length) {
      tbody.innerHTML = '<tr><td colspan="4" style="text-align:center;opacity:.5;padding:.75rem">Nenhum dia especial cadastrado.</td></tr>'
      return
    }
    tbody.innerHTML = items.map(he => {
      const datFmt = new Date(he.data + 'T12:00:00').toLocaleDateString('pt-BR')
      const horario = he.fechado
        ? '<span class="badge b-cancelado">Fechado</span>'
        : (he.hora_abertura != null ? `${he.hora_abertura}h – ${he.hora_fechamento}h` : 'Horário normal')
      return `<tr>
        <td>${datFmt}</td>
        <td>${escHtml(he.descricao)}</td>
        <td>${horario}</td>
        <td style="display:flex;gap:.3rem">
          <button class="btn-xs" onclick='abrirModalHorarioEspecial(${JSON.stringify(he)})'>Editar</button>
          <button class="btn-xs danger" onclick="deletarHorarioEspecial(${he.id})">Excluir</button>
        </td>
      </tr>`
    }).join('')
  } catch(e) {
    tbody.innerHTML = `<tr><td colspan="4" style="color:var(--clr-danger,red);padding:.5rem">${e.message}</td></tr>`
  }
}

function abrirModalHorarioEspecial(he = null) {
  _heEditId = he ? he.id : null
  document.getElementById('he-modal-titulo').textContent = he ? 'Editar Dia Especial' : 'Adicionar Dia Especial'
  document.getElementById('he-data').value      = he ? he.data : ''
  document.getElementById('he-descricao').value = he ? he.descricao : ''
  document.getElementById('he-fechado').checked = he ? he.fechado : false
  document.getElementById('he-abertura').value  = (he && he.hora_abertura != null) ? he.hora_abertura : ''
  document.getElementById('he-fechamento').value = (he && he.hora_fechamento != null) ? he.hora_fechamento : ''
  document.getElementById('he-erro').style.display = 'none'
  toggleHeFechado()
  document.getElementById('modal-horario-especial').style.display = 'flex'
}

function fecharModalHorarioEspecial() {
  document.getElementById('modal-horario-especial').style.display = 'none'
  _heEditId = null
}

function toggleHeFechado() {
  const fechado = document.getElementById('he-fechado').checked
  document.getElementById('he-horario-section').style.display = fechado ? 'none' : ''
}

async function salvarHorarioEspecial() {
  const errEl = document.getElementById('he-erro')
  errEl.style.display = 'none'
  const data       = document.getElementById('he-data').value
  const descricao  = document.getElementById('he-descricao').value.trim()
  const fechado    = document.getElementById('he-fechado').checked
  const aberturaV  = document.getElementById('he-abertura').value
  const fechamentoV = document.getElementById('he-fechamento').value
  if (!data || !descricao) {
    errEl.textContent = 'Data e descrição são obrigatórios.'
    errEl.style.display = ''
    return
  }
  const body = {
    data, descricao, fechado,
    hora_abertura:   aberturaV  !== '' ? parseInt(aberturaV)  : null,
    hora_fechamento: fechamentoV !== '' ? parseInt(fechamentoV) : null,
  }
  try {
    const url    = _heEditId ? `/admin/horarios-especiais/${_heEditId}` : '/admin/horarios-especiais'
    const method = _heEditId ? 'PUT' : 'POST'
    await api(url, { method, body: JSON.stringify(body) })
    fecharModalHorarioEspecial()
    toast(_heEditId ? 'Dia especial atualizado.' : 'Dia especial adicionado.')
    loadHorariosEspeciais()
  } catch(e) {
    errEl.textContent = e?.message || 'Erro ao salvar.'
    errEl.style.display = ''
  }
}

async function deletarHorarioEspecial(id) {
  if (!confirm('Excluir este dia especial?')) return
  try {
    await api(`/admin/horarios-especiais/${id}`, { method: 'DELETE' })
    toast('Dia especial excluído.')
    loadHorariosEspeciais()
  } catch(e) {
    toast(e?.message || 'Erro ao excluir.', true)
  }
}

// ── Lista de Espera ───────────────────────────────────────────────────────────

async function loadListaEspera() {
  const wrap = document.getElementById('le-tabela-wrap')
  const badge = document.getElementById('le-vagas-badge')
  const aviso = document.getElementById('le-aviso-vagas')
  wrap.innerHTML = '<p style="color:var(--clr-text-muted);text-align:center;padding:2rem">Carregando…</p>'
  try {
    const r = await api('/admin/lista-espera')
    const { fila, vagas } = r

    badge.textContent = `${vagas.ocupadas}/${vagas.limite} vagas ocupadas · ${vagas.disponiveis} disponível(is)`

    if (vagas.disponiveis > 0 && fila.length > 0) {
      aviso.style.display = 'block'
      aviso.textContent = `Há ${vagas.disponiveis} vaga(s) disponível(is) e ${fila.length} pessoa(s) na fila. Convoque manualmente ou aguarde a convocação automática.`
    } else {
      aviso.style.display = 'none'
    }

    if (!fila.length) {
      wrap.innerHTML = '<p style="color:var(--clr-text-muted);text-align:center;padding:2rem">Nenhuma pessoa na lista de espera.</p>'
      return
    }

    const rows = fila.map(e => {
      const statusLabel = { aguardando: 'Aguardando', convocado: 'Convocado' }[e.status] || e.status
      const statusColor = e.status === 'convocado' ? '#e0a040' : '#4ab870'
      const dtInscricao = new Date(e.data_inscricao).toLocaleString('pt-BR', { timeZone: 'America/Sao_Paulo', day: '2-digit', month: '2-digit', year: 'numeric', hour: '2-digit', minute: '2-digit' })
      const dtExpira = e.data_expiracao_convocacao
        ? new Date(e.data_expiracao_convocacao).toLocaleString('pt-BR', { timeZone: 'America/Sao_Paulo', day: '2-digit', month: '2-digit', year: 'numeric', hour: '2-digit', minute: '2-digit' })
        : '—'
      return `<tr>
        <td style="text-align:center;font-weight:700;font-size:1.1rem">#${e.posicao}</td>
        <td>${e.player_nome}</td>
        <td style="color:var(--clr-text-muted);font-size:.85rem">${e.player_email}</td>
        <td style="color:var(--clr-text-muted);font-size:.85rem">${e.player_telefone || '—'}</td>
        <td style="color:${statusColor};font-weight:600">${statusLabel}</td>
        <td style="font-size:.82rem">${dtInscricao}</td>
        <td style="font-size:.82rem">${e.status === 'convocado' ? dtExpira : '—'}</td>
        <td>
          <div style="display:flex;gap:.4rem">
            ${e.status === 'aguardando' ? `<button class="btn-xs primary" onclick="leConvocar(${e.id})" title="Convocar agora">Convocar</button>` : ''}
            <button class="btn-xs danger" onclick="leRemover(${e.id})" title="Remover da lista">Remover</button>
          </div>
        </td>
      </tr>`
    }).join('')

    wrap.innerHTML = `<table class="admin-table" style="min-width:900px">
      <thead><tr>
        <th>#</th><th>Nome</th><th>E-mail</th><th>Telefone</th>
        <th>Status</th><th>Inscrito em</th><th>Convocação expira</th><th>Ações</th>
      </tr></thead>
      <tbody>${rows}</tbody>
    </table>`
  } catch (e) {
    wrap.innerHTML = `<p style="color:#e74c3c;text-align:center;padding:2rem">Erro ao carregar: ${e.message}</p>`
  }
}

async function leConvocar(id) {
  if (!confirm('Convocar este jogador agora? Ele receberá e-mail com 48h para confirmar.')) return
  try {
    await api(`/admin/lista-espera/${id}/convocar`, { method: 'POST' })
    showToast('Jogador convocado! E-mail enviado.', 'success')
    loadListaEspera()
  } catch (e) {
    showToast('Erro: ' + e.message, 'error')
  }
}

async function leRemover(id) {
  if (!confirm('Remover este jogador da lista de espera?')) return
  try {
    await api(`/admin/lista-espera/${id}`, { method: 'DELETE' })
    showToast('Removido da lista de espera.', 'success')
    loadListaEspera()
  } catch (e) {
    showToast('Erro: ' + e.message, 'error')
  }
}

// ── Contrato ─────────────────────────────────────────────────────────────────

let _contratoClausulas = []

async function loadContrato() {
  const wrap = document.getElementById('contrato-clausulas-wrap')
  wrap.innerHTML = '<p style="color:var(--clr-text-muted);text-align:center;padding:2rem">Carregando…</p>'
  try {
    _contratoClausulas = await api('/admin/contrato/clausulas')
    _renderContrato()
  } catch (e) {
    wrap.innerHTML = `<p style="color:#e74c3c;text-align:center;padding:2rem">Erro ao carregar: ${e.message}</p>`
  }
}

function _renderContrato() {
  const wrap = document.getElementById('contrato-clausulas-wrap')
  if (!_contratoClausulas.length) {
    wrap.innerHTML = '<p style="color:var(--clr-text-muted);text-align:center;padding:2rem">Nenhuma cláusula cadastrada. Clique em "+ Adicionar Cláusula".</p>'
    return
  }
  wrap.innerHTML = _contratoClausulas.map((c, i) => `
    <div class="contrato-clausula-card" data-idx="${i}" style="
      background:var(--clr-surface);border:1px solid var(--clr-border);
      border-radius:8px;padding:1rem;margin-bottom:.75rem;
    ">
      <div style="display:flex;gap:.5rem;align-items:center;margin-bottom:.6rem">
        <span style="font-size:.75rem;color:var(--clr-text-muted);min-width:2.5rem">#${i + 1}</span>
        <input
          class="ct-titulo"
          value="${_escHtml(c.titulo)}"
          style="flex:1;background:rgba(255,255,255,0.07);border:1px solid var(--clr-border);
                 border-radius:4px;padding:.35rem .6rem;color:var(--clr-text);font-size:.9rem;font-weight:600"
          placeholder="Título da cláusula"
        >
        <label style="display:flex;align-items:center;gap:.3rem;font-size:.8rem;cursor:pointer;white-space:nowrap">
          <input type="checkbox" class="ct-ativo" ${c.ativo ? 'checked' : ''} style="cursor:pointer">
          Ativa
        </label>
        <div style="display:flex;gap:.25rem">
          <button class="btn-xs sec" onclick="contratoMover(${i},-1)" title="Subir" ${i === 0 ? 'disabled' : ''}>▲</button>
          <button class="btn-xs sec" onclick="contratoMover(${i},1)" title="Descer" ${i === _contratoClausulas.length - 1 ? 'disabled' : ''}>▼</button>
          <button class="btn-xs danger" onclick="contratoRemover(${i})" title="Remover">✕</button>
        </div>
      </div>
      <textarea
        class="ct-texto"
        rows="5"
        style="width:100%;background:rgba(255,255,255,0.05);border:1px solid var(--clr-border);
               border-radius:4px;padding:.5rem .6rem;color:var(--clr-text);font-size:.85rem;
               resize:vertical;line-height:1.5"
        placeholder="Texto da cláusula…"
      >${_escHtml(c.texto)}</textarea>
    </div>
  `).join('')
}

function _escHtml(s) {
  return (s || '').replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;').replace(/"/g,'&quot;')
}

function _coletarClausulas() {
  const cards = document.querySelectorAll('.contrato-clausula-card')
  return Array.from(cards).map(card => ({
    titulo: card.querySelector('.ct-titulo').value.trim(),
    texto:  card.querySelector('.ct-texto').value.trim(),
    ativo:  card.querySelector('.ct-ativo').checked,
  }))
}

function contratoMover(idx, dir) {
  _contratoClausulas = _coletarClausulas()
  const novo = idx + dir
  if (novo < 0 || novo >= _contratoClausulas.length) return
  ;[_contratoClausulas[idx], _contratoClausulas[novo]] = [_contratoClausulas[novo], _contratoClausulas[idx]]
  _renderContrato()
}

function contratoRemover(idx) {
  if (!confirm('Remover esta cláusula?')) return
  _contratoClausulas = _coletarClausulas()
  _contratoClausulas.splice(idx, 1)
  _renderContrato()
}

function contratoAddClausula() {
  _contratoClausulas = _coletarClausulas()
  _contratoClausulas.push({ titulo: '', texto: '', ativo: true })
  _renderContrato()
  // Scroll para o novo card
  const cards = document.querySelectorAll('.contrato-clausula-card')
  if (cards.length) cards[cards.length - 1].scrollIntoView({ behavior: 'smooth', block: 'center' })
}

async function salvarContrato() {
  const clausulas = _coletarClausulas()
  if (!clausulas.length) { showToast('Adicione ao menos uma cláusula.', 'error'); return }
  try {
    const r = await api('/admin/contrato/clausulas', { method: 'PUT', body: JSON.stringify(clausulas) })
    showToast(`Contrato salvo! ${r.total} cláusula(s).`, 'success')
    await loadContrato()
  } catch (e) {
    showToast('Erro ao salvar: ' + e.message, 'error')
  }
}

// ── Horários por dia da semana ────────────────────────────────────────────────

const DIAS_NOMES = ['Segunda', 'Terça', 'Quarta', 'Quinta', 'Sexta', 'Sábado', 'Domingo']
let _horarios = []

async function loadHorarios() {
  const wrap = document.getElementById('horarios-wrap')
  wrap.innerHTML = '<p style="color:var(--clr-text-muted);text-align:center;padding:2rem">Carregando…</p>'
  try {
    _horarios = await api('/admin/horarios-semana')
    _renderHorarios()
  } catch (e) {
    wrap.innerHTML = `<p style="color:var(--clr-danger)">Erro: ${e.message}</p>`
  }
}

function _renderHorarios() {
  const wrap = document.getElementById('horarios-wrap')
  wrap.innerHTML = `
    <table style="width:100%;border-collapse:collapse;font-size:.9rem">
      <thead>
        <tr style="border-bottom:1px solid var(--clr-border);color:var(--clr-text-muted)">
          <th style="text-align:left;padding:.5rem .75rem">Dia</th>
          <th style="text-align:center;padding:.5rem .75rem">Aberto</th>
          <th style="text-align:center;padding:.5rem .75rem">Abertura</th>
          <th style="text-align:center;padding:.5rem .75rem">Fechamento</th>
        </tr>
      </thead>
      <tbody>
        ${_horarios.map((h, i) => `
          <tr style="border-bottom:1px solid var(--clr-border)">
            <td style="padding:.6rem .75rem;font-weight:500">${DIAS_NOMES[h.dia_semana]}</td>
            <td style="text-align:center;padding:.6rem .75rem">
              <input type="checkbox" id="h-aberto-${i}" ${h.aberto ? 'checked' : ''}
                onchange="_horariosToggleAberto(${i})" style="width:16px;height:16px;cursor:pointer" />
            </td>
            <td style="text-align:center;padding:.6rem .75rem">
              <select id="h-ab-${i}" ${!h.aberto ? 'disabled' : ''}
                style="padding:.3rem .5rem;border-radius:6px;border:1px solid var(--clr-border);
                       background:var(--clr-surface);color:inherit;font-size:.88rem">
                ${_opcoesHora(h.hora_abertura)}
              </select>
            </td>
            <td style="text-align:center;padding:.6rem .75rem">
              <select id="h-fe-${i}" ${!h.aberto ? 'disabled' : ''}
                style="padding:.3rem .5rem;border-radius:6px;border:1px solid var(--clr-border);
                       background:var(--clr-surface);color:inherit;font-size:.88rem">
                ${_opcoesHora(h.hora_fechamento)}
              </select>
            </td>
          </tr>
        `).join('')}
      </tbody>
    </table>
  `
}

function _opcoesHora(selecionada) {
  let html = ''
  for (let h = 0; h <= 24; h++) {
    html += `<option value="${h}" ${h === selecionada ? 'selected' : ''}>${String(h).padStart(2,'0')}:00</option>`
  }
  return html
}

function _horariosToggleAberto(idx) {
  const aberto = document.getElementById(`h-aberto-${idx}`).checked
  document.getElementById(`h-ab-${idx}`).disabled = !aberto
  document.getElementById(`h-fe-${idx}`).disabled = !aberto
}

async function salvarHorarios() {
  const payload = _horarios.map((h, i) => ({
    dia_semana: h.dia_semana,
    aberto: document.getElementById(`h-aberto-${i}`).checked,
    hora_abertura: parseInt(document.getElementById(`h-ab-${i}`).value, 10),
    hora_fechamento: parseInt(document.getElementById(`h-fe-${i}`).value, 10),
  }))
  // Validação básica
  for (const h of payload) {
    if (h.aberto && h.hora_abertura >= h.hora_fechamento) {
      showToast(`${DIAS_NOMES[h.dia_semana]}: abertura deve ser antes do fechamento.`, 'error')
      return
    }
  }
  try {
    await api('/admin/horarios-semana', { method: 'PUT', body: JSON.stringify(payload) })
    showToast('Horários salvos com sucesso!', 'success')
    _horarios = payload
  } catch (e) {
    showToast('Erro ao salvar: ' + e.message, 'error')
  }
}

// ── Dados da empresa ──────────────────────────────────────────────────────────

async function loadEmpresa() {
  try {
    const e = await api('/admin/empresa')
    document.getElementById('emp-razao-social').value    = e.razao_social    ?? ''
    document.getElementById('emp-nome-fantasia').value   = e.nome_fantasia   ?? ''
    document.getElementById('emp-cnpj').value            = e.cnpj            ?? ''
    document.getElementById('emp-cpf-responsavel').value = e.cpf_responsavel ?? ''
    document.getElementById('emp-logradouro').value      = e.end_logradouro  ?? ''
    document.getElementById('emp-numero').value          = e.end_numero      ?? ''
    document.getElementById('emp-complemento').value     = e.end_complemento ?? ''
    document.getElementById('emp-bairro').value          = e.end_bairro      ?? ''
    document.getElementById('emp-cidade').value          = e.end_cidade      ?? ''
    document.getElementById('emp-estado').value          = e.end_estado      ?? ''
    document.getElementById('emp-pais').value            = e.end_pais        ?? ''
    document.getElementById('emp-cep').value             = e.end_cep         ?? ''
    document.getElementById('emp-whatsapp').value        = e.whatsapp        ?? ''
    document.getElementById('emp-instagram').value       = e.instagram       ?? ''
    document.getElementById('emp-email').value           = e.email_contato   ?? ''
  } catch (err) {
    toast('Erro ao carregar dados da empresa: ' + err.message, true)
  }
}

async function salvarEmpresa(e) {
  if (e) e.preventDefault()
  showErr('emp-erro', '')
  try {
    await api('/admin/empresa', {
      method: 'PUT',
      body: JSON.stringify({
        razao_social:    document.getElementById('emp-razao-social').value.trim(),
        nome_fantasia:   document.getElementById('emp-nome-fantasia').value.trim(),
        cnpj:            document.getElementById('emp-cnpj').value.trim(),
        cpf_responsavel: document.getElementById('emp-cpf-responsavel').value.trim(),
        end_logradouro:  document.getElementById('emp-logradouro').value.trim(),
        end_numero:      document.getElementById('emp-numero').value.trim(),
        end_complemento: document.getElementById('emp-complemento').value.trim(),
        end_bairro:      document.getElementById('emp-bairro').value.trim(),
        end_cidade:      document.getElementById('emp-cidade').value.trim(),
        end_estado:      document.getElementById('emp-estado').value.trim(),
        end_pais:        document.getElementById('emp-pais').value.trim(),
        end_cep:         document.getElementById('emp-cep').value.trim(),
        whatsapp:        document.getElementById('emp-whatsapp').value.trim(),
        instagram:       document.getElementById('emp-instagram').value.trim(),
        email_contato:   document.getElementById('emp-email').value.trim(),
      }),
    })
    toast('Dados da empresa salvos!')
  } catch (err) {
    showErr('emp-erro', err.message)
  }
}

// ── Sidebar recolhível ───────────────────────────────────────────────────────

function toggleSidebar() {
  const sidebar = document.querySelector('.admin-sidebar')
  const btn = document.getElementById('sidebar-toggle')
  const collapsed = sidebar.classList.toggle('collapsed')
  btn.textContent = collapsed ? '▶' : '◀'
  try { localStorage.setItem('sidebar-collapsed', collapsed ? '1' : '0') } catch (_) {}
}

function initSidebar() {
  try {
    if (localStorage.getItem('sidebar-collapsed') === '1') {
      document.querySelector('.admin-sidebar').classList.add('collapsed')
      const btn = document.getElementById('sidebar-toggle')
      if (btn) btn.textContent = '▶'
    }
  } catch (_) {}
}

// ── Boot ──────────────────────────────────────────────────────────────────────

init()
initSidebar()
