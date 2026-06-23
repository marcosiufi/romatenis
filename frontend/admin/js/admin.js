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
    case 'matchmaking':    loadInvitations(); break
    case 'configuracoes':  loadConfiguracoes(); break
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
      ? `${d.lider_ranking.nome} (${d.lider_ranking.pontos} pts)`
      : 'Sem pontuações ainda'
    extra.innerHTML = `
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
  return p.apelido ? `${p.apelido} <span style="opacity:.55;font-size:.75em">(${escHtml(p.nome)})</span>` : escHtml(p.nome)
}

function _statusBadge(status) {
  const map = {
    ativo:    '<span class="badge ba" style="background:#2a6e3a">ativo</span>',
    inativo:  '<span class="badge ba" style="background:#7a4a18">inativo</span>',
    suspenso: '<span class="badge ba" style="background:#5a1a1a">suspenso</span>',
  }
  return map[status] || status
}

function renderJogadores(lista) {
  const tb = document.getElementById('tbody-jogadores')
  if (!lista.length) {
    tb.innerHTML = '<tr><td colspan="8" class="empty">Nenhum jogador encontrado</td></tr>'
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
      <td><button class="btn-xs sec" onclick="abrirModalJogador(${p.id})">Editar</button></td>
    </tr>
  `).join('')
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
  document.getElementById('sub-st-ativas').textContent    = list.filter(s => s.status === 'ativa').length
  document.getElementById('sub-st-pausadas').textContent  = list.filter(s => s.status === 'pausada').length
  document.getElementById('sub-st-expiradas').textContent = list.filter(s => s.status === 'expirada').length
  document.getElementById('sub-st-7d').textContent        = list.filter(s =>
    s.status === 'ativa' && new Date(s.data_expiracao) <= em7d && new Date(s.data_expiracao) > hoje
  ).length
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
    <tr>
      <td>
        <strong>${escHtml(s.player_nome || '–')}</strong>
        <div style="font-size:0.72rem;color:var(--clr-text-muted)">${escHtml(s.player_email || '')}</div>
      </td>
      <td>${PLANO_LABEL[s.plano] || s.plano}</td>
      <td>${subBadge(s.status)}${s.status === 'pausada' && s.data_retorno_prevista
        ? `<div style="font-size:0.68rem;color:var(--clr-text-muted);margin-top:2px">retorno: ${fmtD(s.data_retorno_prevista)}</div>` : ''}</td>
      <td>${fmtD(s.data_inicio_ciclo)}</td>
      <td>${fmtD(s.data_expiracao)}<br>${diasRestantes(s.data_expiracao)}</td>
      <td>R$ ${Number(s.valor_total_ciclo).toFixed(2)}</td>
      <td>
        <button class="btn-xs sec" onclick="abrirModalSubStatus(${s.id}, '${s.status}')">Status</button>
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
  const forma = document.getElementById('sub-forma').value
  const p = _precos[plano]
  if (!p || typeof p !== 'object') return
  document.getElementById('sub-valor-mensal').value = p.valor_mensal ?? ''
  const isPix = forma === 'pix_avista'
  const parcelas = isPix ? 1 : (p.parcelas ?? 1)
  const total = p.valor_total ?? (p.valor_mensal * parcelas)
  const info = parcelas > 1
    ? `${parcelas}× R$ ${fmtR$(p.valor_mensal)} = R$ ${fmtR$(total)} total`
    : `R$ ${fmtR$(total)} à vista`
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

function abrirModalSubStatus(id, statusAtual) {
  document.getElementById('sub-status-id').value = id
  document.getElementById('sub-novo-status').value = statusAtual
  document.getElementById('sub-notas').value = ''
  showErr('sub-status-err', '')
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
    document.getElementById('cfg-locacao').value     = cfg.preco_locacao_hora
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
  const btn = e.submitter
  btn.disabled = true
  try {
    await api('/admin/configuracoes', {
      method: 'PUT',
      body: JSON.stringify({
        preco_mensal:      parseFloat(document.getElementById('cfg-mensal').value),
        preco_trimestral:  parseFloat(document.getElementById('cfg-trimestral').value),
        preco_semestral:   parseFloat(document.getElementById('cfg-semestral').value),
        preco_anual:       parseFloat(document.getElementById('cfg-anual').value),
        preco_locacao_hora: parseFloat(document.getElementById('cfg-locacao').value),
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
    toast('Configurações salvas')
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

// ── Boot ──────────────────────────────────────────────────────────────────────

init()
