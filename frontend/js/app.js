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
async function carregarRanking() {
  const lista = document.getElementById("lista-ranking");
  lista.innerHTML = "<p style='opacity:.5;font-size:.85rem'>Carregando…</p>";
  try {
    const jogadores = await apiFetch("/players");
    if (!jogadores) return;
    if (!jogadores.length) {
      lista.innerHTML = "<p style='opacity:.5;font-size:.85rem'>Nenhum jogador cadastrado ainda.</p>";
      return;
    }
    lista.innerHTML = jogadores
      .map((j, i) => `
        <div class="ranking-item">
          <span class="ranking-pos">${i + 1}</span>
          ${avatarHtml(j)}
          <span style="flex:1">${j.apelido || j.nome}${j.status === "inativo" ? ' <span style="font-size:.65rem;background:rgba(200,80,30,.25);color:#e08050;padding:.1rem .35rem;border-radius:20px;vertical-align:middle">inativo</span>' : ""}</span>
          <span class="ranking-pts">${j.pontos_ranking_temporada_atual} pts</span>
        </div>`)
      .join("");
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

// ── Agendamento ──────────────────────────────────────────────────────────────
let _slots = [];
let _slotSelecionado = null;
let _jogadores = [];
let _me = null;

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
  const ladoA = jogadores.filter(j => j.lado === "A").map(j => j.apelido || j.nome.split(" ")[0]).join(" / ");
  const ladoB = jogadores.filter(j => j.lado === "B").map(j => j.apelido || j.nome.split(" ")[0]).join(" / ");
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

async function selecionarSlot(idx) {
  _slotSelecionado = _slots[idx];
  const tipo = document.querySelector('input[name="tipo-jogo"]:checked').value;

  if (!_me) _me = await apiFetch("/auth/me");
  if (!_jogadores.length) _jogadores = (await apiFetch("/players")) || [];

  const outros = _jogadores.filter((j) => j.id !== _me?.id);
  const toOpts = (excluir = []) =>
    outros.filter((j) => !excluir.includes(j.id))
      .map((j) => `<option value="${j.id}">${j.nome} · ${j.nivel === "nao_classificado" ? "Não class." : "Nível " + j.nivel}</option>`)
      .join("");

  document.getElementById("reserva-slot-info").textContent =
    `${fmtHora(_slotSelecionado.data_hora_inicio)} – ${fmtHora(_slotSelecionado.data_hora_fim)}`;

  document.getElementById("sel-adversario").innerHTML = toOpts();
  const isDuplas = tipo === "duplas";
  document.getElementById("campo-parceiro").hidden = !isDuplas;
  document.getElementById("campo-adversario2").hidden = !isDuplas;
  if (isDuplas) {
    document.getElementById("sel-parceiro").innerHTML = toOpts();
    document.getElementById("sel-adversario2").innerHTML = toOpts();
  }

  document.getElementById("reserva-erro").hidden = true;
  document.getElementById("form-reserva").hidden = false;
  document.getElementById("form-reserva").scrollIntoView({ behavior: "smooth" });
}

document.getElementById("btn-buscar-slots")?.addEventListener("click", buscarSlots);
document.getElementById("inp-data-jogo")?.addEventListener("keydown", (e) => {
  if (e.key === "Enter") buscarSlots();
});

document.getElementById("btn-cancelar-reserva")?.addEventListener("click", () => {
  document.getElementById("form-reserva").hidden = true;
  _slotSelecionado = null;
});

document.getElementById("btn-confirmar-reserva")?.addEventListener("click", async () => {
  if (!_slotSelecionado || !_me) return;

  const tipo = document.querySelector('input[name="tipo-jogo"]:checked').value;
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
      const j = jogadores.find((j) => j.id === p.player_id);
      return j ? j.nome.split(" ")[0] : `#${p.player_id}`;
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

  let statusCls, statusTxt, cardCls = "partida-card";
  if (aguardandoPlacar) {
    statusCls = "status-aguardando"; statusTxt = "Aguardando placar"; cardCls += " aguardando-placar";
  } else if (p.status === "agendado") {
    statusCls = "status-agendado"; statusTxt = "Agendado"; cardCls += " agendada";
  } else if (p.status === "realizado") {
    statusCls = "status-realizado"; statusTxt = "Realizado"; cardCls += " realizado";
  } else if (p.status === "wo") {
    statusCls = "status-wo"; statusTxt = "W.O."; cardCls += " cancelado";
  } else {
    statusCls = "status-cancelado"; statusTxt = "Cancelado"; cardCls += " cancelado";
  }

  const tipo = p.tipo === "simples" ? "Simples" : "Duplas";
  const vsHtml = p.placar
    ? `<div class="partida-placar">${nA} <span style="opacity:.45;font-weight:400">${placarStr(p.placar)}</span> ${nB}</div>`
    : `<div class="partida-jogadores">${nA} <span style="opacity:.35">vs</span> ${nB}</div>`;

  const btnHtml = aguardandoPlacar
    ? `<div style="text-align:center;margin-top:.5rem">
         <button class="btn btn-primario" style="font-size:.8rem;padding:.35rem .9rem"
                 onclick="abrirFormPlacar(${p.id})">Lançar placar</button>
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
    const aguardando = partidas.filter((p) => p.status === "agendado" && new Date(p.data_hora) <= agora);
    const proximas   = partidas.filter((p) => p.status === "agendado" && new Date(p.data_hora) >  agora);
    const historico  = partidas.filter((p) => p.status !== "agendado");

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
