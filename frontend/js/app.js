const API = "/api/v1";

// ── Tokens ──────────────────────────────────────────────────────────────────
const Auth = {
  getAccess:   () => localStorage.getItem("access_token"),
  getRefresh:  () => localStorage.getItem("refresh_token"),
  save(tokens) {
    localStorage.setItem("access_token",  tokens.access_token);
    localStorage.setItem("refresh_token", tokens.refresh_token);
  },
  clear() {
    localStorage.removeItem("access_token");
    localStorage.removeItem("refresh_token");
  },
  isLoggedIn: () => !!localStorage.getItem("access_token"),
};

// ── API fetch com auto-refresh ───────────────────────────────────────────────
async function apiFetch(path, options = {}) {
  const headers = {
    "Content-Type": "application/json",
    ...options.headers,
  };
  if (Auth.getAccess()) headers["Authorization"] = `Bearer ${Auth.getAccess()}`;

  let res = await fetch(API + path, { ...options, headers });

  if (res.status === 401 && Auth.getRefresh()) {
    // Tenta renovar o token
    const r = await fetch(API + "/auth/refresh", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ refresh_token: Auth.getRefresh() }),
    });
    if (r.ok) {
      Auth.save(await r.json());
      headers["Authorization"] = `Bearer ${Auth.getAccess()}`;
      res = await fetch(API + path, { ...options, headers });
    } else {
      Auth.clear();
      showLogin();
      return null;
    }
  }

  if (!res.ok) {
    const body = await res.json().catch(() => ({}));
    throw new Error(body.detail || `Erro ${res.status}`);
  }
  return res.json();
}

// ── Roteamento SPA ───────────────────────────────────────────────────────────
const telas    = document.querySelectorAll(".tela");
const navLinks = document.querySelectorAll(".nav-bottom a");

function mostrarTela(id) {
  telas.forEach((t) => t.classList.toggle("ativa", t.id === id));
  navLinks.forEach((a) => a.classList.toggle("ativo", a.dataset.tela === id));
  if (id === "tela-ranking")  carregarRanking();
  if (id === "tela-perfil")   carregarPerfil();
  if (id === "tela-partidas") carregarPartidas();
  if (id === "tela-agendar")  carregarUsoSemanal();
  if (id === "tela-locacao")  locInit();
}

navLinks.forEach((a) => {
  a.addEventListener("click", (e) => {
    e.preventDefault();
    mostrarTela(a.dataset.tela);
  });
});

// ── Mostrar / ocultar app vs login ──────────────────────────────────────────
function showApp() {
  document.getElementById("tela-login").hidden = true;
  document.getElementById("app").hidden = false;
  mostrarTela("tela-ranking");
}

function showLogin() {
  document.getElementById("tela-login").hidden = false;
  document.getElementById("app").hidden = true;
}

// ── Login ────────────────────────────────────────────────────────────────────
document.getElementById("form-login").addEventListener("submit", async (e) => {
  e.preventDefault();
  const erroEl = document.getElementById("login-erro");
  const btn    = e.target.querySelector("button[type=submit]");
  erroEl.hidden = true;
  btn.disabled  = true;
  btn.textContent = "Entrando…";

  try {
    const res = await fetch(API + "/auth/login", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        email: document.getElementById("inp-email").value,
        senha: document.getElementById("inp-senha").value,
      }),
    });

    if (!res.ok) {
      const data = await res.json().catch(() => ({}));
      throw new Error(data.detail || "Erro ao entrar");
    }

    Auth.save(await res.json());
    showApp();
  } catch (err) {
    erroEl.textContent = err.message;
    erroEl.hidden = false;
  } finally {
    btn.disabled    = false;
    btn.textContent = "Entrar";
  }
});

// ── Logout ───────────────────────────────────────────────────────────────────
document.getElementById("btn-logout").addEventListener("click", () => {
  Auth.clear();
  showLogin();
});

// ── Avatar helper ─────────────────────────────────────────────────────────────
function avatarHtml(jogador, extraClass = "") {
  const iniciais = jogador.nome.trim().split(/\s+/).filter(Boolean)
    .slice(0, 2).map(n => n[0].toUpperCase()).join("");
  if (jogador.foto_url) {
    return `<div class="avatar${extraClass}"><img src="${jogador.foto_url}" alt="${jogador.nome}" loading="lazy" /></div>`;
  }
  return `<div class="avatar${extraClass}">${iniciais}</div>`;
}

// ── Upload de foto ────────────────────────────────────────────────────────────
async function uploadFoto(file) {
  const fd = new FormData();
  fd.append("foto", file);
  const res = await fetch(`${API}/players/me/foto`, {
    method: "PUT",
    headers: { Authorization: `Bearer ${Auth.getAccess()}` },
    body: fd,
  });
  if (!res.ok) {
    const body = await res.json().catch(() => ({}));
    throw new Error(body.detail || "Erro ao enviar foto");
  }
  return res.json();
}

// ── Ranking ──────────────────────────────────────────────────────────────────
function _fmtDataTemporada(iso) {
  return new Date(iso).toLocaleDateString("pt-BR", { day: "2-digit", month: "2-digit", year: "numeric", timeZone: "UTC" });
}

async function carregarRanking() {
  const lista    = document.getElementById("lista-ranking");
  const infoEl   = document.getElementById("ranking-temporada-info");
  const anterEl  = document.getElementById("ranking-anteriores");
  lista.innerHTML = "<p style='opacity:.5;font-size:.85rem'>Carregando…</p>";

  try {
    const [jogadores, temporadas] = await Promise.all([
      apiFetch("/players"),
      fetch("/api/v1/public/temporadas").then(r => r.ok ? r.json() : null).catch(() => null),
    ]);

    // ── Info da temporada ativa ──
    if (infoEl) {
      if (temporadas?.ativa) {
        const { data_inicio, data_fim } = temporadas.ativa;
        infoEl.innerHTML = `<p style="font-size:.78rem;opacity:.55;margin-bottom:.1rem">
          ${_fmtDataTemporada(data_inicio)} – ${_fmtDataTemporada(data_fim)}
        </p>`;
      } else {
        infoEl.innerHTML = "";
      }
    }

    // ── Classificação atual ──
    if (!jogadores?.length) {
      lista.innerHTML = "<p style='opacity:.5;font-size:.85rem'>Nenhum jogador cadastrado ainda.</p>";
    } else {
      lista.innerHTML = jogadores
        .map((j, i) => `
          <div class="ranking-item">
            <span class="ranking-pos">${i + 1}</span>
            ${avatarHtml(j)}
            <span style="flex:1">${j.apelido || j.nome}${j.status === "inativo" ? ' <span style="font-size:.65rem;background:rgba(200,80,30,.25);color:#e08050;padding:.1rem .35rem;border-radius:20px;vertical-align:middle">inativo</span>' : ""}</span>
            <span class="ranking-pts">${j.pontos_ranking_temporada_atual} pts</span>
          </div>`)
        .join("");
    }

    // ── Temporadas anteriores ──
    if (anterEl) {
      const encerradas = temporadas?.encerradas?.filter(s => s.top2?.length) ?? [];
      if (encerradas.length) {
        anterEl.innerHTML = encerradas.map(s => `
          <div class="card" style="margin-top:.75rem">
            <p class="card-titulo" style="margin-bottom:.35rem">Temporada anterior</p>
            <p style="font-size:.72rem;opacity:.5;margin-bottom:.65rem">${_fmtDataTemporada(s.data_inicio)} – ${_fmtDataTemporada(s.data_fim)}</p>
            ${s.top2.map(p => `
              <div class="ranking-item">
                <span class="ranking-pos">${p.posicao}º</span>
                <span style="flex:1">${p.nome}</span>
                <span class="ranking-pts">${p.pontos} pts</span>
              </div>`).join("")}
          </div>`).join("");
      } else {
        anterEl.innerHTML = "";
      }
    }
  } catch {
    lista.innerHTML = "<p style='color:var(--cor-erro)'>Erro ao carregar ranking.</p>";
  }
}

// ── Endereço helpers ─────────────────────────────────────────────────────────
function _temEndereco(p) {
  return !!(p.rua || p.cidade || p.bairro || p.cep);
}

function _enderecoHtml(p) {
  if (!_temEndereco(p)) return "";
  const linha1 = [p.rua, p.numero, p.complemento].filter(Boolean).join(", ");
  const linha2 = [p.bairro, p.cidade, p.estado].filter(Boolean).join(" — ");
  const linha3 = [p.cep, p.pais].filter(Boolean).join(" · ");
  return `
    <p class="perfil-secao-label">Endereço</p>
    ${linha1 ? `<div class="perfil-linha"><span class="perfil-label">Logradouro</span><span>${linha1}</span></div>` : ""}
    ${linha2 ? `<div class="perfil-linha"><span class="perfil-label">Bairro / Cidade</span><span>${linha2}</span></div>` : ""}
    ${linha3 ? `<div class="perfil-linha" style="border:none"><span class="perfil-label">CEP / País</span><span>${linha3}</span></div>` : ""}`;
}

