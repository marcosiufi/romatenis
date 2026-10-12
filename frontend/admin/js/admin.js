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

/** "1 convite enviado", "3 convites enviados": nada de "convite(s)" */
const _plural = (n, um, varios) => `${n} ${n === 1 ? um : varios}`

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

// ── Alerta e confirmação ─────────────────────────────────────────────────────
// Substituem confirm(): o do navegador aparece como "localhost diz…", não
// segue a aparência do painel e trava a página. O desenho é o alerta do
// macOS: o ícone do app, título em forma de pergunta, a consequência, e o
// botão nomeado pelo verbo da ação.

const _ICONE_ALERTA = '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><circle cx="12" cy="12" r="8.5"/><path d="M6.2 5.8c2.4 1.6 3.8 3.6 3.8 6.2s-1.4 4.6-3.8 6.2"/><path d="M17.8 5.8c-2.4 1.6-3.8 3.6-3.8 6.2s1.4 4.6 3.8 6.2"/></svg>'

function alertar({ titulo, mensagem = '', botoes = [{ rotulo: 'OK', valor: true, forte: true }] }) {
  return new Promise(resolver => {
    const raiz = document.getElementById('raiz-alerta')
    const anterior = document.activeElement
    // Dois botões curtos ficam lado a lado (Cancelar à esquerda); senão,
    // empilhados com a ação principal em cima
    const lado = botoes.length === 2 && botoes.every(b => b.rotulo.length <= 12)
    const ordem = lado ? botoes : [...botoes].reverse()
    raiz.innerHTML = `
      <div class="alerta-fundo">
        <div class="alerta" role="alertdialog" aria-modal="true" aria-labelledby="alerta-t">
          <div class="alerta-icone">${_ICONE_ALERTA}</div>
          <p class="alerta-titulo" id="alerta-t">${escHtml(titulo)}</p>
          ${mensagem ? `<p class="alerta-msg">${escHtml(mensagem)}</p>` : ''}
          <div class="alerta-botoes${lado ? ' lado' : ''}">
            ${ordem.map(b => `<button type="button" data-i="${botoes.indexOf(b)}" class="${b.forte ? 'forte' : ''}${b.perigo ? ' perigo' : ''}">${escHtml(b.rotulo)}</button>`).join('')}
          </div>
        </div>
      </div>`
    const tecla = e => {
      if (e.key === 'Escape') {
        e.stopPropagation()
        const c = botoes.find(b => b.cancelar)
        fechar(c ? c.valor : false)
      }
    }
    function fechar(valor) {
      raiz.innerHTML = ''
      document.removeEventListener('keydown', tecla, true)
      anterior?.focus?.()
      resolver(valor)
    }
    raiz.querySelectorAll('button[data-i]').forEach(b => b.addEventListener('click', () => fechar(botoes[+b.dataset.i].valor)))
    document.addEventListener('keydown', tecla, true)
    ;(raiz.querySelector('button.forte, button.perigo') || raiz.querySelector('button'))?.focus()
  })
}

/** Confirmação com a ação nomeada. Destrutiva sai em vermelho. */
function confirmar(titulo, mensagem = '', { acao = 'Confirmar', perigo = false, voltar = 'Cancelar' } = {}) {
  return alertar({
    titulo, mensagem,
    botoes: [
      { rotulo: voltar, valor: false, cancelar: true },
      { rotulo: acao, valor: true, forte: !perigo, perigo },
    ],
  })
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
    const inicial = document.getElementById('admin-inicial')
    if (inicial) inicial.textContent = (me.nome || '?').trim().charAt(0).toUpperCase()
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
  const main = document.querySelector('.admin-main')
  main.scrollTop = 0
  main.classList.remove('rolada')
  switch (tab) {
    case 'dashboard':    loadDashboard(); break
    case 'financeiro':   loadFinanceiro(); break
    case 'acesso':       loadAcesso(); break
    case 'jogadores':    loadPlayers(); break
    case 'partidas':     loadMatches(); break
    case 'temporada':    loadSeasons(); break
    case 'assinaturas':    loadAssinaturas(); break
    case 'locacoes':       loadLocacoes(); break
    case 'matchmaking':    loadInvitations(); break
    case 'configuracoes':  loadConfiguracoes(); loadEmailStatus(); loadSlotsRanking(); loadHorariosEspeciais(); loadHorarios(); break
    case 'cupons':         loadCupons(); break
    case 'lista-espera':   loadListaEspera(); break
    case 'contrato':       loadContrato(); break
    case 'empresa':        loadEmpresa(); break
  }
}

// ── Dashboard ─────────────────────────────────────────────────────────────────

async function loadDashboard() {
  const hoje = new Date().toLocaleDateString('pt-BR', { weekday: 'long', day: 'numeric', month: 'long', timeZone: 'America/Sao_Paulo' })
  const elData = document.getElementById('dash-data')
  if (elData) elData.textContent = hoje.charAt(0).toUpperCase() + hoje.slice(1)
  try {
    const d = await api('/admin/dashboard')
    document.getElementById('st-jogadores').textContent = d.total_jogadores
    document.getElementById('st-subs').textContent = d.assinaturas_ativas
    document.getElementById('st-sem-placar').textContent = d.partidas_sem_placar
    document.getElementById('st-hoje').textContent = d.reservas_hoje

    const extra = document.getElementById('dash-extra')
    const diaMes = iso => new Date(iso).toLocaleDateString('pt-BR', { day: 'numeric', month: 'short', timeZone: 'UTC' })
    const tempInfo = d.temporada_ativa
      ? `De ${diaMes(d.temporada_ativa.data_inicio)} a ${diaMes(d.temporada_ativa.data_fim)}`
      : 'Nenhuma temporada ativa'
    const liderInfo = d.lider_ranking
      ? `${escHtml(d.lider_ranking.nome)}, ${d.lider_ranking.pontos} pontos`
      : 'Sem pontuações ainda'
    const plural = (n, um, varios) => `${n} ${n === 1 ? um : varios}`
    // Pendências que pedem ação vêm primeiro, com o tom do estado — e levam
    // direto à tela onde se resolve
    const pausaCard = d.pausas_pendentes > 0
      ? `<div class="dash-card" role="button" tabindex="0" onclick="switchTab('assinaturas');filtrarPausasPendentes()">
           <div class="dc-label"><span class="badge e-alerta">Pausas</span></div>
           <div class="dc-val">${plural(d.pausas_pendentes, 'pedido de pausa aguardando', 'pedidos de pausa aguardando')} aprovação</div>
         </div>`
      : ''
    // Pagou mas a Autentique nunca enviou o contrato: fica bloqueado em silêncio
    const contratoCard = d.contratos_nao_enviados > 0
      ? `<div class="dash-card" role="button" tabindex="0" onclick="switchTab('jogadores')">
           <div class="dc-label"><span class="badge e-critico">Contrato não enviado</span></div>
           <div class="dc-val">${d.contratos_nao_enviados === 1
             ? '1 jogador pagou e está bloqueado'
             : `${d.contratos_nao_enviados} jogadores pagaram e estão bloqueados`}</div>
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
        <div class="dc-label">Líder do ranking</div>
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
  return p.apelido ? `${escHtml(p.apelido)} <span style="color:var(--tinta-3);font-size:.85em">(${escHtml(p.nome)})</span>` : escHtml(p.nome)
}

function _statusBadge(status) {
  const map = {
    ativo:      '<span class="badge e-bom">Ativo</span>',
    assinatura: '<span class="badge e-alerta">Assinatura</span>',
    pagamento:  '<span class="badge e-alerta">Pagamento</span>',
    renovacao:  '<span class="badge e-tint">Renovação</span>',
    inativo:    '<span class="badge e-neutro">Inativo</span>',
  }
  return map[status] || `<span class="badge e-neutro">${escHtml(status || 'Sem status')}</span>`
}

function _contratoBadge(p) {
  if (p.contrato_assinado) return '<span class="badge e-bom">Assinado</span>'
  if (p.contrato_enviado_em) return '<span class="badge e-alerta">Aguardando</span>'
  return '<span class="badge e-neutro">Não enviado</span>'
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
      <td>${p.aceita_convites_sistema ? 'Sim' : 'Não'}</td>
      <td>${_statusBadge(p.status)}</td>
      <td>${_contratoBadge(p)}</td>
      <td style="white-space:nowrap">
        <button class="btn-xs sec" onclick="abrirModalJogador(${p.id})">Editar</button>
        <button class="btn-xs sec" onclick="enviarContrato(${p.id})">${p.contrato_enviado_em ? 'Reenviar contrato' : 'Enviar contrato'}</button>
        ${!p.contrato_assinado ? `<button class="btn-xs sec" onclick="marcarContratoAssinado(${p.id})" title="Marcar o contrato como assinado">Marcar assinado</button>` : ''}
      </td>
    </tr>
  `).join('')
}

