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
    case 'dashboard':   loadDashboard(); break
    case 'jogadores':   loadPlayers(); break
    case 'partidas':    loadMatches(); break
    case 'temporada':   loadSeasons(); break
    case 'matchmaking': loadInvitations(); break
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
    _players = await api('/players')
    renderJogadores(_players)
  } catch (err) {
    toast('Erro ao carregar jogadores: ' + err.message, true)
  }
}

function filtrarJogadores() {
  const q = document.getElementById('busca-jogador').value.toLowerCase()
  const lista = q ? _players.filter(p => p.nome.toLowerCase().includes(q) || p.email.toLowerCase().includes(q)) : _players
  renderJogadores(lista)
}

function renderJogadores(lista) {
  const tb = document.getElementById('tbody-jogadores')
  if (!lista.length) {
    tb.innerHTML = '<tr><td colspan="7" class="empty">Nenhum jogador encontrado</td></tr>'
    return
  }
  tb.innerHTML = lista.map(p => `
    <tr>
      <td>${escHtml(p.nome)}${p.is_admin ? ' <span class="badge ba">admin</span>' : ''}</td>
      <td style="color:var(--clr-text-muted)">${escHtml(p.email)}</td>
      <td>${nivelBadge(p.nivel)}</td>
      <td>${p.rating_atual.toFixed(0)}</td>
      <td>${p.pontos_ranking_temporada_atual}</td>
      <td>${p.aceita_convites_sistema ? '✓' : '–'}</td>
      <td><button class="btn-xs sec" onclick="abrirModalJogador(${p.id})">Editar</button></td>
    </tr>
  `).join('')
}

function abrirModalJogador(playerId = null) {
  document.getElementById('modal-jogador-titulo').textContent = playerId ? 'Editar Jogador' : 'Criar Jogador'
  document.getElementById('jog-id').value = playerId || ''
  document.getElementById('jog-nome').value = ''
  document.getElementById('jog-email').value = ''
  document.getElementById('jog-telefone').value = ''
  document.getElementById('jog-senha').value = ''
  document.getElementById('jog-convites').checked = false
  document.getElementById('jog-is-admin').checked = false
  document.getElementById('row-nivel').style.display = playerId ? '' : 'none'
  document.getElementById('row-is-admin').style.display = playerId ? '' : 'none'
  document.getElementById('row-senha').style.display = playerId ? 'none' : ''
  showErr('jog-erro', '')

  if (playerId) {
    const p = _players.find(x => x.id === playerId)
    if (p) {
      document.getElementById('jog-nome').value = p.nome
      document.getElementById('jog-email').value = p.email
      document.getElementById('jog-telefone').value = p.telefone
      document.getElementById('jog-convites').checked = p.aceita_convites_sistema
      document.getElementById('jog-is-admin').checked = p.is_admin
      document.getElementById('jog-nivel').value = p.nivel
    }
  }
  document.getElementById('modal-jogador').classList.add('open')
}

function fecharModalJogador() {
  document.getElementById('modal-jogador').classList.remove('open')
}

async function salvarJogador(e) {
  e.preventDefault()
  showErr('jog-erro', '')
  const id = document.getElementById('jog-id').value
  const btn = e.submitter
  btn.disabled = true

  try {
    if (id) {
      // Editar via admin endpoint (suporta nivel + is_admin)
      const body = {
        nome: document.getElementById('jog-nome').value,
        email: document.getElementById('jog-email').value,
        telefone: document.getElementById('jog-telefone').value,
        aceita_convites_sistema: document.getElementById('jog-convites').checked,
        nivel: document.getElementById('jog-nivel').value,
        is_admin: document.getElementById('jog-is-admin').checked,
      }
      await api(`/admin/players/${id}`, { method: 'PATCH', body: JSON.stringify(body) })
      toast('Jogador atualizado')
    } else {
      // Criar
      const senha = document.getElementById('jog-senha').value
      if (!senha) { showErr('jog-erro', 'Senha obrigatória ao criar jogador'); return }
      const body = {
        nome: document.getElementById('jog-nome').value,
        email: document.getElementById('jog-email').value,
        telefone: document.getElementById('jog-telefone').value,
        senha,
      }
      await api('/players', { method: 'POST', body: JSON.stringify(body) })
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

// ── Security util ─────────────────────────────────────────────────────────────

function escHtml(str) {
  if (!str) return ''
  return String(str)
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;')
}

// ── Boot ──────────────────────────────────────────────────────────────────────

init()