// ── Perfil ───────────────────────────────────────────────────────────────────
const PLANO_LABEL = { mensal: "Mensal", trimestral: "Trimestral", semestral: "Semestral", anual: "Anual" };
const PLANO_MESES = { mensal: 30, trimestral: 90, semestral: 180, anual: 365 };
const STATUS_SUB = {
  pendente:     { cor: "#e0a040", icone: "⏳", label: "Aguardando ativação" },
  ativa:        { cor: "#4ab870", icone: "✓",  label: "Ativa" },
  pausada:      { cor: "#e0a040", icone: "⏸",  label: "Pausada" },
  expirada:     { cor: "#e07040", icone: "✕",  label: "Expirada" },
  inadimplente: { cor: "#e74c3c", icone: "!",  label: "Inadimplente" },
  cancelada:    { cor: "#888",    icone: "–",  label: "Cancelada" },
};

function fmtData(isoStr) {
  return new Date(isoStr).toLocaleDateString("pt-BR", { timeZone: "America/Sao_Paulo" });
}

function _subProgressPct(sub) {
  const inicio  = new Date(sub.data_inicio_ciclo).getTime();
  const fim     = new Date(sub.data_expiracao).getTime();
  const agora   = Date.now();
  return Math.max(0, Math.min(100, Math.round(((agora - inicio) / (fim - inicio)) * 100)));
}

function _diasRestantes(sub) {
  return Math.ceil((new Date(sub.data_expiracao) - Date.now()) / 86400000);
}

function _subCardHtml(sub, pixPendente) {
  const info    = STATUS_SUB[sub.status] || STATUS_SUB.cancelada;
  const pct     = _subProgressPct(sub);
  const dias    = _diasRestantes(sub);
  const expira  = fmtData(sub.data_expiracao);
  const podePausar  = sub.status === "ativa" && dias > 0 && sub.plano !== "mensal";
  const podeRenovar = ["expirada", "inadimplente", "cancelada"].includes(sub.status) || (sub.status === "ativa" && dias <= 7);

  let retornoHtml = "";
  if (sub.status === "pausada" && sub.data_retorno_prevista) {
    retornoHtml = `<p class="sub-detalhe">Retorno previsto: ${fmtData(sub.data_retorno_prevista)}</p>`;
  }

  let pixHtml = "";
  if (pixPendente?.pix_copia_e_cola) {
    pixHtml = `
      <div class="pix-box">
        <p class="pix-label">⚡ Pagamento pendente — copie o PIX:</p>
        <div class="pix-row">
          <input id="pix-code-input" class="pix-code" readonly value="${pixPendente.pix_copia_e_cola}" />
          <button class="btn btn-primario pix-copy-btn" onclick="copiarPixJogador()">Copiar</button>
        </div>
        ${pixPendente.payment_link ? `<a href="${pixPendente.payment_link}" target="_blank" class="pix-link">Abrir link de cobrança ↗</a>` : ""}
      </div>`;
  }

  return `
    <div class="sub-card sub-card--${sub.status}">
      <div class="sub-card-header">
        <span class="sub-status-dot" style="color:${info.cor}">${info.icone} ${info.label}</span>
        <span class="sub-plano-label">${PLANO_LABEL[sub.plano] || sub.plano}</span>
      </div>
      <div class="sub-progress-wrap">
        <div class="sub-progress-bar" style="width:${pct}%;background:${info.cor}"></div>
      </div>
      <div class="sub-datas">
        <span>Início: ${fmtData(sub.data_inicio_ciclo)}</span>
        <span>Vence: ${expira}</span>
      </div>
      <p class="sub-dias" style="color:${dias <= 7 ? "#e07040" : info.cor}">
        ${dias > 0 ? `${dias} ${dias === 1 ? "dia restante" : "dias restantes"}` : "Vencida"}
      </p>
      ${retornoHtml}
      ${pixHtml}
      <div class="sub-acoes">
        ${podePausar  ? `<button class="btn btn-secundario sub-btn" onclick="abrirPausaUI()">⏸ Solicitar Pausa</button>` : ""}
        ${podeRenovar ? `<button class="btn btn-primario sub-btn"   onclick="abrirRenovarUI('Renovar Assinatura')">↺ Renovar</button>` : ""}
      </div>
    </div>`;
}