async function enviarContrato(playerId) {
  if (!(await confirmar('Enviar o termo de adesão?', 'O jogador recebe o contrato pelo WhatsApp, pela Autentique.', { acao: 'Enviar' }))) return
  try {
    await api(`/admin/players/${playerId}/enviar-contrato`, { method: 'POST' })
    toast('Contrato enviado')
    loadPlayers()
  } catch (err) {
    toast('Erro ao enviar contrato: ' + err.message, true)
  }
}

async function marcarContratoAssinado(playerId) {
  if (!(await confirmar('Marcar o contrato como assinado?', 'Use só quando o jogador assinou fora da Autentique. As reservas ficam liberadas na hora.', { acao: 'Marcar' }))) return
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
  document.getElementById('modal-jogador-titulo').textContent = playerId ? 'Editar jogador' : 'Criar jogador'
  document.getElementById('jog-id').value = playerId || ''
  // Limpa todos os campos. Em variável, e não começando a linha com "[": sem
  // ponto e vírgula, o JS colava o array na linha de cima — `'' [ … ]` — e o
  // forEach rodava em undefined. O "+ Criar" jogador nunca abria.
  const campos = ['jog-nome','jog-apelido','jog-email','jog-telefone','jog-senha',
    'jog-cpf','jog-nascimento','jog-rua','jog-numero','jog-complemento',
    'jog-bairro','jog-cidade','jog-cep']
  campos.forEach(id => _setVal(id, ''))
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
    // Convidado de jogo avulso não tem player_id: vale o nome que veio com ele
    .map(p => p.player_id != null ? playerNome(p.player_id) : (p.convidado_nome || 'Convidado').split(' ')[0])
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
      ? `<button class="btn-xs sec"    onclick="abrirModalPlacar(${m.id})">Placar</button>
         <button class="btn-xs sec"    onclick="abrirModalWO(${m.id})">W.O.</button>
         <button class="btn-xs danger" onclick="cancelarPartida(${m.id})">Cancelar</button>`
      : '–'
    return `
      <tr>
        <td>${m.id}</td>
        <td style="white-space:nowrap">${fmtDH(m.data_hora)}</td>
        <td style="white-space:nowrap">${m.tipo === 'simples' ? 'Simples' : 'Duplas'}${m.avulso ? ' <span class="badge e-neutro">Avulso</span>' : ''}</td>
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
  if (!(await confirmar('Cancelar a partida?', `A partida nº ${matchId} sai da agenda e o horário fica livre.`, { acao: 'Cancelar partida', perigo: true, voltar: 'Manter' }))) return
  try {
    await api(`/matches/${matchId}/cancelar`, { method: 'POST' })
    toast('Partida cancelada')
    await loadMatches()
  } catch (err) {
    toast(err.message, true)
  }
}

async function recalcularClassificacao() {
  if (!(await confirmar('Recalcular os níveis?', 'A classificação A, B, C e D de todos os jogadores é refeita a partir do rating atual.', { acao: 'Recalcular' }))) return
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
           <span>Pódio</span>
           <ol>${top3.map(r => `<li>${escHtml(r.nome)}, ${r.pontos} pontos</li>`).join('')}</ol>
         </div>`
      : ''
    const acoes = isAtiva
      ? `<button class="btn-xs danger" onclick="encerrarTemporada(${s.id})">Encerrar</button>`
      : ''
    return `
      <div class="season-card ${s.status}">
        <div class="s-header">
          <div>
            <div class="s-title">Temporada ${s.id} ${seasonBadge(s.status)}</div>
            <div class="s-dates">De ${fmtD(s.data_inicio)} a ${fmtD(s.data_fim)}</div>
          </div>
          <div>${acoes}</div>
        </div>
        ${rankHtml}
      </div>
    `
  }).join('')
}