async function carregarPerfil() {
  const el = document.getElementById("perfil-info");
  el.innerHTML = "<p style='opacity:.5;font-size:.85rem'>Carregando…</p>";
  try {
    const [p, sub, pixPendente, filaPos] = await Promise.all([
      apiFetch("/auth/me"),
      apiFetch("/subscriptions/minha-ativa").catch(() => null),
      apiFetch("/subscriptions/pix-pendente").catch(() => null),
      apiFetch("/subscriptions/lista-espera/minha-posicao").catch(() => null),
    ]);
    if (!p) return;

    const nivel = p.nivel === "nao_classificado" ? "Não classificado" : `Nível ${p.nivel}`;

    let subHtml;
    if (sub) {
      subHtml = _subCardHtml(sub, pixPendente);
    } else if (filaPos) {
      const statusLabel = filaPos.status === "convocado" ? "🎉 Convocado!" : "⏳ Na lista de espera";
      const statusColor = filaPos.status === "convocado" ? "#4ab870" : "#e0a040";
      const expiracaoHtml = filaPos.status === "convocado" && filaPos.data_expiracao_convocacao
        ? `<p style="font-size:.78rem;color:#e0a040;margin-bottom:.5rem">Sua vaga expira em: <strong>${new Date(filaPos.data_expiracao_convocacao).toLocaleString("pt-BR",{timeZone:"America/Sao_Paulo",day:"2-digit",month:"2-digit",year:"numeric",hour:"2-digit",minute:"2-digit"})}</strong></p>`
        : "";
      subHtml = `<div class="sub-card" style="border-left:3px solid ${statusColor}">
        <p style="font-weight:700;color:${statusColor};margin-bottom:.3rem">${statusLabel}</p>
        <p style="font-size:.82rem;opacity:.8;margin-bottom:.25rem">Posição na fila: <strong>#${filaPos.posicao}</strong></p>
        ${expiracaoHtml}
        <p style="font-size:.78rem;opacity:.7;margin-bottom:.5rem">${filaPos.status === "convocado" ? "Uma vaga está disponível! Acesse o site e contrate seu plano agora." : "Você será notificado por e-mail quando uma vaga do ranking abrir."}</p>
        <button class="btn btn-secundario" style="width:100%;font-size:.8rem" onclick="sairDaFila()">Sair da lista de espera</button>
      </div>`;
    } else {
      subHtml = `<div class="sub-card sub-card--sem">
           <p style="font-weight:600;margin-bottom:.4rem">Sem assinatura ativa</p>
           <p style="font-size:.8rem;opacity:.7;margin-bottom:.75rem">Contrate um plano para ter acesso ao ranking e agendamentos.</p>
           <button class="btn btn-primario" style="width:100%" onclick="abrirRenovarUI()">Contratar Plano</button>
         </div>`;
    }

    const contratoHtml = !p.contrato_assinado && p.contrato_link_assinatura
      ? `<div class="sub-card" style="border-left:3px solid #e0a040;margin-bottom:.75rem">
           <p style="font-weight:700;color:#e0a040;margin-bottom:.3rem">📄 Contrato pendente</p>
           <p style="font-size:.8rem;opacity:.8;margin-bottom:.5rem">
             Assine o Termo de Adesão para liberar reservas de quadra.
           </p>
           ${p.contrato_link_assinatura
             ? `<a href="${p.contrato_link_assinatura}" target="_blank" rel="noopener"
                   style="font-size:.8rem;color:var(--cor-terracota);font-weight:600">
                   Abrir contrato para assinar →
                </a>`
             : `<p style="font-size:.78rem;opacity:.6">O contrato foi enviado via WhatsApp para assinatura.</p>`
           }
         </div>`
      : "";

    el.innerHTML = `
      ${contratoHtml}
      <div class="perfil-avatar-wrap">
        ${avatarHtml(p, " avatar-lg")}
        <label class="btn-foto" for="inp-foto-upload">Alterar foto</label>
        <input id="inp-foto-upload" type="file" accept=".jpg,.jpeg,.png,.webp" style="display:none" />
      </div>
      <div class="perfil-linha"><span class="perfil-label">Nome</span><span>${p.nome}</span></div>
      ${p.apelido ? `<div class="perfil-linha"><span class="perfil-label">Apelido</span><span>${p.apelido}</span></div>` : ""}
      <div class="perfil-linha"><span class="perfil-label">E-mail</span><span>${p.email}</span></div>
      <div class="perfil-linha"><span class="perfil-label">Telefone</span><span>${p.telefone}</span></div>
      ${p.cpf ? `<div class="perfil-linha"><span class="perfil-label">CPF</span><span>${p.cpf}</span></div>` : ""}
      ${p.data_nascimento ? `<div class="perfil-linha"><span class="perfil-label">Nascimento</span><span>${fmtData(p.data_nascimento + "T12:00:00")}</span></div>` : ""}
      <div class="perfil-linha"><span class="perfil-label">Nível</span><span>${nivel}</span></div>
      <div class="perfil-linha"><span class="perfil-label">Rating</span><span>${Math.round(p.rating_atual)}</span></div>
      <div class="perfil-linha"><span class="perfil-label">Pontos (temporada)</span><span>${p.pontos_ranking_temporada_atual}</span></div>
      <div class="perfil-linha" style="${_temEndereco(p) ? '' : 'border:none'}"><span class="perfil-label">Partidas computadas</span><span>${p.partidas_computadas_rating}</span></div>
      ${_enderecoHtml(p)}
      <div style="display:flex;gap:.5rem;justify-content:center;margin:.75rem 0">
        <button class="btn btn-secundario" style="font-size:.8rem;padding:.35rem 1rem" onclick="abrirEdicaoPerfil()">Editar dados pessoais</button>
        <button class="btn btn-secundario" style="font-size:.8rem;padding:.35rem 1rem" onclick="abrirAlterarSenha()">Alterar senha</button>
      </div>
      <div id="perfil-form-senha" style="display:none;background:rgba(255,255,255,.05);border-radius:8px;padding:.9rem 1rem;margin-bottom:.5rem">
        <p style="font-size:.85rem;font-weight:600;margin-bottom:.65rem;color:var(--cor-terracota)">Alterar senha</p>
        <div class="campo"><label>Senha atual</label><input type="password" id="senha-atual" /></div>
        <div class="campo"><label>Nova senha</label><input type="password" id="senha-nova" /></div>
        <div class="campo"><label>Confirmar nova senha</label><input type="password" id="senha-confirma" /></div>
        <p id="senha-erro" class="erro" hidden></p>
        <div style="display:flex;gap:.5rem;margin-top:.5rem">
          <button class="btn btn-secundario" style="flex:1;font-size:.82rem" onclick="fecharAlterarSenha()">Cancelar</button>
          <button class="btn btn-primario" style="flex:1;font-size:.82rem" onclick="confirmarAlterarSenha()">Salvar</button>
        </div>
      </div>
      <div id="perfil-form-editar" style="display:none;background:rgba(255,255,255,.05);border-radius:8px;padding:.9rem 1rem;margin-bottom:.5rem">
        <p style="font-size:.85rem;font-weight:600;margin-bottom:.65rem;color:var(--cor-terracota)">Editar dados</p>
        <div class="campo"><label>Nome completo</label><input type="text" id="edit-nome" value="${p.nome || ""}" /></div>
        <div class="campo"><label>Apelido</label><input type="text" id="edit-apelido" value="${p.apelido || ""}" placeholder="Opcional" /></div>
        <div class="campo"><label>E-mail</label><input type="email" id="edit-email" value="${p.email || ""}" /></div>
        <div class="campo"><label>Telefone</label><input type="tel" id="edit-telefone" value="${p.telefone || ""}" placeholder="Ex: 16991234567" /></div>
        <div class="campo"><label>CPF</label><input type="text" id="edit-cpf" value="${p.cpf || ""}" placeholder="000.000.000-00" maxlength="14" /></div>
        <div class="campo"><label>Data de nascimento</label><input type="date" id="edit-nascimento" value="${p.data_nascimento || ""}" /></div>
        <p class="perfil-secao-label" style="margin-top:.5rem">Endereço</p>
        <div class="campo"><label>Logradouro</label><input type="text" id="edit-rua" value="${p.rua || ""}" /></div>
        <div style="display:grid;grid-template-columns:1fr 1fr;gap:.5rem">
          <div class="campo"><label>Número</label><input type="text" id="edit-numero" value="${p.numero || ""}" /></div>
          <div class="campo"><label>Complemento</label><input type="text" id="edit-complemento" value="${p.complemento || ""}" /></div>
        </div>
        <div class="campo"><label>Bairro</label><input type="text" id="edit-bairro" value="${p.bairro || ""}" /></div>
        <div style="display:grid;grid-template-columns:1fr auto;gap:.5rem">
          <div class="campo"><label>Cidade</label><input type="text" id="edit-cidade" value="${p.cidade || ""}" /></div>
          <div class="campo"><label>Estado</label><input type="text" id="edit-estado" value="${p.estado || ""}" maxlength="2" style="text-transform:uppercase;width:4rem" /></div>
        </div>
        <div style="display:grid;grid-template-columns:1fr 1fr;gap:.5rem">
          <div class="campo"><label>CEP</label><input type="text" id="edit-cep" value="${p.cep || ""}" maxlength="9" /></div>
          <div class="campo"><label>País</label><input type="text" id="edit-pais" value="${p.pais || ""}" /></div>
        </div>
        <p id="edit-perfil-erro" class="erro" hidden></p>
        <div style="display:flex;gap:.5rem;margin-top:.5rem">
          <button class="btn btn-secundario" style="flex:1;font-size:.82rem" onclick="fecharEdicaoPerfil()">Cancelar</button>
          <button class="btn btn-primario" style="flex:1;font-size:.82rem" onclick="salvarDadosPerfil()">Salvar</button>
        </div>
      </div>
      <p class="card-titulo" style="margin-top:1rem;margin-bottom:.5rem">Minha Assinatura</p>
      ${subHtml}
      <div id="sub-renovar-ui" style="display:none" class="sub-card">
        <p id="renovar-titulo" style="font-weight:700;margin-bottom:.75rem">Contratar / Renovar Plano</p>
        <div class="campo">
          <label>Plano</label>
          <select id="renovar-plano" onchange="atualizarFormasPagamento()">
            <option value="mensal">Mensal</option>
            <option value="trimestral">Trimestral</option>
            <option value="semestral">Semestral</option>
            <option value="anual">Anual</option>
          </select>
        </div>
        <div class="campo">
          <label>Forma de Pagamento</label>
          <select id="renovar-forma">
            <option value="pix_avista">PIX à vista (5% de desconto)</option>
            <option value="cartao_parcelado">Cartão de Crédito</option>
          </select>
        </div>
        <div id="renovar-pix-box" style="display:none" class="pix-box">
          <p class="pix-label">⚡ PIX gerado — copie e pague:</p>
          <div class="pix-row">
            <input id="renovar-pix-input" class="pix-code" readonly />
            <button class="btn btn-primario pix-copy-btn" onclick="copiarPixRenovar()">Copiar</button>
          </div>
        </div>
        <div id="renovar-link-box" style="display:none" class="pix-box">
          <p class="pix-label">💳 Pagamento gerado:</p>
          <a id="renovar-link-anchor" href="#" target="_blank" rel="noopener"
             style="font-size:.85rem;color:var(--cor-terracota);font-weight:600;display:block;margin-top:.25rem">
            Abrir link de pagamento →
          </a>
        </div>
        <p id="renovar-erro" class="erro" hidden></p>
        <div style="display:flex;gap:.5rem;margin-top:.5rem">
          <button class="btn btn-secundario" style="flex:1" onclick="fecharRenovarUI()">Cancelar</button>
          <button id="renovar-btn" class="btn btn-primario" style="flex:1" onclick="confirmarRenovar()">Confirmar</button>
        </div>
      </div>
      <div id="sub-pausa-ui" style="display:none" class="sub-card">
        <p style="font-weight:700;margin-bottom:.5rem">Solicitar Pausa</p>
        <p style="font-size:.78rem;opacity:.7;margin-bottom:.5rem">Disponível para planos de 3, 6 ou 12 meses. Pausa máxima de 15 dias.</p>
        <div class="campo">
          <label>Motivo (obrigatório)</label>
          <input type="text" id="pausa-motivo" placeholder="Ex: viagem, lesão…" />
        </div>
        <div class="campo">
          <label>Data de início da pausa (obrigatório)</label>
          <input type="date" id="pausa-data-inicio" min="${new Date().toISOString().split('T')[0]}" />
        </div>
        <div class="campo">
          <label>Dias de pausa (1–15)</label>
          <input type="number" id="pausa-dias" min="1" max="15" value="7" />
        </div>
        <p id="pausa-erro" class="erro" hidden></p>
        <div style="display:flex;gap:.5rem;margin-top:.5rem">
          <button class="btn btn-secundario" style="flex:1" onclick="fecharPausaUI()">Cancelar</button>
          <button class="btn btn-primario" style="flex:1" onclick="confirmarPausa()">Enviar</button>
        </div>
      </div>
    `;

    // Popula preços no select de renovação
    apiFetch("/subscriptions/precos").then(precos => {
      if (!precos) return;
      document.getElementById("renovar-plano").innerHTML = [
        ["mensal",      `Mensal — R$ ${precos.mensal?.valor_total?.toFixed(2) ?? ""}`],
        ["trimestral",  `Trimestral — R$ ${precos.trimestral?.valor_total?.toFixed(2) ?? ""}`],
        ["semestral",   `Semestral — R$ ${precos.semestral?.valor_total?.toFixed(2) ?? ""}`],
        ["anual",       `Anual — R$ ${precos.anual?.valor_total?.toFixed(2) ?? ""}`],
      ].map(([v, l]) => `<option value="${v}">${l}</option>`).join("");
    }).catch(() => {});

    document.getElementById("inp-foto-upload").addEventListener("change", async (e) => {
      const file = e.target.files[0];
      if (!file) return;
      try {
        await uploadFoto(file);
        await Promise.all([carregarPerfil(), carregarRanking()]);
      } catch (err) { alert(err.message); }
    });
  } catch {
    el.innerHTML = "<p style='color:var(--cor-erro)'>Erro ao carregar perfil.</p>";
  }
}