async function encerrarTemporada(seasonId) {
  if (!(await confirmar('Encerrar a temporada?', 'O ranking final é salvo e os pontos de todos os jogadores voltam a zero. Não dá para desfazer.', { acao: 'Encerrar temporada', perigo: true }))) return
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
    toast(r.convites_enviados ? _plural(r.convites_enviados, 'convite enviado', 'convites enviados') : 'Nenhum convite enviado')
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
        const statusMap = { pendente: 'aguardando', confirmado: 'confirmou', recusado: 'recusou', expirado: 'expirou', cancelado: 'cancelado' }
        return `${playerNome(jp.player_id)} (${statusMap[jp.status] || jp.status})`
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
  pendente:     ['b-pendente',  'Aguardando'],
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
  if (diff < 0)  return `<span style="color:var(--perigo)">${Math.abs(diff)}d atrás</span>`
  if (diff <= 7) return `<span style="color:var(--aviso)">${diff}d</span>`
  return `<span style="color:var(--ok)">${diff}d</span>`
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
    <tr${s.pausa_solicitada ? ' style="background:color-mix(in srgb, var(--atencao) 9%, transparent)"' : ''}>
      <td>
        <strong>${escHtml(s.player_nome || '–')}</strong>
        <div style="font-size:0.72rem;color:var(--clr-text-muted)">${escHtml(s.player_email || '')}</div>
      </td>
      <td>${PLANO_LABEL[s.plano] || s.plano}</td>
      <td>
        ${subBadge(s.status)}
        ${s.pausa_solicitada ? '<span class="badge e-alerta" style="margin-left:4px">Pausa pedida</span>' : ''}
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

// ── Modal Nova assinatura ─────────────────────────────────────────────────────

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
    toast('Assinatura criada')
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
    btn.disabled = false; btn.textContent = 'Criar e gerar PIX'
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
    motivoEl.textContent = `Motivo: ${s.pausa_motivo}.${dias ? ` De ${dataInicio} a ${dataRetorno}, ${dias} dias.` : ''}`
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
    toast('Status atualizado')
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
        ${res.payment_link ? `<p style="margin-top:0.5rem;font-size:0.8rem"><a href="${escHtml(res.payment_link)}" target="_blank" >Abrir a cobrança</a></p>` : ''}
      `
    } else {
      body.innerHTML = '<p style="color:var(--clr-text-muted);font-size:0.85rem">Nenhum PIX pendente encontrado para este jogador.</p>'
    }
  } catch (err) {
    body.innerHTML = `<p style="color:var(--perigo);font-size:0.85rem">${escHtml(err.message)}</p>`
  }
}

function copiarPix(inputId) {
  const el = document.getElementById(inputId)
  if (!el) return
  navigator.clipboard.writeText(el.value).then(() => toast('Código PIX copiado'))
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

// ── Cupons ────────────────────────────────────────────────────────────────────

function _cupomStatus(c) {
  const agora = new Date()
  if (!c.ativo) return { txt: 'Inativo', cls: 'e-neutro' }
  if (c.validade_inicio && new Date(c.validade_inicio) > agora) return { txt: 'Agendado', cls: 'e-tint' }
  if (c.validade_fim && new Date(c.validade_fim) < agora) return { txt: 'Expirado', cls: 'e-neutro' }
  if (c.max_usos != null && c.usos >= c.max_usos) return { txt: 'Esgotado', cls: 'e-neutro' }
  return { txt: 'Ativo', cls: 'e-bom' }
}

async function loadCupons() {
  const wrap = document.getElementById('cupons-tabela-wrap')
  try {
    const cupons = await api('/admin/cupons')
    if (!cupons.length) {
      wrap.innerHTML = '<p style="color:var(--clr-text-muted);text-align:center;padding:2rem">Nenhum cupom criado ainda.</p>'
      return
    }
    const linhas = cupons.map(c => {
      const st = _cupomStatus(c)
      const usos = c.max_usos != null ? `${c.usos} / ${c.max_usos}` : `${c.usos} / ∞`
      const prazo = c.validade_fim ? `até ${fmtD(c.validade_fim)}` : 'sem prazo'
      return `<tr>
        <td><strong>${escHtml(c.codigo)}</strong>${c.descricao ? `<br><span style="font-size:.75rem;color:var(--clr-text-muted)">${escHtml(c.descricao)}</span>` : ''}</td>
        <td>${c.percentual}%</td>
        <td>${prazo}</td>
        <td>${usos}</td>
        <td><span class="badge ${st.cls}">${st.txt}</span></td>
        <td style="white-space:nowrap;text-align:right">
          <button class="btn-xs sec" onclick="toggleCupom(${c.id}, ${!c.ativo})">${c.ativo ? 'Desativar' : 'Ativar'}</button>
          <button class="btn-xs bnc" onclick="excluirCupom(${c.id}, '${escHtml(c.codigo)}')">Excluir</button>
        </td>
      </tr>`
    }).join('')
    wrap.innerHTML = `<table class="data-table" style="width:100%">
      <thead><tr><th>Código</th><th>Desconto</th><th>Prazo</th><th>Usos</th><th>Status</th><th></th></tr></thead>
      <tbody>${linhas}</tbody></table>`
  } catch (err) {
    wrap.innerHTML = `<p style="color:var(--perigo);text-align:center;padding:2rem">Erro ao carregar: ${escHtml(err.message)}</p>`
  }
}

async function criarCupom(e) {
  e.preventDefault()
  const erro = document.getElementById('cupom-erro')
  erro.style.display = 'none'
  const v = (id) => document.getElementById(id).value.trim()
  const body = {
    codigo: v('cupom-codigo').toUpperCase(),
    percentual: parseInt(v('cupom-percentual'), 10),
    descricao: v('cupom-descricao') || null,
    max_usos: v('cupom-max-usos') ? parseInt(v('cupom-max-usos'), 10) : null,
    validade_inicio: v('cupom-inicio') ? new Date(v('cupom-inicio')).toISOString() : null,
    validade_fim: v('cupom-fim') ? new Date(v('cupom-fim')).toISOString() : null,
    ativo: true,
  }
  try {
    await api('/admin/cupons', { method: 'POST', body: JSON.stringify(body) })
    document.getElementById('cupom-form').reset()
    toast('Cupom criado')
    loadCupons()
  } catch (err) {
    erro.textContent = err.message
    erro.style.display = 'block'
  }
}

async function toggleCupom(id, ativo) {
  try {
    await api(`/admin/cupons/${id}`, { method: 'PATCH', body: JSON.stringify({ ativo }) })
    loadCupons()
  } catch (err) { toast(err.message, true) }
}

async function excluirCupom(id, codigo) {
  if (!(await confirmar(`Excluir o cupom ${codigo}?`, 'Pagamentos que já o usaram não mudam.', { acao: 'Excluir', perigo: true }))) return
  try {
    await api(`/admin/cupons/${id}`, { method: 'DELETE' })
    toast('Cupom excluído')
    loadCupons()
  } catch (err) { toast(err.message, true) }
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
    document.getElementById('cfg-cancelamento').value       = cfg.cancelamento_antecedencia_horas

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
      el.textContent = `R$ ${fmtR$(total / meses)} por mês em ${meses} parcelas`
    } else {
      el.textContent = `R$ ${fmtR$(total)} à vista`
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

// ── Diagnóstico de e-mail ─────────────────────────────────────────────────────

async function loadEmailStatus() {
  const el = document.getElementById('email-status')
  if (!el) return
  try {
    const s = await api('/admin/email/status')
    if (!s.configurado) {
      el.innerHTML = `<span class="cfg-off-badge">SMTP não configurado</span>
        <div style="color:var(--tinta-2);margin-top:.4rem">
          Defina SMTP_HOST, SMTP_USER e SMTP_PASS no <code>.env</code> do servidor.
        </div>`
      return
    }
    const alias = s.usa_alias
      ? `<div style="color:var(--tinta-2);margin-top:.3rem">
           Enviando como <strong>${escHtml(s.remetente)}</strong> usando a conta
           <strong>${escHtml(s.usuario)}</strong>. O provedor precisa autorizar este alias.
         </div>`
      : ''
    el.innerHTML = `
      <div><strong>Servidor:</strong> ${escHtml(s.host)}:${s.porta}</div>
      <div><strong>Remetente:</strong> ${escHtml(s.remetente_nome)} &lt;${escHtml(s.remetente)}&gt;</div>
      <div><strong>Senha:</strong> ${s.senha_definida ? 'definida' : '<span style="color:var(--perigo)">ausente</span>'}</div>
      ${alias}`
  } catch (err) {
    el.innerHTML = `<span style="color:var(--perigo)">Erro ao ler status: ${escHtml(err.message)}</span>`
  }
}

async function testarEmail() {
  const dest = document.getElementById('email-teste-dest').value.trim()
  const out = document.getElementById('email-teste-result')
  if (!dest) { out.innerHTML = '<span style="color:var(--aviso)">Informe um e-mail de destino.</span>'; return }
  out.innerHTML = 'Enviando…'
  try {
    const r = await api('/admin/email/testar', {
      method: 'POST',
      body: JSON.stringify({ destinatario: dest }),
    })
    out.innerHTML = `<span style="color:var(--ok)">Enviado para ${escHtml(r.enviado_para)}
      como ${escHtml(r.remetente)}. Confira a caixa de entrada (e o spam).</span>`
  } catch (err) {
    out.innerHTML = `<span style="color:var(--perigo)">Não foi enviado: ${escHtml(err.message)}</span>`
  }
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
        cancelamento_antecedencia_horas: parseInt(document.getElementById('cfg-cancelamento').value, 10),
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
      ? `Configurações salvas. ${_plural(avisados, 'pessoa da lista de espera foi avisada', 'pessoas da lista de espera foram avisadas')} da abertura.`
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

// ── Locações da quadra ───────────────────────────────────────────────────────

const _LOC_METODO = { pix: 'no PIX', cartao: 'no cartão', boleto: 'no boleto' }

/** Uma etiqueta só, com a situação que importa: a reserva e o pagamento juntos */
function _locSituacao(l) {
  if (l.status === 'cancelada') return ['e-neutro', 'Cancelada']
  if (l.pagamento_status === 'pago') return ['e-bom', `Paga ${_LOC_METODO[l.pagamento_metodo] || ''}`.trim()]
  if (l.pagamento_status === 'estornado') return ['e-neutro', 'Estornada']
  if (l.pagamento_status === 'falhou') return ['e-critico', 'Pagamento falhou']
  if (l.status === 'aguardando_pagamento' || l.pagamento_status === 'pendente') return ['e-alerta', 'Aguardando pagamento']
  return ['e-tint', 'Confirmada']
}

function _locLinha(l, futura) {
  const opc = { timeZone: 'America/Sao_Paulo' }
  const ini = new Date(l.data_hora_inicio)
  const fim = new Date(l.data_hora_fim)
  const outroAno = ini.getFullYear() !== new Date().getFullYear()
  const dia = ini.toLocaleDateString('pt-BR', { ...opc, weekday: 'short', day: 'numeric', month: 'short', ...(outroAno ? { year: 'numeric' } : {}) })
  const hora = d => d.toLocaleTimeString('pt-BR', { ...opc, hour: '2-digit', minute: '2-digit' })
  const [cls, situacao] = _locSituacao(l)
  // Cancelar uma locação passada não devolve horário nenhum; só faz sentido
  // nas próximas ou numa passada que nunca foi paga
  const cancelavel = l.status !== 'cancelada' && (futura || l.pagamento_status !== 'pago')
  return `<div class="locacao-card${l.status === 'cancelada' ? ' cancelada' : ''}">
    <div class="lc-data">
      <div class="lc-dia">${escHtml(dia.charAt(0).toUpperCase() + dia.slice(1))}</div>
      <div class="lc-hora">${hora(ini)} às ${hora(fim)}</div>
    </div>
    <div class="lc-jogador">
      <div class="lc-nome">${escHtml(l.jogador_nome) || 'Sem nome'}</div>
      ${l.jogador_email ? `<div class="lc-email">${escHtml(l.jogador_email)}</div>` : ''}
    </div>
    <div class="lc-situacao"><span class="badge ${cls}">${escHtml(situacao)}</span></div>
    <div class="lc-valor">${_brl(l.valor)}</div>
    <div class="lc-actions">${cancelavel ? `<button class="btn-xs danger" onclick="cancelarLocacao(${l.id})">Cancelar</button>` : ''}</div>
  </div>`
}

async function loadLocacoes() {
  const lista = document.getElementById('lista-locacoes')
  lista.innerHTML = '<p class="empty">Carregando…</p>'
  try {
    const locacoes = await api('/admin/locacoes')
    if (!locacoes.length) {
      lista.innerHTML = '<p class="empty">Nenhuma locação ainda. Elas aparecem aqui quando alguém aluga a quadra pelo app.</p>'
      return
    }
    const agora = Date.now()
    const proximas = locacoes.filter(l => new Date(l.data_hora_fim) > agora)
      .sort((a, b) => new Date(a.data_hora_inicio) - new Date(b.data_hora_inicio))
    const anteriores = locacoes.filter(l => new Date(l.data_hora_fim) <= agora)
      .sort((a, b) => new Date(b.data_hora_inicio) - new Date(a.data_hora_inicio))
    const grupo = (titulo, itens, futura, vazio) => `
      <div class="lc-grupo">
        <div class="card-cabeca"><h3 class="card-titulo">${titulo}</h3><span class="card-nota">${itens.length || ''}</span></div>
        <div class="card lc-lista">${itens.length ? itens.map(l => _locLinha(l, futura)).join('') : `<p class="empty">${vazio}</p>`}</div>
      </div>`
    lista.innerHTML = grupo('Próximas', proximas, true, 'Nenhuma locação marcada daqui para a frente.')
      + (anteriores.length ? grupo('Anteriores', anteriores, false, '') : '')
  } catch (e) {
    lista.innerHTML = `<p class="empty" style="color:var(--critico)">Não foi possível carregar as locações: ${escHtml(e.message)}</p>`
  }
}

async function cancelarLocacao(id) {
  if (!(await confirmar('Cancelar a locação?', 'O horário volta para a agenda.', { acao: 'Cancelar locação', perigo: true, voltar: 'Manter' }))) return
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
  tbody.innerHTML = '<tr><td colspan="5" style="text-align:center;color:var(--tinta-3);padding:1rem">Carregando…</td></tr>'
  try {
    const slots = await api('/admin/slots-ranking')
    if (!slots.length) {
      tbody.innerHTML = '<tr><td colspan="5" style="text-align:center;color:var(--tinta-3);padding:1rem">Nenhum horário cadastrado.</td></tr>'
      return
    }
    tbody.innerHTML = slots.map(s => `
      <tr>
        <td>${DIAS_SEMANA[s.dia_semana] ?? s.dia_semana}</td>
        <td>${s.hora_inicio.slice(0,5)}</td>
        <td>${s.hora_fim.slice(0,5)}</td>
        <td>
          <span class="badge ${s.ativo ? 'e-bom' : 'e-neutro'}">${s.ativo ? 'Ativo' : 'Inativo'}</span>
        </td>
        <td style="display:flex;gap:.4rem">
          <button class="btn-xs" onclick='abrirModalSlotRanking(${JSON.stringify(s)})'>Editar</button>
          <button class="btn-xs" onclick="toggleSlotRanking(${s.id},${s.ativo})" title="${s.ativo ? 'Desativar' : 'Ativar'}">${s.ativo ? 'Pausar' : 'Ativar'}</button>
          <button class="btn-xs danger" onclick="deletarSlotRanking(${s.id})">Excluir</button>
        </td>
      </tr>`).join('')
  } catch {
    tbody.innerHTML = '<tr><td colspan="5" style="text-align:center;color:var(--perigo);padding:1rem">Erro ao carregar.</td></tr>'
  }
}

let _srEditId = null

function abrirModalSlotRanking(slot = null) {
  _srEditId = slot ? slot.id : null
  document.getElementById('sr-modal-titulo').textContent = slot ? 'Editar horário do ranking' : 'Adicionar horário do ranking'
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
  if (!(await confirmar(ativo ? 'Desativar este horário do ranking?' : 'Ativar este horário do ranking?', '', { acao: ativo ? 'Desativar' : 'Ativar', perigo: ativo }))) return
  try {
    await api(`/admin/slots-ranking/${id}/toggle`, { method: 'PATCH' })
    loadSlotsRanking()
  } catch { toast('Erro ao atualizar.', true) }
}

async function deletarSlotRanking(id) {
  if (!(await confirmar('Excluir este horário do ranking?', '', { acao: 'Excluir', perigo: true }))) return
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
      tbody.innerHTML = '<tr><td colspan="4" style="text-align:center;color:var(--tinta-3);padding:.75rem">Nenhum dia especial cadastrado.</td></tr>'
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
  document.getElementById('he-modal-titulo').textContent = he ? 'Editar dia especial' : 'Adicionar dia especial'
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
  if (!(await confirmar('Excluir este dia especial?', 'O dia volta ao horário normal da semana.', { acao: 'Excluir', perigo: true }))) return
  try {
    await api(`/admin/horarios-especiais/${id}`, { method: 'DELETE' })
    toast('Dia especial excluído.')
    loadHorariosEspeciais()
  } catch(e) {
    toast(e?.message || 'Erro ao excluir.', true)
  }
}

// ── Lista de Espera ───────────────────────────────────────────────────────────

function _fmtTelefone(t) {
  const d = String(t || '').replace(/\D/g, '')
  if (d.length === 11) return `(${d.slice(0, 2)}) ${d.slice(2, 7)}-${d.slice(7)}`
  if (d.length === 10) return `(${d.slice(0, 2)}) ${d.slice(2, 6)}-${d.slice(6)}`
  return t || ''
}

async function loadListaEspera() {
  const wrap = document.getElementById('le-tabela-wrap')
  const badge = document.getElementById('le-vagas-badge')
  const aviso = document.getElementById('le-aviso-vagas')
  wrap.innerHTML = '<p class="empty">Carregando…</p>'
  try {
    const r = await api('/admin/lista-espera')
    const { fila, vagas } = r

    badge.textContent = `${vagas.ocupadas} de ${vagas.limite} vagas ocupadas`

    if (vagas.disponiveis > 0 && fila.length > 0) {
      aviso.style.display = 'block'
      aviso.textContent = `${vagas.disponiveis === 1 ? 'Há 1 vaga livre' : `Há ${vagas.disponiveis} vagas livres`} e ${_plural(fila.length, 'pessoa', 'pessoas')} na fila. Convoque agora ou aguarde a convocação automática.`
    } else {
      aviso.style.display = 'none'
    }

    if (!fila.length) {
      wrap.innerHTML = '<p class="empty">Ninguém na lista de espera.</p>'
      return
    }

    const quando = iso => {
      const d = new Date(iso)
      const ano = d.getFullYear() !== new Date().getFullYear() ? { year: 'numeric' } : {}
      return d.toLocaleString('pt-BR', { timeZone: 'America/Sao_Paulo', day: '2-digit', month: '2-digit', ...ano, hour: '2-digit', minute: '2-digit' }).replace(',', ' às')
    }
    const rows = fila.map(e => {
      const convocado = e.status === 'convocado'
      return `<tr>
        <td class="le-posicao">${e.posicao}</td>
        <td>
          <strong>${escHtml(e.player_nome)}</strong>
          <div style="font-size:var(--t-nota);color:var(--tinta-2)">${escHtml(e.player_email)}</div>
        </td>
        <td style="white-space:nowrap;color:var(--tinta-2)">${escHtml(_fmtTelefone(e.player_telefone)) || '–'}</td>
        <td>
          <span class="badge ${convocado ? 'e-alerta' : 'e-neutro'}">${convocado ? 'Convocado' : 'Na fila'}</span>
          ${convocado && e.data_expiracao_convocacao ? `<div style="font-size:var(--t-nota);color:var(--tinta-2);white-space:nowrap">Confirma até ${quando(e.data_expiracao_convocacao)}</div>` : ''}
        </td>
        <td style="white-space:nowrap">${quando(e.data_inscricao)}</td>
        <td style="white-space:nowrap">
          ${e.status === 'aguardando' ? `<button class="btn-xs sec" onclick="leConvocar(${e.id})">Convocar</button>` : ''}
          <button class="btn-xs danger" onclick="leRemover(${e.id})">Remover</button>
        </td>
      </tr>`
    }).join('')

    wrap.innerHTML = `<div class="admin-table-wrap"><table class="admin-table">
      <thead><tr>
        <th>Nº</th><th>Jogador</th><th>Telefone</th>
        <th>Situação</th><th>Entrou em</th><th>Ações</th>
      </tr></thead>
      <tbody>${rows}</tbody>
    </table></div>`
  } catch (e) {
    wrap.innerHTML = `<p class="empty" style="color:var(--critico)">Não foi possível carregar a lista: ${escHtml(e.message)}</p>`
  }
}

async function leConvocar(id) {
  if (!(await confirmar('Convocar este jogador?', 'Ele recebe um e-mail e tem 48 horas para confirmar a vaga.', { acao: 'Convocar' }))) return
  try {
    await api(`/admin/lista-espera/${id}/convocar`, { method: 'POST' })
    showToast('Convocação enviada por e-mail', 'success')
    loadListaEspera()
  } catch (e) {
    showToast('Erro: ' + e.message, 'error')
  }
}

async function leRemover(id) {
  if (!(await confirmar('Remover da lista de espera?', '', { acao: 'Remover', perigo: true }))) return
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
    wrap.innerHTML = `<p style="color:var(--perigo);text-align:center;padding:2rem">Erro ao carregar: ${e.message}</p>`
  }
}

function _renderContrato() {
  const wrap = document.getElementById('contrato-clausulas-wrap')
  if (!_contratoClausulas.length) {
    wrap.innerHTML = '<p style="color:var(--clr-text-muted);text-align:center;padding:2rem">Nenhuma cláusula cadastrada. Clique em "+ Adicionar cláusula".</p>'
    return
  }
  wrap.innerHTML = _contratoClausulas.map((c, i) => `
    <div class="contrato-clausula-card" data-idx="${i}">
      <div class="ct-cabeca">
        <input class="ct-titulo" value="${_escHtml(c.titulo)}" placeholder="Título da cláusula" aria-label="Título da cláusula ${i + 1}">
        <label class="form-check"><input type="checkbox" class="ct-ativo" ${c.ativo ? 'checked' : ''}> Ativa</label>
        <div class="ct-acoes">
          <button class="btn-xs sec" onclick="contratoMover(${i},-1)" title="Subir" aria-label="Subir a cláusula" ${i === 0 ? 'disabled' : ''}><svg viewBox="0 0 24 24" width="13" height="13" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M6 15l6-6 6 6"/></svg></button>
          <button class="btn-xs sec" onclick="contratoMover(${i},1)" title="Descer" aria-label="Descer a cláusula" ${i === _contratoClausulas.length - 1 ? 'disabled' : ''}><svg viewBox="0 0 24 24" width="13" height="13" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M6 9l6 6 6-6"/></svg></button>
          <button class="btn-xs danger" onclick="contratoRemover(${i})">Remover</button>
        </div>
      </div>
      <textarea class="ct-texto" rows="5" placeholder="Texto da cláusula" aria-label="Texto da cláusula ${i + 1}">${_escHtml(c.texto)}</textarea>
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

async function contratoRemover(idx) {
  if (!(await confirmar('Remover esta cláusula?', '', { acao: 'Remover', perigo: true }))) return
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
    showToast(`Contrato salvo com ${_plural(r.total, 'cláusula', 'cláusulas')}`, 'success')
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



// ── Acesso à quadra ──────────────────────────────────────────────────────────
//
// O servidor não fala com os leitores: quem faz isso é o agente instalado na
// quadra. Esta tela configura o estado desejado e mostra a saúde da ponte.

function fecharModal(id) {
  document.getElementById(id).classList.remove('open')
}

async function loadAcesso() {
  await Promise.all([
    loadAcessoConfig(),
    loadAcessoDispositivos(),
    loadAcessoCredenciais(),
    loadAcessoEventos(),
  ])
}

async function loadAcessoConfig() {
  try {
    const c = await api('/admin/acesso/configuracoes')
    document.getElementById('acesso-ativo').checked = c.acesso_ativo
    document.getElementById('acesso-exige-selfie').checked = c.acesso_exige_selfie
    document.getElementById('acesso-antes').value = c.acesso_minutos_antes
    document.getElementById('acesso-depois').value = c.acesso_minutos_depois
    document.getElementById('acesso-token').value = c.agente_token || ''

    // Agente "online" = reportou há menos de 2 min. O ciclo dele é de 20 s,
    // então essa folga cobre um ciclo perdido sem alarme falso.
    const badge = document.getElementById('acesso-agente-status')
    if (!c.agente_visto_em) {
      badge.className = 'badge bnc'
      badge.textContent = 'Agente nunca conectou'
    } else {
      const atrasoMin = (Date.now() - new Date(c.agente_visto_em)) / 60000
      const online = atrasoMin < 2
      badge.className = online ? 'badge ba' : 'badge bc'
      badge.textContent = online ? 'Agente conectado' : `Agente sem contato desde ${fmtDH(c.agente_visto_em)}`
    }
  } catch (err) {
    showErr('acesso-cfg-erro', err.message)
  }
}

async function salvarAcessoConfig() {
  try {
    const r = await api('/admin/acesso/configuracoes', {
      method: 'PUT',
      body: JSON.stringify({
        acesso_ativo: document.getElementById('acesso-ativo').checked,
        acesso_exige_selfie: document.getElementById('acesso-exige-selfie').checked,
        acesso_minutos_antes: Number(document.getElementById('acesso-antes').value),
        acesso_minutos_depois: Number(document.getElementById('acesso-depois').value),
      }),
    })
    document.getElementById('acesso-cfg-erro').style.display = 'none'
    toast(r.janelas_criadas
      ? `Regras salvas. ${_plural(r.janelas_criadas, 'liberação criada', 'liberações criadas')} para reservas já marcadas.`
      : 'Regras salvas.')
    loadAcessoCredenciais()
  } catch (err) {
    showErr('acesso-cfg-erro', err.message)
  }
}

async function gerarTokenAgente() {
  if (!(await confirmar('Gerar um token novo?', 'O agente da quadra para de funcionar até você atualizar a configuração dele com o token novo.', { acao: 'Gerar token', perigo: true }))) return
  try {
    const r = await api('/admin/acesso/token', { method: 'POST' })
    document.getElementById('acesso-token').value = r.agente_token
    toast('Token gerado. Atualize a configuração do agente na quadra.')
  } catch (err) {
    toast(err.message, true)
  }
}

function copiarTokenAgente() {
  const campo = document.getElementById('acesso-token')
  if (!campo.value) return toast('Nenhum token gerado ainda.', true)
  navigator.clipboard.writeText(campo.value)
    .then(() => toast('Token copiado.'))
    .catch(() => toast('Não consegui copiar; selecione e copie à mão.', true))
}

async function loadAcessoDispositivos() {
  const corpo = document.getElementById('acesso-dispositivos')
  try {
    const linhas = await api('/admin/acesso/dispositivos')
    if (!linhas.length) {
      corpo.innerHTML = '<tr><td colspan="6" class="empty">Nenhum leitor cadastrado.</td></tr>'
      return
    }
    corpo.innerHTML = linhas.map(d => {
      let estado = '<span class="badge bnc">sem contato</span>'
      if (d.ultimo_erro) estado = '<span class="badge b-wo">erro</span>'
      else if (d.ultimo_contato_em) estado = '<span class="badge ba">ok</span>'
      if (!d.ativo) estado = '<span class="badge bd">inativo</span>'
      return `<tr>
        <td>${escHtml(d.nome)}</td>
        <td>${d.papel === 'entrada' ? 'Entrada' : 'Saída'}</td>
        <td>${escHtml(d.host)}:${d.porta}</td>
        <td>${estado}${d.ultimo_erro ? `<div class="cfg-hint">${escHtml(d.ultimo_erro)}</div>` : ''}</td>
        <td>${d.ultimo_contato_em ? fmtDH(d.ultimo_contato_em) : '—'}</td>
        <td>
          <button class="btn-xs sec" onclick='abrirModalDispositivo(${JSON.stringify(d)})'>Editar</button>
          <button class="btn-xs warn" onclick="abrirPortao(${d.id})">Abrir</button>
          <button class="btn-xs danger" onclick="excluirDispositivo(${d.id})">Excluir</button>
        </td>
      </tr>`
    }).join('')
  } catch (err) {
    corpo.innerHTML = `<tr><td colspan="6" class="empty">${escHtml(err.message)}</td></tr>`
  }
}

function abrirModalDispositivo(d = null) {
  document.getElementById('modal-dispositivo-titulo').textContent = d ? 'Editar leitor' : 'Novo leitor'
  document.getElementById('disp-id').value      = d ? d.id : ''
  document.getElementById('disp-nome').value    = d ? d.nome : ''
  document.getElementById('disp-papel').value   = d ? d.papel : 'entrada'
  document.getElementById('disp-host').value    = d ? d.host : ''
  document.getElementById('disp-porta').value   = d ? d.porta : 80
  document.getElementById('disp-usuario').value = d ? d.usuario : 'admin'
  document.getElementById('disp-modelo').value  = d ? d.modelo : 'SS 3531 MF LITE'
  document.getElementById('disp-ativo').checked = d ? d.ativo : true
  // Sempre vazio: o painel nunca recebe a senha de volta. Em branco, mantém.
  document.getElementById('disp-senha').value = ''
  document.getElementById('disp-erro').style.display = 'none'
  document.getElementById('modal-dispositivo').classList.add('open')
}

async function salvarDispositivo() {
  const id = document.getElementById('disp-id').value
  const corpo = {
    nome:    document.getElementById('disp-nome').value.trim(),
    papel:   document.getElementById('disp-papel').value,
    modelo:  document.getElementById('disp-modelo').value.trim(),
    host:    document.getElementById('disp-host').value.trim(),
    porta:   Number(document.getElementById('disp-porta').value),
    usuario: document.getElementById('disp-usuario').value.trim(),
    senha:   document.getElementById('disp-senha').value,
    ativo:   document.getElementById('disp-ativo').checked,
  }
  if (!corpo.nome || !corpo.host) {
    return showErr('disp-erro', 'Nome e endereço IP são obrigatórios.')
  }
  if (!id && !corpo.senha) {
    return showErr('disp-erro', 'Informe a senha do leitor.')
  }
  try {
    await api(id ? `/admin/acesso/dispositivos/${id}` : '/admin/acesso/dispositivos', {
      method: id ? 'PATCH' : 'POST',
      body: JSON.stringify(corpo),
    })
    fecharModal('modal-dispositivo')
    toast('Leitor salvo.')
    loadAcessoDispositivos()
  } catch (err) {
    showErr('disp-erro', err.message)
  }
}

async function excluirDispositivo(id) {
  if (!(await confirmar('Excluir este leitor?', 'O agente da quadra deixa de sincronizá-lo.', { acao: 'Excluir', perigo: true }))) return
  try {
    await api(`/admin/acesso/dispositivos/${id}`, { method: 'DELETE' })
    toast('Leitor excluído.')
    loadAcessoDispositivos()
  } catch (err) {
    toast(err.message, true)
  }
}

async function abrirPortao(id) {
  if (!(await confirmar('Abrir o portão agora?', 'Ele abre em alguns segundos, quando o agente da quadra receber o comando.', { acao: 'Abrir' }))) return
  try {
    await api(`/admin/acesso/dispositivos/${id}/abrir`, { method: 'POST' })
    // A abertura entra numa fila: o servidor não alcança o leitor, quem
    // executa é o agente no próximo ciclo.
    toast('Comando enviado. O portão abre em alguns segundos.')
  } catch (err) {
    toast(err.message, true)
  }
}

async function loadAcessoCredenciais() {
  const corpo = document.getElementById('acesso-credenciais')
  const soPendentes = document.getElementById('acesso-so-pendentes').checked
  const rotulo = {
    pendente_foto:  '<span class="badge bc">falta selfie</span>',
    pendente_envio: '<span class="badge bb">aguardando o agente</span>',
    sincronizada:   '<span class="badge ba">liberada</span>',
    erro:           '<span class="badge b-wo">erro</span>',
    removida:       '<span class="badge bd">removida</span>',
  }
  try {
    const linhas = await api(`/admin/acesso/credenciais?apenas_pendentes=${soPendentes}`)
    if (!linhas.length) {
      corpo.innerHTML = `<tr><td colspan="6" class="empty">${soPendentes ? 'Ninguém pendente.' : 'Ninguém cadastrado no portão ainda.'}</td></tr>`
      return
    }
    corpo.innerHTML = linhas.map(c => `<tr>
      <td>${escHtml(c.nome)}</td>
      <td>${escHtml(c.origem)}</td>
      <td>${escHtml(c.id_dispositivo)}</td>
      <td>${rotulo[c.status] || escHtml(c.status)}${c.erro ? `<div class="cfg-hint">${escHtml(c.erro)}</div>` : ''}</td>
      <td>${c.proxima_janela ? fmtDH(c.proxima_janela) : '—'}</td>
      <td>${c.link_selfie
            ? `<button class="btn-xs sec" onclick="copiarLinkSelfie('${escHtml(c.link_selfie)}')">Copiar link</button>`
            : (c.tem_foto ? 'do perfil' : '—')}</td>
    </tr>`).join('')
  } catch (err) {
    corpo.innerHTML = `<tr><td colspan="6" class="empty">${escHtml(err.message)}</td></tr>`
  }
}

function copiarLinkSelfie(caminho) {
  const url = location.origin + caminho
  navigator.clipboard.writeText(url)
    .then(() => toast('Link copiado. Envie para a pessoa enviar a selfie.'))
    .catch(() => prompt('Copie o link:', url))
}

async function loadAcessoEventos() {
  const corpo = document.getElementById('acesso-eventos')
  const rotulo = {
    entrada:         '<span class="badge ba">entrada</span>',
    saida:           '<span class="badge bb">saída</span>',
    negado:          '<span class="badge b-wo">negado</span>',
    abertura_remota: '<span class="badge bc">abertura pelo painel</span>',
  }
  try {
    const linhas = await api('/admin/acesso/eventos?limite=100')
    if (!linhas.length) {
      corpo.innerHTML = '<tr><td colspan="5" class="empty">Nenhuma passagem registrada.</td></tr>'
      return
    }
    corpo.innerHTML = linhas.map(e => `<tr>
      <td>${fmtDH(e.momento)}</td>
      <td>${escHtml(e.pessoa)}</td>
      <td>${escHtml(e.leitor || '—')}</td>
      <td>${rotulo[e.tipo] || escHtml(e.tipo)}</td>
      <td>${escHtml(e.motivo || '')}</td>
    </tr>`).join('')
  } catch (err) {
    corpo.innerHTML = `<tr><td colspan="5" class="empty">${escHtml(err.message)}</td></tr>`
  }
}

document.addEventListener('keydown', e => {
  if ((e.key === 'Enter' || e.key === ' ') && e.target.matches?.('[role="button"][onclick]')) {
    e.preventDefault()
    e.target.click()
  }
})

// ── Barra de ferramentas que encolhe ao rolar ────────────────────────────────
// O título grande da tela encolhe e a barra ganha o material quando o
// conteúdo passa por baixo dela — o título grande da Apple, no Mac.
document.querySelector('.admin-main')?.addEventListener('scroll', e => {
  e.currentTarget.classList.toggle('rolada', e.currentTarget.scrollTop > 12)
}, { passive: true })

// ── Financeiro ───────────────────────────────────────────────────────────────
// O dinheiro do clube com a linguagem do Apple Card: o recebido em destaque,
// de onde veio numa barra só, a atividade do ano e as transações agrupadas
// por dia. Regras de data e fuso: app/services/financeiro_service.py.

const _fin = { ano: null, mes: null, filtro: 'todos', busca: '', transacoes: [] }
const _FIN_CAT = {
  plano:   { rotulo: 'Planos',         icone: '<path d="M4 7h16v12H4z"/><path d="M4 11h16"/><path d="M8 3v4M16 3v4"/>' },
  locacao: { rotulo: 'Locações',       icone: '<rect x="3" y="6" width="18" height="12" rx="1.5"/><path d="M12 6v12M3 9h18M3 15h18"/>' },
  avulso:  { rotulo: 'Jogos avulsos',  icone: '<circle cx="12" cy="12" r="8"/><path d="M6.6 6.4c2.2 1.5 3.4 3.3 3.4 5.6s-1.2 4.1-3.4 5.6M17.4 6.4c-2.2 1.5-3.4 3.3-3.4 5.6s1.2 4.1 3.4 5.6"/>' },
  outro:   { rotulo: 'Outros',         icone: '<circle cx="12" cy="12" r="8"/><path d="M12 8v8M8 12h8"/>' },
}
const _FIN_METODO = { pix: 'PIX', cartao: 'Cartão', boleto: 'Boleto' }
const _FIN_STATUS = {
  pago:      '',
  pendente:  '<span class="badge e-alerta">Pendente</span>',
  estornado: '<span class="badge e-neutro">Estornado</span>',
  falhou:    '<span class="badge e-critico">Não pago</span>',
}

const _brl = v => Number(v || 0).toLocaleString('pt-BR', { style: 'currency', currency: 'BRL' })
/** Valor com os centavos menores, como os saldos do Apple Card */
function _brlDestaque(v) {
  const [inteiro, centavos] = _brl(v).split(',')
  return `${escHtml(inteiro)}<span class="centavos">,${escHtml(centavos)}</span>`
}
const _iconeCat = (cat, extra = '') => `<span class="transacao-icone cat-${cat}${extra}">`
  + `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">${(_FIN_CAT[cat] || _FIN_CAT.outro).icone}</svg></span>`

function _finRotuloMes(ano, mes) {
  const t = new Date(ano, mes - 1, 1).toLocaleDateString('pt-BR', { month: 'long', year: 'numeric' })
  return t.charAt(0).toUpperCase() + t.slice(1)
}

async function loadFinanceiro() {
  if (!_fin.ano) {
    const hoje = new Date(new Date().toLocaleString('en-US', { timeZone: 'America/Sao_Paulo' }))
    _fin.ano = hoje.getFullYear()
    _fin.mes = hoje.getMonth() + 1
  }
  document.getElementById('fin-mes-rotulo').textContent = _finRotuloMes(_fin.ano, _fin.mes)
  const agora = new Date()
  const ehAtual = _fin.ano === agora.getFullYear() && _fin.mes === agora.getMonth() + 1
  document.getElementById('fin-proximo').disabled = ehAtual
  await Promise.all([_finCarregarResumo(), _finCarregarTransacoes()])
}

function finMudarMes(delta) {
  let m = _fin.mes + delta, a = _fin.ano
  if (m < 1) { m = 12; a-- }
  if (m > 12) { m = 1; a++ }
  _fin.ano = a
  _fin.mes = m
  loadFinanceiro()
}

async function _finCarregarResumo() {
  try {
    const r = await api(`/admin/financeiro/resumo?ano=${_fin.ano}&mes=${_fin.mes}`)

    document.getElementById('fin-recebido').innerHTML = _brlDestaque(r.recebido)
    const ant = r.recebido_mes_anterior
    let variacao = ''
    if (ant > 0) {
      const pct = Math.round(((r.recebido - ant) / ant) * 100)
      const sobe = pct >= 0
      const base = r.em_andamento ? 'ao mesmo período do mês anterior' : 'ao mês anterior'
      variacao = `<span class="fin-variacao ${sobe ? 'sobe' : 'desce'}">${sobe ? '▲' : '▼'} ${Math.abs(pct)}%</span> em relação ${base}. `
    }
    document.getElementById('fin-recebido-detalhe').innerHTML =
      `${variacao}${r.pagamentos} ${r.pagamentos === 1 ? 'pagamento' : 'pagamentos'}`
      + (r.descontos ? `, ${_brl(r.descontos)} em cupons` : '') + '.'

    document.getElementById('fin-areceber').innerHTML = _brlDestaque(r.a_receber)
    document.getElementById('fin-areceber-detalhe').textContent = r.pendentes
      ? `${r.pendentes} ${r.pendentes === 1 ? 'cobrança aberta' : 'cobranças abertas'}, de qualquer mês.`
      : 'Nenhuma cobrança aberta.'

    document.getElementById('fin-atraso').innerHTML = _brlDestaque(r.em_atraso)
    document.getElementById('fin-card-atraso').classList.toggle('atraso', r.em_atraso > 0)
    document.getElementById('fin-atraso-detalhe').textContent = r.atrasados
      ? `${r.atrasados} ${r.atrasados === 1 ? 'cobrança passou' : 'cobranças passaram'} da data.`
      : 'Nada vencido.'

    // De onde veio: uma barra só, segmentos proporcionais
    const total = Object.values(r.composicao).reduce((a, b) => a + b, 0)
    const cats = ['plano', 'locacao', 'avulso']
    const barra = document.getElementById('fin-barra')
    barra.innerHTML = total
      ? cats.filter(c => r.composicao[c] > 0)
          .map(c => `<span class="cat-${c}" style="flex-grow:${r.composicao[c]}" title="${_FIN_CAT[c].rotulo}: ${_brl(r.composicao[c])}"></span>`).join('')
      : ''
    barra.setAttribute('aria-label', total
      ? cats.map(c => `${_FIN_CAT[c].rotulo} ${_brl(r.composicao[c])}`).join(', ')
      : 'Nada recebido no mês')
    document.getElementById('fin-legenda').innerHTML = cats.map(c => `
      <div class="fin-legenda-linha">
        <span class="fin-ponto cat-${c}"></span>
        <span>${_FIN_CAT[c].rotulo}</span>
        <span class="fin-legenda-valor">${_brl(r.composicao[c])}</span>
        <span class="fin-legenda-pct">${total ? Math.round((r.composicao[c] / total) * 100) : 0}%</span>
      </div>`).join('')
    const pix = r.por_metodo.pix || 0
    document.getElementById('fin-composicao-nota').textContent = total
      ? `${Math.round((pix / total) * 100)}% via PIX`
      : ''

    // Atividade: doze barras, o mês escolhido no tint
    const max = Math.max(...r.serie.map(s => s.recebido), 1)
    document.getElementById('fin-grafico').innerHTML = r.serie.map(s => {
      const atual = s.ano === _fin.ano && s.mes === _fin.mes
      const curto = new Date(s.ano, s.mes - 1, 1).toLocaleDateString('pt-BR', { month: 'short' }).replace('.', '')
      const h = Math.max(2, Math.round((s.recebido / max) * 100))
      return `<button type="button" class="fin-coluna${atual ? ' atual' : ''}" onclick="finIrPara(${s.ano}, ${s.mes})"
                title="${_finRotuloMes(s.ano, s.mes)}: ${_brl(s.recebido)}" aria-label="${_finRotuloMes(s.ano, s.mes)}, ${_brl(s.recebido)}">
                <span class="fin-pilar" style="height:${h}%"></span>
                <span class="fin-mes-curto">${curto}</span>
              </button>`
    }).join('')
  } catch (e) {
    toast(e.message, true)
  }
}

function finIrPara(ano, mes) {
  _fin.ano = ano
  _fin.mes = mes
  loadFinanceiro()
}

async function _finCarregarTransacoes() {
  const lista = document.getElementById('fin-lista')
  try {
    const q = new URLSearchParams({ ano: _fin.ano, mes: _fin.mes, filtro: _fin.filtro, busca: _fin.busca })
    _fin.transacoes = await api(`/admin/financeiro/transacoes?${q}`)
    _finRenderTransacoes()
  } catch (e) {
    lista.innerHTML = `<p class="empty">${escHtml(e.message)}</p>`
  }
}

function _finRenderTransacoes() {
  const lista = document.getElementById('fin-lista')
  const itens = _fin.transacoes
  document.getElementById('fin-contagem').textContent =
    itens.length ? `${itens.length} ${itens.length === 1 ? 'transação' : 'transações'}` : ''
  if (!itens.length) {
    const vazio = {
      todos: 'Nenhuma transação neste mês.',
      recebidos: 'Nada recebido neste mês.',
      pendentes: 'Nenhuma cobrança em aberto.',
      estornos: 'Nenhum estorno ou cobrança não paga neste mês.',
    }[_fin.filtro]
    lista.innerHTML = `<p class="empty">${_fin.busca ? 'Nada encontrado para essa busca.' : vazio}</p>`
    return
  }

  // Agrupadas por dia, como no Wallet: Hoje, Ontem, depois o dia por extenso
  const fuso = { timeZone: 'America/Sao_Paulo' }
  const chave = d => new Date(d).toLocaleDateString('sv-SE', fuso)
  const hoje = chave(new Date())
  const ontem = chave(new Date(Date.now() - 86400000))
  const rotuloDia = d => {
    const k = chave(d)
    if (k === hoje) return 'Hoje'
    if (k === ontem) return 'Ontem'
    const t = new Date(d).toLocaleDateString('pt-BR', { ...fuso, weekday: 'long', day: 'numeric', month: 'long' })
    return t.charAt(0).toUpperCase() + t.slice(1)
  }

  let html = ''
  let diaAtual = null
  for (const t of itens) {
    const k = chave(t.data)
    if (k !== diaAtual) {
      diaAtual = k
      html += `<div class="fin-dia">${escHtml(rotuloDia(t.data))}</div>`
    }
    const hora = new Date(t.data).toLocaleTimeString('pt-BR', { ...fuso, hour: '2-digit', minute: '2-digit' })
    const sub = t.status === 'pago'
      ? `${_FIN_METODO[t.metodo] || t.metodo}, ${hora}`
      : (t.status === 'pendente' ? `${_FIN_METODO[t.metodo] || t.metodo}, aguardando` : _FIN_METODO[t.metodo] || t.metodo)
    html += `
      <button type="button" class="transacao" onclick="abrirTransacao(${t.id})">
        ${_iconeCat(t.categoria)}
        <span>
          <span class="transacao-titulo">${escHtml(t.pessoa || t.titulo)}</span>
          <span class="transacao-sub">${escHtml(t.titulo)}, ${escHtml(sub)}</span>
        </span>
        <span class="transacao-direita">
          <span class="transacao-valor${t.status === 'estornado' || t.status === 'falhou' ? ' riscado' : ''}">${_brl(t.valor)}</span>
          ${_FIN_STATUS[t.status] || ''}
        </span>
      </button>`
  }
  lista.innerHTML = html
}

function finFiltrar(filtro) {
  _fin.filtro = filtro
  document.querySelectorAll('#fin-filtro button').forEach(b =>
    b.setAttribute('aria-pressed', b.dataset.filtro === filtro ? 'true' : 'false'))
  _finCarregarTransacoes()
}

let _finBuscaTimer = null
function finBuscar() {
  clearTimeout(_finBuscaTimer)
  _finBuscaTimer = setTimeout(() => {
    _fin.busca = document.getElementById('fin-busca').value.trim()
    _finCarregarTransacoes()
  }, 250)
}

/** Detalhe de uma transação, como no Wallet: o valor grande no topo. */
function abrirTransacao(id) {
  const t = _fin.transacoes.find(x => x.id === id)
  if (!t) return
  const fuso = { timeZone: 'America/Sao_Paulo' }
  const quando = d => new Date(d).toLocaleString('pt-BR', { ...fuso, day: 'numeric', month: 'long', year: 'numeric', hour: '2-digit', minute: '2-digit' })
  const situacao = { pago: 'Pago', pendente: 'Aguardando pagamento', estornado: 'Estornado', falhou: 'Não pago' }[t.status] || t.status
  const linha = (rotulo, valor) => valor ? `<div><dt>${rotulo}</dt><dd>${valor}</dd></div>` : ''
  document.getElementById('transacao-titulo').textContent = t.titulo
  document.getElementById('transacao-corpo').innerHTML = `
    <div class="fin-detalhe-topo">
      ${_iconeCat(t.categoria)}
      <div class="fin-detalhe-valor${t.status === 'estornado' || t.status === 'falhou' ? ' transacao-valor riscado' : ''}">${_brlDestaque(t.valor)}</div>
      <p class="fin-detalhe-pessoa">${escHtml(t.pessoa || '—')}</p>
    </div>
    <dl class="lista-dados">
      ${linha('Situação', escHtml(situacao))}
      ${linha('Forma de pagamento', escHtml(_FIN_METODO[t.metodo] || t.metodo))}
      ${linha(t.pago_em ? 'Pago em' : 'Referente a', escHtml(quando(t.pago_em || t.data)))}
      ${linha('Cupom', t.cupom ? escHtml(t.cupom) : '')}
      ${linha('Desconto', t.desconto ? escHtml(_brl(t.desconto)) : '')}
      ${linha('Código', `nº ${t.id}`)}
    </dl>`
  document.getElementById('modal-transacao').classList.add('open')
}

// ── Boot ──────────────────────────────────────────────────────────────────────

init()
initSidebar()