function abrirAlterarSenha() {
  document.getElementById("perfil-form-editar").style.display = "none";
  const f = document.getElementById("perfil-form-senha");
  f.style.display = "block";
  ["senha-atual","senha-nova","senha-confirma"].forEach(id => document.getElementById(id).value = "");
  document.getElementById("senha-erro").hidden = true;
}

function fecharAlterarSenha() {
  document.getElementById("perfil-form-senha").style.display = "none";
}

async function confirmarAlterarSenha() {
  const erro = document.getElementById("senha-erro");
  erro.hidden = true;
  const atual    = document.getElementById("senha-atual").value;
  const nova     = document.getElementById("senha-nova").value;
  const confirma = document.getElementById("senha-confirma").value;
  if (!atual || !nova) { erro.textContent = "Preencha todos os campos."; erro.hidden = false; return; }
  if (nova.length < 6)  { erro.textContent = "A nova senha deve ter pelo menos 6 caracteres."; erro.hidden = false; return; }
  if (nova !== confirma) { erro.textContent = "As senhas não conferem."; erro.hidden = false; return; }
  try {
    await apiFetch("/auth/alterar-senha", { method: "POST", body: JSON.stringify({ senha_atual: atual, nova_senha: nova }) });
    fecharAlterarSenha();
    alert("Senha alterada com sucesso!");
  } catch (e) {
    erro.textContent = e.message || "Erro ao alterar senha.";
    erro.hidden = false;
  }
}

function abrirEdicaoPerfil() {
  document.getElementById("perfil-form-senha").style.display = "none";
  document.getElementById("perfil-form-editar").style.display = "block";
}

function fecharEdicaoPerfil() {
  const f = document.getElementById("perfil-form-editar");
  if (f) f.style.display = "none";
}

function _validarCPF(cpf) {
  cpf = cpf.replace(/\D/g, "");
  if (cpf.length !== 11 || /^(\d)\1+$/.test(cpf)) return false;
  let soma = 0;
  for (let i = 0; i < 9; i++) soma += +cpf[i] * (10 - i);
  let r = (soma * 10) % 11;
  if (r >= 10) r = 0;
  if (r !== +cpf[9]) return false;
  soma = 0;
  for (let i = 0; i < 10; i++) soma += +cpf[i] * (11 - i);
  r = (soma * 10) % 11;
  if (r >= 10) r = 0;
  return r === +cpf[10];
}

async function salvarDadosPerfil() {
  const erro = document.getElementById("edit-perfil-erro");
  erro.hidden = true;

  const g = (id) => document.getElementById(id)?.value.trim() ?? "";
  const cpfRaw = g("edit-cpf").replace(/\D/g, "");
  if (cpfRaw && !_validarCPF(cpfRaw)) {
    erro.textContent = "CPF inválido.";
    erro.hidden = false;
    return;
  }

  const body = {
    nome:            g("edit-nome")        || undefined,
    apelido:         g("edit-apelido")     || null,
    email:           g("edit-email")       || undefined,
    telefone:        g("edit-telefone")    || undefined,
    cpf:             cpfRaw                || null,
    data_nascimento: g("edit-nascimento")  || null,
    rua:             g("edit-rua")         || null,
    numero:          g("edit-numero")      || null,
    complemento:     g("edit-complemento") || null,
    bairro:          g("edit-bairro")      || null,
    cidade:          g("edit-cidade")      || null,
    estado:          g("edit-estado").toUpperCase() || null,
    cep:             g("edit-cep")         || null,
    pais:            g("edit-pais")        || null,
  };
  // Remove campos undefined (não enviados ao backend)
  Object.keys(body).forEach(k => body[k] === undefined && delete body[k]);

  try {
    await apiFetch("/players/me", { method: "PATCH", body: JSON.stringify(body) });
    await carregarPerfil();
  } catch (e) {
    erro.textContent = e.message || "Erro ao salvar.";
    erro.hidden = false;
  }
}

async function sairDaFila() {
  if (!confirm("Deseja sair da lista de espera?")) return;
  try {
    await apiFetch("/subscriptions/lista-espera", { method: "DELETE" });
    carregarPerfil();
  } catch (e) { alert(e.message); }
}

function copiarPixJogador() {
  const el = document.getElementById("pix-code-input");
  if (el) navigator.clipboard.writeText(el.value).then(() => alert("PIX copiado!"));
}
function copiarPixRenovar() {
  const el = document.getElementById("renovar-pix-input");
  if (el) navigator.clipboard.writeText(el.value).then(() => alert("PIX copiado!"));
}

function atualizarFormasPagamento() {
  // PIX disponível para todos os planos com 5% de desconto
}

function abrirRenovarUI(titulo) {
  document.getElementById("sub-pausa-ui").style.display = "none";
  document.getElementById("sub-renovar-ui").style.display = "";
  document.getElementById("renovar-pix-box").style.display = "none";
  document.getElementById("renovar-link-box").style.display = "none";
  document.getElementById("renovar-erro").hidden = true;
  document.getElementById("renovar-btn").style.display = "";
  document.getElementById("renovar-titulo").textContent = titulo || "Contratar / Renovar Plano";
  atualizarFormasPagamento();
}
function fecharRenovarUI() { document.getElementById("sub-renovar-ui").style.display = "none"; }

async function confirmarRenovar() {
  const btn = document.getElementById("renovar-btn");
  const erroEl = document.getElementById("renovar-erro");
  erroEl.hidden = true;
  btn.disabled = true; btn.textContent = "Gerando…";
  try {
    const plano = document.getElementById("renovar-plano").value;
    const forma_pagamento = document.getElementById("renovar-forma").value;
    const res = await apiFetch("/subscriptions/renovar", {
      method: "POST",
      body: JSON.stringify({ plano, forma_pagamento }),
    });
    if (res?.pix_copia_e_cola) {
      document.getElementById("renovar-pix-input").value = res.pix_copia_e_cola;
      document.getElementById("renovar-pix-box").style.display = "";
      btn.style.display = "none";
    } else if (res?.payment_link) {
      document.getElementById("renovar-link-anchor").href = res.payment_link;
      document.getElementById("renovar-link-box").style.display = "";
      btn.style.display = "none";
    } else {
      fecharRenovarUI();
      await carregarPerfil();
    }
  } catch (err) {
    erroEl.textContent = err.message;
    erroEl.hidden = false;
  } finally {
    btn.disabled = false; btn.textContent = "Confirmar";
  }
}

function abrirPausaUI() {
  document.getElementById("sub-renovar-ui").style.display = "none";
  document.getElementById("sub-pausa-ui").style.display = "";
  document.getElementById("pausa-erro").hidden = true;
}
function fecharPausaUI() { document.getElementById("sub-pausa-ui").style.display = "none"; }

async function confirmarPausa() {
  const erroEl = document.getElementById("pausa-erro");
  erroEl.hidden = true;
  const motivo = document.getElementById("pausa-motivo").value.trim();
  const dataInicio = document.getElementById("pausa-data-inicio").value;
  const diasPausa = parseInt(document.getElementById("pausa-dias").value, 10);

  if (!motivo) {
    erroEl.textContent = "O motivo da pausa é obrigatório.";
    erroEl.hidden = false;
    return;
  }
  if (!dataInicio) {
    erroEl.textContent = "Informe a data de início da pausa.";
    erroEl.hidden = false;
    return;
  }
  if (!diasPausa || diasPausa < 1 || diasPausa > 15) {
    erroEl.textContent = "Informe entre 1 e 15 dias de pausa.";
    erroEl.hidden = false;
    return;
  }
  try {
    await apiFetch("/subscriptions/solicitar-pausa", {
      method: "POST",
      body: JSON.stringify({ motivo, data_inicio: dataInicio, dias_pausa: diasPausa }),
    });
    alert("Solicitação enviada! O administrador analisará e entrará em contato.");
    fecharPausaUI();
  } catch (err) {
    erroEl.textContent = err.message;
    erroEl.hidden = false;
  }
}

// ── Uso semanal ──────────────────────────────────────────────────────────────
function _barraUso(label, uso) {
  const pct = uso.limite ? Math.min((uso.usados / uso.limite) * 100, 100) : 0;
  const esgotado = uso.restantes === 0;
  const cor = esgotado ? "#e07040" : "var(--cor-terracota)";
  return `
    <div class="uso-linha">
      <div class="uso-topo">
        <span class="uso-label">${label}</span>
        <span class="uso-nums">${uso.usados} de ${uso.limite}</span>
      </div>
      <div class="uso-barra"><div class="uso-barra-fill" style="width:${pct}%;background:${cor}"></div></div>
      <span class="uso-restante" style="${esgotado ? "color:#e07040" : ""}">
        ${esgotado ? "Cota esgotada nesta semana" : `${uso.restantes} ${uso.restantes === 1 ? "jogo restante" : "jogos restantes"}`}
      </span>
    </div>`;
}

async function carregarUsoSemanal() {
  const el = document.getElementById("uso-semanal");
  if (!el) return;
  el.innerHTML = "<p style='opacity:.5;font-size:.85rem'>Carregando…</p>";
  try {
    const u = await apiFetch("/bookings/uso-semanal");
    if (!u) return;
    const periodo = `${_fmtDataTemporada(u.semana_inicio)} – ${_fmtDataTemporada(u.semana_fim)}`;
    el.innerHTML = `
      <p style="font-size:.72rem;opacity:.5;margin-bottom:.6rem">${periodo}</p>
      ${_barraUso("Simples", u.simples)}
      ${_barraUso("Duplas", u.duplas)}`;
  } catch {
    el.innerHTML = "<p style='color:var(--cor-erro);font-size:.85rem'>Erro ao carregar seus jogos da semana.</p>";
  }
}

// ── Agendamento ──────────────────────────────────────────────────────────────
let _slots = [];
let _slotSelecionado = null;
let _jogadores = [];
let _me = null;
let _precoJogoAvulso = null;

const POSICOES = [
  { sel: "sel-adversario",  lado: "B", label: "Adversário" },
  { sel: "sel-parceiro",    lado: "A", label: "Seu parceiro" },
  { sel: "sel-adversario2", lado: "B", label: "2º adversário" },
];

function _tipoSelecionado() {
  return document.querySelector('input[name="tipo-jogo"]:checked').value;
}

function _posicoesAtivas() {
  return _tipoSelecionado() === "duplas" ? POSICOES : POSICOES.slice(0, 1);
}

function _avulsoLigado() {
  return document.getElementById("chk-jogo-avulso")?.checked === true;
}

function _slotEhUltimaHora(slot) {
  return ["ranking_ultima_hora", "comercial_ultima_hora"].includes(slot?.tipo_disponibilidade);
}

function fmtHora(isoStr) {
  return new Date(isoStr).toLocaleTimeString("pt-BR", { hour: "2-digit", minute: "2-digit", timeZone: "America/Sao_Paulo" });
}

const SLOT_CONFIG = {
  ranking:               { label: "Disponível",        cls: "label-ranking" },
  ranking_ultima_hora:   { label: "Última hora!",       cls: "label-ultima-hora" },
  comercial_ultima_hora: { label: "Última hora!",       cls: "label-ultima-hora" },
  ocupado:               { label: "Reservado",          cls: "label-ocupado" },
  passado:               { label: "Encerrado",          cls: "label-indisponivel" },
  comercial:             { label: "Só na última hora",  cls: "label-indisponivel" },
  janela_morta:          { label: "Fora da janela",     cls: "label-indisponivel" },
};

function fmtPlacar(placar, lado_vencedor) {
  if (!placar || !placar.lado_A || !placar.lado_B) return null;
  const sets = placar.lado_A.map((g, i) => `${g}-${placar.lado_B[i] ?? "?"}`).join(", ");
  const venc = lado_vencedor === "A" ? placar.lado_A.reduce((a, b) => a + b, 0) > placar.lado_B.reduce((a, b) => a + b, 0) ? "A" : "B" : lado_vencedor;
  return sets;
}

function fmtJogadoresSlot(jogadores) {
  if (!jogadores || !jogadores.length) return null;
  const nome = (j) => esc(j.apelido || j.nome.split(" ")[0]);
  const ladoA = jogadores.filter(j => j.lado === "A").map(nome).join(" / ");
  const ladoB = jogadores.filter(j => j.lado === "B").map(nome).join(" / ");
  return ladoA && ladoB ? `${ladoA} vs ${ladoB}` : (ladoA || ladoB);
}

async function buscarSlots() {
  const data = document.getElementById("inp-data-jogo").value;
  const tipo = document.querySelector('input[name="tipo-jogo"]:checked').value;
  if (!data) return;

  document.getElementById("slots-container").hidden = false;
  document.getElementById("form-reserva").hidden = true;
  _slotSelecionado = null;

  const lista = document.getElementById("lista-slots");
  lista.innerHTML = "<p style='opacity:.5;font-size:.85rem'>Carregando…</p>";

  try {
    const slots = await apiFetch(`/bookings/slots?data=${data}&tipo=${tipo}`);
    if (!slots) return;
    _slots = slots;

    if (!slots.length) {
      lista.innerHTML = "<p style='opacity:.5;font-size:.85rem'>Nenhum slot para este dia.</p>";
      return;
    }

    lista.innerHTML = slots.map((s, i) => {
      const cfg = SLOT_CONFIG[s.tipo_disponibilidade] || { label: s.tipo_disponibilidade, cls: "label-indisponivel" };
      const livre = s.disponivel;
      const nomes = fmtJogadoresSlot(s.jogadores);
      const placar = s.placar ? fmtPlacar(s.placar, s.lado_vencedor) : null;
      const statusLabel = s.status_partida === "realizado" ? "Resultado: " : s.status_partida === "wo" ? "W.O. · " : "";

      let centro = "";
      if (nomes) {
        const placarHtml = placar ? `<span class="slot-placar">${statusLabel}${placar}</span>` : "";
        centro = `<div class="slot-info-centro"><span class="slot-jogadores">${nomes}</span>${placarHtml}</div>`;
      } else if (s.motivo_indisponibilidade && s.tipo_disponibilidade === "janela_morta") {
        centro = `<span class="slot-motivo-inline" style="font-size:.75rem;opacity:.45">${s.motivo_indisponibilidade}</span>`;
      } else {
        centro = `<span></span>`;
      }

      return `
        <div class="slot-item ${livre ? "slot-livre" : "slot-indisponivel"}"
             ${livre ? `onclick="selecionarSlot(${i})"` : ""}>
          <span class="slot-hora">${fmtHora(s.data_hora_inicio)}</span>
          ${centro}
          <span class="slot-label ${cfg.cls}">${cfg.label}</span>
        </div>`;
    }).join("");
  } catch {
    lista.innerHTML = "<p style='color:var(--cor-erro)'>Erro ao buscar horários.</p>";
  }
}

function fmtBRL(v) {
  return `R$ ${Number(v).toLocaleString("pt-BR", { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`;
}

function esc(s) {
  return String(s ?? "").replace(/[&<>"']/g, (c) =>
    ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
}

let _convidadosData = {};

function _snapshotConvidados() {
  _posicoesAtivas().forEach(({ sel }) => {
    if (!document.getElementById(`cv-${sel}-nome`)) return;
    _convidadosData[sel] = {
      nome:    document.getElementById(`cv-${sel}-nome`).value,
      cpf:     document.getElementById(`cv-${sel}-cpf`).value,
      tel:     document.getElementById(`cv-${sel}-tel`).value,
      nasc:    document.getElementById(`cv-${sel}-nasc`).value,
      apelido: document.getElementById(`cv-${sel}-apelido`).value,
    };
  });
}

function _formConvidadoHtml({ sel, label }) {
  const d = _convidadosData[sel] || {};
  return `
    <div class="convidado-box">
      <p class="convidado-titulo">Convidado — ${label}</p>
      <div class="campo"><label>Nome completo</label><input type="text" id="cv-${sel}-nome" value="${esc(d.nome)}" /></div>
      <div class="campo"><label>CPF</label><input type="text" id="cv-${sel}-cpf" maxlength="14" placeholder="000.000.000-00" value="${esc(d.cpf)}" /></div>
      <div class="campo"><label>WhatsApp</label><input type="tel" id="cv-${sel}-tel" placeholder="16991234567" value="${esc(d.tel)}" /></div>
      <div class="campo"><label>Data de nascimento</label><input type="date" id="cv-${sel}-nasc" value="${esc(d.nasc)}" /></div>
      <div class="campo" style="margin-bottom:0"><label>Apelido (opcional)</label><input type="text" id="cv-${sel}-apelido" value="${esc(d.apelido)}" /></div>
    </div>`;
}

function _renderFormsConvidados() {
  const wrap  = document.getElementById("avulso-convidados");
  const pagam = document.getElementById("avulso-pagamento");
  if (!_avulsoLigado()) {
    _snapshotConvidados();
    wrap.innerHTML = "";
    pagam.hidden = true;
    return;
  }
  _snapshotConvidados();
  const posConv = _posicoesAtivas().filter((p) => document.getElementById(p.sel).value === "convidado");
  wrap.innerHTML = posConv.map(_formConvidadoHtml).join("");
  pagam.hidden = posConv.length === 0;

  const total = document.getElementById("avulso-total");
  if (!posConv.length || _precoJogoAvulso == null) {
    total.textContent = "";
  } else {
    total.innerHTML = `Total: <strong>${fmtBRL(_precoJogoAvulso * posConv.length)}</strong>`
      + `<span style="opacity:.6;font-weight:400"> · ${posConv.length} × ${fmtBRL(_precoJogoAvulso)}</span>`;
  }
}

function _renderSelectsJogadores() {
  const opts = _jogadores
    .filter((j) => j.id !== _me?.id)
    .map((j) => `<option value="${j.id}">${j.nome} · ${j.nivel === "nao_classificado" ? "Não class." : "Nível " + j.nivel}</option>`)
    .join("");
  const optConvidado = _avulsoLigado()
    ? `<option value="convidado">+ Convidado (fora do ranking)</option>`
    : "";

  const isDuplas = _tipoSelecionado() === "duplas";
  document.getElementById("campo-parceiro").hidden = !isDuplas;
  document.getElementById("campo-adversario2").hidden = !isDuplas;

  _posicoesAtivas().forEach(({ sel }) => {
    const el = document.getElementById(sel);
    const anterior = el.value;
    el.innerHTML = optConvidado + opts;
    if (anterior && [...el.options].some((o) => o.value === anterior)) el.value = anterior;
  });
  _renderFormsConvidados();
}

async function selecionarSlot(idx) {
  _slotSelecionado = _slots[idx];

  if (!_me) _me = await apiFetch("/auth/me");
  if (!_jogadores.length) _jogadores = (await apiFetch("/players")) || [];
  if (_precoJogoAvulso == null) {
    _precoJogoAvulso = await fetch("/api/v1/public/empresa")
      .then((r) => (r.ok ? r.json() : null))
      .then((e) => e?.preco_jogo_avulso ?? null)
      .catch(() => null);
  }

  document.getElementById("reserva-slot-info").textContent =
    `${fmtHora(_slotSelecionado.data_hora_inicio)} – ${fmtHora(_slotSelecionado.data_hora_fim)}`;

  _convidadosData = {};
  document.getElementById("chk-jogo-avulso").checked = false;
  document.getElementById("campo-avulso-toggle").hidden = !_slotEhUltimaHora(_slotSelecionado);
  document.getElementById("avulso-cobranca").hidden = true;
  document.getElementById("avulso-cobranca").innerHTML = "";
  document.getElementById("reserva-acoes").hidden = false;

  _renderSelectsJogadores();

  document.getElementById("reserva-erro").hidden = true;
  document.getElementById("form-reserva").hidden = false;
  document.getElementById("form-reserva").scrollIntoView({ behavior: "smooth" });
}

document.getElementById("chk-jogo-avulso")?.addEventListener("change", _renderSelectsJogadores);
POSICOES.forEach(({ sel }) => {
  document.getElementById(sel)?.addEventListener("change", _renderFormsConvidados);
});

document.getElementById("btn-buscar-slots")?.addEventListener("click", buscarSlots);
document.getElementById("inp-data-jogo")?.addEventListener("keydown", (e) => {
  if (e.key === "Enter") buscarSlots();
});

document.getElementById("btn-cancelar-reserva")?.addEventListener("click", () => {
  document.getElementById("form-reserva").hidden = true;
  _slotSelecionado = null;
});

function _coletarConvidado(sel, lado) {
  const g = (campo) => document.getElementById(`cv-${sel}-${campo}`).value.trim();
  const nome = g("nome");
  const cpf = g("cpf").replace(/\D/g, "");
  const tel = g("tel").replace(/\D/g, "");
  const nasc = g("nasc");

  if (!nome || !cpf || !tel || !nasc) throw new Error("Preencha todos os dados dos convidados.");
  if (nome.split(/\s+/).length < 2) throw new Error(`Informe o nome completo do convidado (${nome}).`);
  if (!_validarCPF(cpf)) throw new Error(`CPF inválido para o convidado ${nome}.`);

  return { nome, cpf, whatsapp: tel, data_nascimento: nasc, apelido: g("apelido") || null, lado };
}

async function confirmarJogoAvulso() {
  const erroEl = document.getElementById("reserva-erro");
  const btn = document.getElementById("btn-confirmar-reserva");
  const tipo = _tipoSelecionado();

  const membros_a = [_me.id];
  const membros_b = [];
  const convidados = [];

  try {
    for (const { sel, lado } of _posicoesAtivas()) {
      const val = document.getElementById(sel).value;
      if (val === "convidado") {
        convidados.push(_coletarConvidado(sel, lado));
      } else {
        (lado === "A" ? membros_a : membros_b).push(parseInt(val));
      }
    }
    if (!convidados.length) throw new Error("Selecione ao menos um convidado de fora do ranking.");
  } catch (e) {
    erroEl.textContent = e.message;
    erroEl.hidden = false;
    return;
  }

  btn.disabled = true;
  btn.textContent = "Gerando cobrança…";
  erroEl.hidden = true;

  try {
    const r = await apiFetch("/bookings/jogo-avulso", {
      method: "POST",
      body: JSON.stringify({
        data_hora: _slotSelecionado.data_hora_inicio,
        tipo,
        metodo_pagamento: document.getElementById("sel-avulso-pagamento").value,
        membros_a,
        membros_b,
        convidados,
      }),
    });

    const box = document.getElementById("avulso-cobranca");
    const pagamento = r.invoice_url
      ? `<a href="${r.invoice_url}" target="_blank" rel="noopener" class="btn btn-primario" style="width:100%;margin-top:.5rem">Abrir link de pagamento →</a>`
      : `<div class="pix-row" style="margin-top:.5rem">
           <input class="pix-code" readonly value="${r.pix_copia_cola || ""}" id="avulso-pix-input" />
           <button class="btn btn-primario pix-copy-btn" onclick="copiarPixAvulso()">Copiar</button>
         </div>`;
    box.innerHTML = `
      <div class="pix-box">
        <p class="pix-label">${fmtBRL(r.valor)} — aguardando pagamento</p>
        <p style="font-size:.78rem;opacity:.7">${r.msg}</p>
        ${pagamento}
      </div>
      <button class="btn btn-secundario" style="width:100%;margin-top:.5rem" onclick="fecharReserva()">Fechar</button>`;
    box.hidden = false;
    document.getElementById("reserva-acoes").hidden = true;
  } catch (e) {
    erroEl.textContent = e.message.replace(/^Erro \d+: /, "");
    erroEl.hidden = false;
  } finally {
    btn.disabled = false;
    btn.textContent = "Confirmar";
  }
}

function copiarPixAvulso() {
  const el = document.getElementById("avulso-pix-input");
  if (el?.value) navigator.clipboard.writeText(el.value).then(() => alert("PIX copiado!"));
}

function fecharReserva() {
  document.getElementById("form-reserva").hidden = true;
  _slotSelecionado = null;
  buscarSlots();
  carregarUsoSemanal();
}

document.getElementById("btn-confirmar-reserva")?.addEventListener("click", async () => {
  if (!_slotSelecionado || !_me) return;
  if (_avulsoLigado()) return confirmarJogoAvulso();

  const tipo = _tipoSelecionado();
  const advId = parseInt(document.getElementById("sel-adversario").value);
  let lado_a = [_me.id];
  let lado_b = [advId];

  if (tipo === "duplas") {
    const parceiroId = parseInt(document.getElementById("sel-parceiro").value);
    const adv2Id = parseInt(document.getElementById("sel-adversario2").value);
    lado_a = [_me.id, parceiroId];
    lado_b = [advId, adv2Id];
  }

  const btn = document.getElementById("btn-confirmar-reserva");
  const erroEl = document.getElementById("reserva-erro");
  btn.disabled = true;
  btn.textContent = "Confirmando…";
  erroEl.hidden = true;

  try {
    await apiFetch("/bookings/ranking", {
      method: "POST",
      body: JSON.stringify({
        data_hora: _slotSelecionado.data_hora_inicio,
        tipo,
        lado_a,
        lado_b,
      }),
    });
    document.getElementById("form-reserva").hidden = true;
    _slotSelecionado = null;
    buscarSlots();
    carregarUsoSemanal();
    alert("Partida agendada!");
  } catch (e) {
    erroEl.textContent = e.message.replace(/^Erro \d+: /, "");
    erroEl.hidden = false;
  } finally {
    btn.disabled = false;
    btn.textContent = "Confirmar";
  }
});

// Data mínima = hoje
const inpData = document.getElementById("inp-data-jogo");
if (inpData) {
  const hoje = new Date().toLocaleDateString("sv-SE", { timeZone: "America/Sao_Paulo" });
  inpData.min = hoje;
  inpData.value = hoje;
}

// ── Partidas ─────────────────────────────────────────────────────────────────
let _partidas = [];
let _partidaSelecionada = null;

function fmtDataHora(isoStr) {
  const d = new Date(isoStr);
  const dia = d.toLocaleDateString("pt-BR", {
    timeZone: "America/Sao_Paulo", weekday: "short", day: "2-digit", month: "2-digit",
  });
  const hora = d.toLocaleTimeString("pt-BR", {
    timeZone: "America/Sao_Paulo", hour: "2-digit", minute: "2-digit",
  });
  return `${dia} ${hora}`;
}

function nomesLado(partida, lado, jogadores) {
  return partida.participantes
    .filter((p) => p.lado === lado)
    .map((p) => {
      if (p.convidado_id) return esc(p.convidado_nome || "Convidado");
      const j = jogadores.find((j) => j.id === p.player_id);
      if (!j) return `#${p.player_id}`;
      if (j.apelido) return j.apelido;
      const partes = j.nome.trim().split(/\s+/);
      return partes.length > 1 ? `${partes[0]} ${partes[partes.length - 1]}` : partes[0];
    })
    .join(" / ");
}

function placarStr(placar) {
  if (!placar) return "";
  const { games_A, games_B, tiebreak_A, tiebreak_B } = placar;
  const tb = tiebreak_A != null ? ` (TB ${tiebreak_A}–${tiebreak_B})` : "";
  return `${games_A}–${games_B}${tb}`;
}

function renderPartida(p, aguardandoPlacar) {
  const nA = nomesLado(p, "A", _jogadores);
  const nB = nomesLado(p, "B", _jogadores);

  const futura = new Date(p.data_hora) > new Date();

  let statusCls, statusTxt, cardCls = "partida-card";
  if (aguardandoPlacar) {
    statusCls = "status-aguardando"; statusTxt = "Aguardando placar"; cardCls += " aguardando-placar";
  } else if (p.status === "agendado" && !futura) {
    statusCls = "status-cancelado"; statusTxt = "Encerrado";
  } else if (p.status === "agendado") {
    statusCls = "status-agendado"; statusTxt = "Agendado"; cardCls += " agendada";
  } else if (p.status === "realizado") {
    statusCls = "status-realizado"; statusTxt = "Realizado"; cardCls += " realizado";
  } else if (p.status === "wo") {
    statusCls = "status-wo"; statusTxt = "W.O."; cardCls += " cancelado";
  } else {
    statusCls = "status-cancelado"; statusTxt = "Cancelado"; cardCls += " cancelado";
  }

  const tipo = (p.tipo === "simples" ? "Simples" : "Duplas")
    + (p.avulso ? ' · <span class="partida-avulso">Jogo avulso — não pontua</span>' : "");
  const vsHtml = p.placar
    ? `<div class="partida-placar">${nA} <span style="opacity:.45;font-weight:400">${placarStr(p.placar)}</span> ${nB}</div>`
    : `<div class="partida-jogadores">${nA} <span style="opacity:.35">vs</span> ${nB}</div>`;

  const btnHtml = aguardandoPlacar
    ? `<div style="text-align:center;margin-top:.5rem">
         <button class="btn btn-primario" style="font-size:.8rem;padding:.35rem .9rem"
                 onclick="abrirFormPlacar(${p.id})">Lançar placar</button>
       </div>`
    : p.status === "agendado" && futura
    ? `<div style="text-align:right;margin-top:.4rem">
         <button class="btn" style="font-size:.75rem;padding:.25rem .7rem;opacity:.7;border:1px solid rgba(255,255,255,.15);border-radius:6px;background:transparent;color:inherit;cursor:pointer"
                 onclick="cancelarPartida(${p.id})">Cancelar partida</button>
       </div>`
    : "";

  return `
    <div class="${cardCls}">
      <div class="partida-header">
        <span class="partida-data">${fmtDataHora(p.data_hora)}</span>
        <span class="partida-status ${statusCls}">${statusTxt}</span>
      </div>
      ${vsHtml}
      <div class="partida-tipo">${tipo}</div>
      ${btnHtml}
    </div>`;
}

async function carregarPartidas() {
  const cont = document.getElementById("partidas-lista");
  document.getElementById("form-placar").hidden = true;
  _partidaSelecionada = null;
  cont.innerHTML = "<p style='opacity:.5;font-size:.85rem'>Carregando…</p>";

  try {
    if (!_jogadores.length) _jogadores = (await apiFetch("/players")) || [];
    const partidas = await apiFetch("/matches");
    if (!partidas) return;
    _partidas = partidas;

    const agora = new Date();
    const passada = (p) => new Date(p.data_hora) <= agora;
    // Jogo avulso não recebe placar: quando passa do horário vai direto ao histórico
    const aguardando = partidas.filter((p) => p.status === "agendado" && !p.avulso && passada(p));
    const proximas   = partidas.filter((p) => p.status === "agendado" && !passada(p));
    const historico  = partidas.filter((p) => p.status !== "agendado" || (p.avulso && passada(p)));

    let html = "";
    if (aguardando.length) {
      html += `<div class="card"><p class="card-titulo">Aguardando placar</p>${aguardando.map((p) => renderPartida(p, true)).join("")}</div>`;
    }
    if (proximas.length) {
      html += `<div class="card"><p class="card-titulo">Próximas partidas</p>${proximas.map((p) => renderPartida(p, false)).join("")}</div>`;
    }
    if (historico.length) {
      html += `<div class="card"><p class="card-titulo">Histórico</p>${historico.map((p) => renderPartida(p, false)).join("")}</div>`;
    }
    cont.innerHTML = html || "<div class='card'><p style='opacity:.5;font-size:.85rem'>Nenhuma partida encontrada.</p></div>";
  } catch {
    cont.innerHTML = "<p style='color:var(--cor-erro)'>Erro ao carregar partidas.</p>";
  }
}

async function cancelarPartida(matchId) {
  if (!confirm("Cancelar esta partida? O horário será liberado na agenda.")) return;
  try {
    await apiFetch(`/matches/${matchId}/cancelar-jogador`, { method: "POST" });
    carregarPartidas();
  } catch (e) {
    alert(e.message || "Erro ao cancelar partida.");
  }
}

function abrirFormPlacar(matchId) {
  _partidaSelecionada = _partidas.find((p) => p.id === matchId);
  if (!_partidaSelecionada) return;

  const nA = nomesLado(_partidaSelecionada, "A", _jogadores);
  const nB = nomesLado(_partidaSelecionada, "B", _jogadores);
  document.getElementById("placar-match-info").textContent =
    `${nA} vs ${nB} — ${fmtDataHora(_partidaSelecionada.data_hora)}`;
  document.getElementById("label-games-a").textContent = `Games — ${nA}`;
  document.getElementById("label-games-b").textContent = `Games — ${nB}`;
  document.getElementById("inp-games-a").value = 0;
  document.getElementById("inp-games-b").value = 0;
  document.getElementById("inp-tb-a").value = 0;
  document.getElementById("inp-tb-b").value = 0;
  document.getElementById("campo-tiebreak").hidden = true;
  document.getElementById("placar-erro").hidden = true;

  const form = document.getElementById("form-placar");
  form.hidden = false;
  form.scrollIntoView({ behavior: "smooth" });
}

// Mostra/oculta tiebreak quando ambos são 8
["inp-games-a", "inp-games-b"].forEach((id) => {
  document.getElementById(id)?.addEventListener("input", () => {
    const a = parseInt(document.getElementById("inp-games-a").value) || 0;
    const b = parseInt(document.getElementById("inp-games-b").value) || 0;
    document.getElementById("campo-tiebreak").hidden = !(a === 8 && b === 8);
  });
});

document.getElementById("btn-cancelar-placar")?.addEventListener("click", () => {
  document.getElementById("form-placar").hidden = true;
  _partidaSelecionada = null;
});

document.getElementById("btn-submeter-placar")?.addEventListener("click", async () => {
  if (!_partidaSelecionada) return;
  const gA = parseInt(document.getElementById("inp-games-a").value) || 0;
  const gB = parseInt(document.getElementById("inp-games-b").value) || 0;
  const isTb = gA === 8 && gB === 8;
  const tbA = isTb ? parseInt(document.getElementById("inp-tb-a").value) || 0 : null;
  const tbB = isTb ? parseInt(document.getElementById("inp-tb-b").value) || 0 : null;

  const btn   = document.getElementById("btn-submeter-placar");
  const erroEl = document.getElementById("placar-erro");
  btn.disabled = true;
  btn.textContent = "Enviando…";
  erroEl.hidden = true;

  try {
    await apiFetch(`/matches/${_partidaSelecionada.id}/placar`, {
      method: "POST",
      body: JSON.stringify({ games_a: gA, games_b: gB, tiebreak_a: tbA, tiebreak_b: tbB }),
    });
    document.getElementById("form-placar").hidden = true;
    _partidaSelecionada = null;
    await carregarPartidas();
  } catch (e) {
    erroEl.textContent = e.message.replace(/^Erro \d+: /, "");
    erroEl.hidden = false;
  } finally {
    btn.disabled = false;
    btn.textContent = "Confirmar";
  }
});

// ── Locação Avulsa ───────────────────────────────────────────────────────────

let _locPrecoHora = 0;
let _locSelecionado = null;

function locIrStep(n) {
  [1, 2, 3, 4].forEach(i => {
    document.getElementById(`loc-s${i}`).hidden = i !== n;
  });
}

function locInit() {
  const hoje = new Date().toISOString().slice(0, 10);
  document.getElementById("loc-data").value = hoje;
  const r1 = document.querySelector('input[name="loc-horas"][value="1"]');
  if (r1) r1.checked = true;
  _locSelecionado = null;
  _locPrecoHora = 0;
  locIrStep(1);
}

document.getElementById("btn-verificar-loc").addEventListener("click", async () => {
  const data = document.getElementById("loc-data").value;
  if (!data) return;
  const numHoras = parseInt(document.querySelector('input[name="loc-horas"]:checked').value, 10);

  const slotsEl = document.getElementById("loc-slots-list");
  slotsEl.innerHTML = '<p style="opacity:.6;font-size:.85rem">Verificando…</p>';
  locIrStep(2);

  try {
    const res = await fetch(`/api/v1/public/disponibilidade?data=${data}`);
    if (!res.ok) {
      const err = await res.json().catch(() => ({}));
      throw new Error(err.detail || "Erro ao buscar horários");
    }
    const d = await res.json();
    _locPrecoHora = d.preco_hora;

    const [ano, mes, dia] = data.split("-");
    document.getElementById("loc-data-label").textContent = `${dia}/${mes}/${ano}`;
    const total = (_locPrecoHora * numHoras).toFixed(2).replace(".", ",");
    document.getElementById("loc-preco-info").textContent =
      `R$ ${_locPrecoHora.toFixed(2).replace(".", ",")} /hora · ${numHoras}h = R$ ${total}`;

    // Horários de início onde numHoras consecutivas estão disponíveis
    const livres = new Set(
      (d.slots || []).filter(s => s.status === "disponivel").map(s => parseInt(s.hora_inicio))
    );
    const validos = (d.slots || []).filter(s => {
      const h = parseInt(s.hora_inicio);
      for (let i = 0; i < numHoras; i++) if (!livres.has(h + i)) return false;
      return true;
    });

    if (!validos.length) {
      slotsEl.innerHTML = '<p style="opacity:.6;font-size:.85rem">Nenhum horário disponível para esta duração.</p>';
      return;
    }

    slotsEl.innerHTML = validos.map(s => {
      const hFim = String(parseInt(s.hora_inicio) + numHoras).padStart(2, "0") + ":00";
      return `<button onclick="locSelecionarSlot('${data}','${s.hora_inicio}',${numHoras})"
        style="display:block;width:100%;text-align:left;padding:.65rem .85rem;margin-bottom:.4rem;
          border-radius:8px;border:1px solid rgba(40,160,80,.4);background:rgba(40,160,80,.1);
          font-size:.9rem;font-weight:500;cursor:pointer;color:inherit">
        ${s.hora_inicio} às ${hFim}
      </button>`;
    }).join("");

  } catch (e) {
    slotsEl.innerHTML = `<p style="color:var(--cor-erro);font-size:.85rem">Erro: ${e.message}</p>`;
  }
});

function locSelecionarSlot(data, hora, numHoras) {
  _locSelecionado = { data, hora, numHoras };
  const hFim = String(parseInt(hora) + numHoras).padStart(2, "0") + ":00";
  const [ano, mes, dia] = data.split("-");
  const total = (_locPrecoHora * numHoras).toFixed(2).replace(".", ",");
  document.getElementById("loc-s3-info").innerHTML =
    `<strong>${dia}/${mes}/${ano}</strong> · ${hora} às ${hFim}<br>` +
    `${numHoras}h · <strong>R$ ${total}</strong>`;
  document.getElementById("loc-s3-erro").hidden = true;
  const pixRadio = document.querySelector('input[name="loc-pagto"][value="pix"]');
  if (pixRadio) pixRadio.checked = true;
  locIrStep(3);
}

document.getElementById("btn-loc-confirmar").addEventListener("click", async () => {
  if (!_locSelecionado) return;
  const btn = document.getElementById("btn-loc-confirmar");
  btn.disabled = true;
  btn.textContent = "Aguarde…";

  const metodo = document.querySelector('input[name="loc-pagto"]:checked').value;
  const { data, hora, numHoras } = _locSelecionado;

  try {
    const resp = await apiFetch("/public/reserva", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        data,
        hora_inicio: hora,
        num_horas: numHoras,
        metodo_pagamento: metodo,
      }),
    });

    document.getElementById("loc-s4-msg").textContent = resp.msg;
    document.getElementById("loc-pix").hidden = true;
    document.getElementById("loc-cartao").hidden = true;

    if (metodo === "pix" && resp.pix_qrcode) {
      document.getElementById("loc-pix-qr").src = `data:image/png;base64,${resp.pix_qrcode}`;
      document.getElementById("loc-pix-chave").textContent = resp.pix_copia_cola || "";
      document.getElementById("btn-copiar-pix").onclick = () => {
        navigator.clipboard.writeText(resp.pix_copia_cola || "").then(() => {
          const b = document.getElementById("btn-copiar-pix");
          b.textContent = "Copiado!";
          setTimeout(() => { b.textContent = "Copiar código PIX"; }, 2000);
        });
      };
      document.getElementById("loc-pix").hidden = false;
    } else if (metodo === "cartao" && resp.invoice_url) {
      document.getElementById("loc-cartao-url").href = resp.invoice_url;
      document.getElementById("loc-cartao").hidden = false;
    }

    locIrStep(4);

  } catch (e) {
    const erroEl = document.getElementById("loc-s3-erro");
    erroEl.textContent = e.message.replace(/^Erro \d+: /, "");
    erroEl.hidden = false;
  } finally {
    btn.disabled = false;
    btn.textContent = "Confirmar";
  }
});

function locNovaReserva() {
  locInit();
}

// ── Service Worker ───────────────────────────────────────────────────────────
if ("serviceWorker" in navigator) {
  navigator.serviceWorker.register("/service-worker.js").catch(console.error);
}

// ── Boot ─────────────────────────────────────────────────────────────────────
if (Auth.isLoggedIn()) {
  showApp();
} else {
  showLogin();
}
