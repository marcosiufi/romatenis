const API = "/api/v1";

// ── Estado comercial (pré-lançamento) ────────────────────────────────────────
// Cacheado após a primeira busca. Enquanto não chega, assume tudo habilitado —
// o backend é a autoridade e responde 403 com a mensagem configurada.
let _empresa = null;

async function getEmpresa() {
  if (_empresa) return _empresa;
  _empresa = await fetch("/api/v1/public/empresa")
    .then((r) => (r.ok ? r.json() : null))
    .catch(() => null);
  return _empresa;
}

/** Mostra o aviso de "ainda não abrimos" no elemento indicado. */
async function aplicarAvisoComercial(elId, chaveAtiva, chaveMsg) {
  const el = document.getElementById(elId);
  if (!el) return true;
  const e = await getEmpresa();
  const ativo = e?.[chaveAtiva] !== false;
  el.textContent = ativo ? "" : (e?.[chaveMsg] || "");
  el.hidden = ativo;
  return ativo;
}

// ── Escape de HTML ───────────────────────────────────────────────────────────
// Nome, apelido, e-mail, endereço e afins são texto livre do usuário e chegam
// da API sem sanitização. Sempre passar por esc() antes de interpolar em
// innerHTML — inclusive dentro de atributos, por causa das aspas.
function esc(s) {
  return String(s ?? "").replace(/[&<>"']/g, (c) =>
    ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
}

// ── Interface: alerta, confirmação, faixa e folhas ──────────────────────────
// Substituem alert() e confirm(): os do navegador aparecem como "localhost
// diz…", não seguem a aparência do app e travam a página inteira.

const ICONE_OK = `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><circle cx="12" cy="12" r="9.5"/><path d="M7.8 12.3l2.8 2.8 5.6-6"/></svg>`;
const ICONE_ERRO = `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><circle cx="12" cy="12" r="9.5"/><path d="M12 7.5v5.5"/><path d="M12 16.5h.01"/></svg>`;
const ICONE_AVISO = `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.9" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M10.3 4.2 2.6 17.6A2 2 0 0 0 4.3 20.6h15.4a2 2 0 0 0 1.7-3L13.7 4.2a2 2 0 0 0-3.4 0z"/><path d="M12 9.5v4"/><path d="M12 17h.01"/></svg>`;

/** Alerta no desenho do iOS. Resolve com o `valor` do botão tocado. */
function alertar({ titulo, mensagem = "", botoes = [{ rotulo: "OK", valor: true, forte: true }] }) {
  return new Promise((resolver) => {
    const raiz = document.getElementById("raiz-alerta");
    const anterior = document.activeElement;
    // Botões lado a lado só quando são dois e curtos, como no iOS
    const empilhar = botoes.length > 2 || botoes.some((b) => b.rotulo.length > 13);
    raiz.innerHTML = `
      <div class="alerta-fundo">
        <div class="alerta" role="alertdialog" aria-modal="true" aria-labelledby="alerta-t"${mensagem ? ' aria-describedby="alerta-m"' : ""}>
          <div class="alerta-texto">
            <p class="alerta-titulo" id="alerta-t">${esc(titulo)}</p>
            ${mensagem ? `<p class="alerta-msg" id="alerta-m">${esc(mensagem)}</p>` : ""}
          </div>
          <div class="alerta-botoes${empilhar ? " empilhados" : ""}">
            ${botoes.map((b, i) => `<button type="button" data-i="${i}" class="${b.forte ? "forte" : ""}${b.perigo ? " perigo" : ""}">${esc(b.rotulo)}</button>`).join("")}
          </div>
        </div>
      </div>`;
    const tecla = (e) => {
      if (e.key !== "Escape") return;
      e.stopPropagation();
      const cancelar = botoes.find((b) => b.cancelar);
      fechar(cancelar ? cancelar.valor : false);
    };
    function fechar(valor) {
      raiz.innerHTML = "";
      document.removeEventListener("keydown", tecla, true);
      anterior?.focus?.();
      resolver(valor);
    }
    raiz.querySelectorAll("button[data-i]").forEach((btn) => {
      btn.addEventListener("click", () => fechar(botoes[+btn.dataset.i].valor));
    });
    document.addEventListener("keydown", tecla, true);
    (raiz.querySelector("button.forte") || raiz.querySelector("button"))?.focus();
  });
}

/** Confirmação com a ação nomeada. A destrutiva sai em vermelho e, como
 *  manda a Apple, o botão de recuar fica em destaque. */
function confirmar(titulo, mensagem, { acao = "Confirmar", perigo = false, voltar = "Cancelar" } = {}) {
  return alertar({
    titulo, mensagem,
    botoes: [
      { rotulo: voltar, valor: false, cancelar: true, forte: perigo },
      { rotulo: acao, valor: true, forte: !perigo, perigo },
    ],
  });
}

/** Faixa no topo da tela, como um banner do iOS. Some sozinha. */
let _faixaTimer = null;
function avisar(texto, { erro = false } = {}) {
  const el = document.getElementById("faixa");
  if (!el) return;
  el.className = `faixa${erro ? " erro" : ""}`;
  el.innerHTML = `${erro ? ICONE_ERRO : ICONE_OK}<span>${esc(texto)}</span>`;
  requestAnimationFrame(() => requestAnimationFrame(() => el.classList.add("visivel")));
  clearTimeout(_faixaTimer);
  _faixaTimer = setTimeout(() => el.classList.remove("visivel"), erro ? 4500 : 2400);
}

/** Folhas: abrem e fecham alternando `hidden`. A trava de rolagem do fundo
 *  é CSS puro (`body:has(.folha-fundo:not([hidden]))`). */
function abrirFolha(id) {
  const f = document.getElementById(id);
  if (!f) return;
  f.hidden = false;
  f.querySelector(".folha-corpo")?.scrollTo(0, 0);
}
function fecharFolha(id) {
  const f = document.getElementById(id);
  if (f) f.hidden = true;
}
// Toque no véu fora da folha e Esc fecham a folha de cima — pelo botão
// "Cancelar" dela, para a limpeza de estado de cada fluxo rodar igual.
document.addEventListener("click", (e) => {
  if (e.target.classList?.contains("folha-fundo")) {
    e.target.querySelector(".folha-barra button")?.click();
  }
});
document.addEventListener("keydown", (e) => {
  if (e.key === "Escape" && !document.querySelector(".alerta-fundo")) {
    const abertas = [...document.querySelectorAll(".folha-fundo:not([hidden])")];
    abertas.at(-1)?.querySelector(".folha-barra button")?.click();
  }
  // Linha tocável (role=button) responde ao Enter e ao espaço, como um botão
  if ((e.key === "Enter" || e.key === " ") && e.target.matches?.('[role="button"][onclick]')) {
    e.preventDefault();
    e.target.click();
  }
});

/** Estados de carregamento, erro e vazio — o mesmo desenho em todas as telas. */
const carregandoHtml = () => '<div class="carregando" role="status" aria-label="Carregando"></div>';
function erroHtml(texto) {
  return `<div class="vazio">${ICONE_ERRO}<p class="vazio-titulo">Não foi possível carregar</p><p class="vazio-texto">${esc(texto)}</p></div>`;
}
function vazioHtml(icone, titulo, texto) {
  return `<div class="vazio">${icone}<p class="vazio-titulo">${esc(titulo)}</p><p class="vazio-texto">${esc(texto)}</p></div>`;
}
function avisoHtml(conteudo, tom = "") {
  return `<div class="aviso${tom ? " a-" + tom : ""}">${tom === "critico" ? ICONE_ERRO : ICONE_AVISO}<div>${conteudo}</div></div>`;
}

// ── Datas, valores e documentos ──────────────────────────────────────────────
const FUSO = "America/Sao_Paulo";
const _primeiraMaiuscula = (t) => t.charAt(0).toUpperCase() + t.slice(1);
/** "21 de out." */
function fmtDiaMes(iso, utc = false) {
  return new Date(iso).toLocaleDateString("pt-BR", { day: "numeric", month: "short", timeZone: utc ? "UTC" : FUSO });
}
/** "21 de outubro de 2026" */
function fmtDataLonga(iso) {
  return new Date(iso).toLocaleDateString("pt-BR", { day: "numeric", month: "long", year: "numeric", timeZone: FUSO });
}
function fmtCPF(c) {
  const d = String(c || "").replace(/\D/g, "");
  return d.length === 11 ? `${d.slice(0, 3)}.${d.slice(3, 6)}.${d.slice(6, 9)}-${d.slice(9)}` : (c || "");
}
function fmtTelefone(t) {
  const d = String(t || "").replace(/\D/g, "");
  if (d.length === 11) return `(${d.slice(0, 2)}) ${d.slice(2, 7)}-${d.slice(7)}`;
  if (d.length === 10) return `(${d.slice(0, 2)}) ${d.slice(2, 6)}-${d.slice(6)}`;
  return t || "";
}

// ── Desenhos da marca ────────────────────────────────────────────────────────
// A quadra em escala real (23,77 × 10,97 m) — o único ornamento do sistema,
// só em superfície de marca. E o logotipo, para o passe da assinatura.
const SVG_QUADRA = `<div class="quadra" aria-hidden="true"><svg viewBox="-40 -40 2457 1177" fill="none" stroke="currentColor" stroke-width="1.25"><rect x="0" y="0" width="2377" height="1097"/><line x1="0" y1="137" x2="2377" y2="137"/><line x1="0" y1="960" x2="2377" y2="960"/><line x1="1188.5" y1="-30" x2="1188.5" y2="1127"/><line x1="548.5" y1="137" x2="548.5" y2="960"/><line x1="1828.5" y1="137" x2="1828.5" y2="960"/><line x1="548.5" y1="548.5" x2="1828.5" y2="548.5"/><line x1="0" y1="548.5" x2="15" y2="548.5"/><line x1="2362" y1="548.5" x2="2377" y2="548.5"/></svg></div>`;
const SVG_LOGO = `<svg class="logo" viewBox="0 0 300 105" role="img" aria-label="Roma Tênis"><text x="150" y="68" text-anchor="middle" font-family="Cinzel, Georgia, serif" font-size="62" font-weight="700" letter-spacing="8" fill="currentColor">ROMA</text><line class="logo-traco" x1="106" y1="82" x2="194" y2="82" stroke-width="1.5"/><text class="logo-acento" x="150" y="102" text-anchor="middle" font-family="-apple-system, 'Inter Variable', 'Segoe UI', sans-serif" font-size="15" font-weight="500" letter-spacing="7">TÊNIS</text></svg>`;

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

// O título grande rola com a página; quando passa por baixo da barra de
// navegação, a barra ganha o material e mostra o título pequeno no centro.
let _observaTitulo = null;
function _observarTitulo(tela) {
  const barra = document.getElementById("barra-nav");
  if (!barra) return;
  if (!_observaTitulo) {
    _observaTitulo = new IntersectionObserver(
      ([e]) => barra.classList.toggle("rolada", !e.isIntersecting),
      { rootMargin: `-${barra.offsetHeight}px 0px 0px 0px` },
    );
  }
  _observaTitulo.disconnect();
  barra.classList.remove("rolada");
  const titulo = tela?.querySelector(".titulo-grande");
  if (titulo) _observaTitulo.observe(titulo);
}

function mostrarTela(id) {
  telas.forEach((t) => t.classList.toggle("ativa", t.id === id));
  navLinks.forEach((a) => {
    const ativo = a.dataset.tela === id;
    a.classList.toggle("ativo", ativo);
    if (ativo) a.setAttribute("aria-current", "page"); else a.removeAttribute("aria-current");
  });
  const tela = document.getElementById(id);
  document.getElementById("barra-nav-titulo").textContent = tela?.dataset.titulo || "";
  window.scrollTo(0, 0);
  _observarTitulo(tela);

  if (id === "tela-ranking")  carregarRanking();
  if (id === "tela-perfil")   carregarPerfil();
  if (id === "tela-partidas") carregarPartidas();
  if (id === "tela-agendar") {
    carregarUsoSemanal();
    aplicarAvisoComercial("aviso-reservas-agendar", "reservas_ativas", "msg_reservas_desabilitado");
  }
  if (id === "tela-locacao") {
    locInit();
    aplicarAvisoComercial("aviso-reservas-locacao", "reservas_ativas", "msg_reservas_desabilitado");
  }
}

navLinks.forEach((a) => {
  a.addEventListener("click", (e) => {
    e.preventDefault();
    // Tocar na aba já aberta volta ao topo, como no iOS
    if (a.classList.contains("ativo")) { window.scrollTo({ top: 0, behavior: "smooth" }); return; }
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
  _eu = null;
}

// ── Login ────────────────────────────────────────────────────────────────────
// Administrador entra em duas etapas: senha e um código de 6 dígitos que chega
// por e-mail. O aparelho em que o código foi confirmado fica dispensado por
// 30 dias (dispositivo_token). Associado comum entra direto.
let _desafioLogin = null;

function _mostrarEtapaCodigo(enviadoPara) {
  const pedindo = !!enviadoPara;
  document.getElementById("campos-senha").hidden = pedindo;
  document.getElementById("campo-codigo").hidden = !pedindo;
  document.getElementById("btn-voltar-senha").hidden = !pedindo;
  document.getElementById("login-codigo-ajuda").textContent = pedindo
    ? `Enviamos um código de 6 dígitos para ${enviadoPara}. Ele vale por 10 minutos.`
    : "";
  document.getElementById("login-erro").hidden = true;
  if (pedindo) {
    const campo = document.getElementById("inp-codigo");
    campo.value = "";
    setTimeout(() => campo.focus(), 50);
  } else {
    _desafioLogin = null;
  }
}

document.getElementById("form-login").addEventListener("submit", async (e) => {
  e.preventDefault();
  const erroEl = document.getElementById("login-erro");
  const btn    = e.target.querySelector("button[type=submit]");
  const pedindoCodigo = !document.getElementById("campo-codigo").hidden;
  erroEl.hidden = true;
  btn.disabled  = true;
  btn.textContent = "Entrando…";

  try {
    const res = pedindoCodigo
      ? await fetch(API + "/auth/login/codigo", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            desafio: _desafioLogin,
            codigo: document.getElementById("inp-codigo").value.replace(/\D/g, ""),
          }),
        })
      : await fetch(API + "/auth/login", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            email: document.getElementById("inp-email").value,
            senha: document.getElementById("inp-senha").value,
            dispositivo_token: localStorage.getItem("dispositivo_token") || null,
          }),
        });

    const data = await res.json().catch(() => ({}));
    if (!res.ok) throw new Error(data.detail || "Erro ao entrar");

    if (data.requer_codigo) {
      _desafioLogin = data.desafio;
      _mostrarEtapaCodigo(data.enviado_para);
      return;
    }
    if (data.dispositivo_token) localStorage.setItem("dispositivo_token", data.dispositivo_token);
    Auth.save(data);
    _mostrarEtapaCodigo(null);
    showApp();
  } catch (err) {
    erroEl.textContent = err.message;
    erroEl.hidden = false;
  } finally {
    btn.disabled    = false;
    btn.textContent = "Entrar";
  }
});

// ── Sair ─────────────────────────────────────────────────────────────────────
async function sair() {
  const ok = await confirmar(
    "Sair da conta?",
    "Para voltar, você entra de novo com seu e-mail e senha.",
    { acao: "Sair", perigo: true },
  );
  if (!ok) return;
  Auth.clear();
  showLogin();
}

// A pessoa logada — para destacar "Você" no ranking e montar as reservas
let _eu = null;
async function _carregarEu() {
  if (!_eu) _eu = await apiFetch("/auth/me").catch(() => null);
  return _eu;
}

// ── Avatar helper ─────────────────────────────────────────────────────────────
function avatarHtml(jogador, extraClass = "") {
  const iniciais = jogador.nome.trim().split(/\s+/).filter(Boolean)
    .slice(0, 2).map(n => n[0].toUpperCase()).join("");
  if (jogador.foto_url) {
    return `<div class="avatar${extraClass}"><img src="${esc(jogador.foto_url)}" alt="${esc(jogador.nome)}" loading="lazy" /></div>`;
  }
  return `<div class="avatar${extraClass}">${esc(iniciais)}</div>`;
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
const ICONE_TROFEU = `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M7.5 4h9v6.5a4.5 4.5 0 0 1-9 0V4z"/><path d="M7.5 6.5H5a.5.5 0 0 0-.5.5 3 3 0 0 0 3 3"/><path d="M16.5 6.5H19a.5.5 0 0 1 .5.5 3 3 0 0 1-3 3"/><path d="M12 15v3.5"/><path d="M8.5 20h7"/></svg>`;

function _fmtDataTemporada(iso) {
  return new Date(iso).toLocaleDateString("pt-BR", { day: "2-digit", month: "2-digit", year: "numeric", timeZone: "UTC" });
}

async function carregarRanking() {
  const lista    = document.getElementById("lista-ranking");
  const infoEl   = document.getElementById("ranking-temporada-info");
  const anterEl  = document.getElementById("ranking-anteriores");
  if (!lista.innerHTML.trim()) lista.innerHTML = carregandoHtml();

  try {
    const [jogadores, temporadas, eu] = await Promise.all([
      apiFetch("/players"),
      fetch("/api/v1/public/temporadas").then(r => r.ok ? r.json() : null).catch(() => null),
      _carregarEu(),
    ]);

    if (infoEl) {
      const t = temporadas?.ativa;
      infoEl.textContent = t
        ? `Temporada de ${fmtDiaMes(t.data_inicio, true)} a ${fmtDiaMes(t.data_fim, true)}`
        : "";
    }

    if (!jogadores?.length) {
      lista.innerHTML = vazioHtml(ICONE_TROFEU, "Classificação vazia", "Os associados aparecem aqui assim que a temporada começar.");
    } else {
      lista.innerHTML = jogadores.map((j, i) => {
        const souEu = eu && j.id === eu.id;
        return `
          <div class="linha com-posicao ranking-item${i < 3 ? " podio" : ""}${souEu ? " eu" : ""}">
            <span class="ranking-pos">${i + 1}</span>
            ${avatarHtml(j)}
            <span class="linha-texto ranking-nome">
              <span class="linha-titulo">${esc(j.apelido || j.nome)}</span>
              ${souEu ? '<span class="etiqueta e-tint">Você</span>' : ""}
              ${j.status === "inativo" ? '<span class="etiqueta">Inativo</span>' : ""}
            </span>
            <span class="ranking-pts">${j.pontos_ranking_temporada_atual}<small>pts</small></span>
          </div>`;
      }).join("");
    }

    if (anterEl) {
      const encerradas = temporadas?.encerradas?.filter(s => s.top2?.length) ?? [];
      const cabecalho = encerradas.length
        ? `<h2 class="grupo-cabecalho">${encerradas.length === 1 ? "Temporada anterior" : "Temporadas anteriores"}</h2>`
        : "";
      anterEl.innerHTML = cabecalho + encerradas.map((s) => `
        <div class="grupo">
          ${s.top2.map(p => `
            <div class="linha ranking-item podio">
              <span class="ranking-pos">${p.posicao}º</span>
              <span class="linha-texto"><span class="linha-titulo">${esc(p.nome)}</span></span>
              <span class="ranking-pts">${p.pontos}<small>pts</small></span>
            </div>`).join("")}
        </div>
        <p class="grupo-rodape">De ${fmtDiaMes(s.data_inicio, true)} a ${fmtDiaMes(s.data_fim, true)}.</p>`).join("");
    }
  } catch (e) {
    lista.innerHTML = erroHtml(e.message || "Verifique sua conexão e tente de novo.");
  }
}

// ── Perfil ───────────────────────────────────────────────────────────────────
const PLANO_LABEL = { mensal: "Mensal", trimestral: "Trimestral", semestral: "Semestral", anual: "Anual" };
const PLANO_MESES = { mensal: 30, trimestral: 90, semestral: 180, anual: 365 };

// Situação no passe da assinatura: rótulo e tom da etiqueta. Sem cor aqui —
// o tom vira classe, e a classe lê os tokens da aparência.
const ESTADO_SUB = {
  pendente:     { rotulo: "Aguardando ativação", tom: "alerta" },
  ativa:        { rotulo: "Ativa",               tom: "" },
  pausada:      { rotulo: "Pausada",             tom: "alerta" },
  expirada:     { rotulo: "Expirada",            tom: "critico" },
  inadimplente: { rotulo: "Pagamento pendente",  tom: "critico" },
  cancelada:    { rotulo: "Cancelada",           tom: "critico" },
};

const _icone = (d) => `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">${d}</svg>`;
const ICONE_RENOVAR = _icone('<path d="M20 11a8 8 0 1 0-2.3 5.7"/><path d="M20 5v6h-6"/>');
const ICONE_PAUSA   = _icone('<path d="M9 6v12M15 6v12"/>');
const ICONE_CHAVE   = _icone('<circle cx="8" cy="15" r="4"/><path d="M11 12l9-9M17 6l3 3M14 9l2 2"/>');
const ICONE_FILA    = _icone('<path d="M8 6h12M8 12h12M8 18h12"/><path d="M4 6h.01M4 12h.01M4 18h.01"/>');

// ── Pagamentos: o histórico no desenho do Wallet ─────────────────────────────
// Ícone redondo da categoria, o que foi pago, a data; à direita o valor e,
// embaixo dele, como foi pago — ou a situação, quando ainda não foi.
const _PAG_ICONE = {
  plano:   _icone('<rect x="3" y="5.5" width="18" height="13" rx="2.5"/><path d="M3 10h18"/><path d="M7 14.5h4"/>'),
  locacao: _icone('<rect x="3" y="6" width="18" height="12" rx="1.5"/><path d="M12 6v12M3 9h18M3 15h18"/>'),
  avulso:  _icone('<circle cx="12" cy="12" r="8"/><path d="M6.6 6.4c2.2 1.5 3.4 3.3 3.4 5.6s-1.2 4.1-3.4 5.6M17.4 6.4c-2.2 1.5-3.4 3.3-3.4 5.6s1.2 4.1 3.4 5.6"/>'),
  outro:   _icone('<circle cx="12" cy="12" r="8"/><path d="M12 8v8M8 12h8"/>'),
};
const _PAG_METODO = { pix: "PIX", cartao: "Cartão", boleto: "Boleto" };
const _PAG_SITUACAO = {
  pendente:  '<small class="pendente">Pendente</small>',
  falhou:    '<small class="falhou">Não aprovado</small>',
  estornado: "<small>Estornado</small>",
};

function _dataCurta(iso) {
  const d = new Date(iso);
  const outroAno = d.getFullYear() !== new Date().getFullYear();
  return d.toLocaleDateString("pt-BR", { day: "numeric", month: "short", ...(outroAno ? { year: "numeric" } : {}), timeZone: FUSO });
}

function _pagamentoLinha(t) {
  const riscado = t.status === "estornado" || t.status === "falhou";
  const embaixo = _PAG_SITUACAO[t.status] || `<small>${esc(_PAG_METODO[t.metodo] || "")}</small>`;
  const cupom = t.cupom ? `, cupom ${esc(t.cupom)}` : "";
  return `
    <div class="linha com-icone">
      <span class="icone-quadro redondo ${riscado ? "esmaecido" : `cat-${esc(t.categoria)}`}">${_PAG_ICONE[t.categoria] || _PAG_ICONE.outro}</span>
      <span class="linha-texto">
        <span class="linha-titulo">${esc(t.titulo)}</span>
        <span class="linha-sub">${esc(_dataCurta(t.data))}${cupom}</span>
      </span>
      <span class="transacao-valor${riscado ? " estornado" : ""}">${fmtBRL(t.valor)}${embaixo}</span>
    </div>`;
}

/** Os pendentes primeiro — são os que pedem ação —, depois do mais novo ao mais antigo */
function _ordenarPagamentos(lista) {
  return [...lista].sort((a, b) =>
    (b.status === "pendente") - (a.status === "pendente") || new Date(b.data) - new Date(a.data));
}

function _pagamentosHtml(lista) {
  if (!lista?.length) return "";
  const ordem = _ordenarPagamentos(lista);
  const VISIVEIS = 4;
  return `
    <div class="grupo-cabecalho">
      <span>Pagamentos</span>
      ${ordem.length > VISIVEIS ? `<button type="button" class="btn btn-texto" onclick="abrirFolha('folha-pagamentos')">Ver todos</button>` : ""}
    </div>
    <div class="grupo">${ordem.slice(0, VISIVEIS).map(_pagamentoLinha).join("")}</div>`;
}

/** A folha com o histórico inteiro, separado por mês */
function _folhaPagamentosHtml(lista) {
  if (!lista?.length) return "";
  const meses = new Map();
  for (const t of _ordenarPagamentos(lista)) {
    const chave = t.status === "pendente" ? "Pendentes"
      : _primeiraMaiuscula(new Date(t.data).toLocaleDateString("pt-BR", { month: "long", year: "numeric", timeZone: FUSO }));
    if (!meses.has(chave)) meses.set(chave, []);
    meses.get(chave).push(t);
  }
  const grupos = [...meses].map(([mes, itens]) => `
    <h2 class="grupo-cabecalho">${esc(mes)}</h2>
    <div class="grupo">${itens.map(_pagamentoLinha).join("")}</div>`).join("");
  return `
    <div id="folha-pagamentos" class="folha-fundo" hidden>
      <div class="folha" role="dialog" aria-modal="true" aria-labelledby="t-pagamentos">
        <div class="folha-barra">
          <span></span>
          <p class="folha-titulo" id="t-pagamentos">Pagamentos</p>
          <button type="button" class="btn btn-texto forte" onclick="fecharFolha('folha-pagamentos')">OK</button>
        </div>
        <div class="folha-corpo">
          ${grupos}
          <p class="grupo-rodape">Planos, locações e jogos avulsos pelos quais você respondeu.</p>
        </div>
      </div>
    </div>`;
}

function fmtData(isoStr) {
  return new Date(isoStr).toLocaleDateString("pt-BR", { timeZone: FUSO });
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

function _temEndereco(p) {
  return !!(p.rua || p.cidade || p.bairro || p.cep);
}

/** Endereço em até três linhas, como num envelope. */
function _enderecoTexto(p) {
  const l1 = [p.rua, p.numero].filter(Boolean).join(", ") + (p.complemento ? `, ${p.complemento}` : "");
  const l2 = [p.bairro, [p.cidade, p.estado].filter(Boolean).join(" – ")].filter(Boolean).join(", ");
  return [l1, l2, p.cep].filter(Boolean).map(esc).join("<br>");
}

/** A assinatura como um passe do Wallet: superfície de marca, linhas da
 *  quadra, o plano e quanto falta. As ações ficam numa lista logo abaixo. */
function _passeHtml(sub, pixPendente) {
  const est  = ESTADO_SUB[sub.status] || ESTADO_SUB.cancelada;
  const pct  = _subProgressPct(sub);
  const dias = _diasRestantes(sub);
  const podePausar  = sub.status === "ativa" && dias > 0 && sub.plano !== "mensal";
  const podeRenovar = ["expirada", "inadimplente", "cancelada"].includes(sub.status)
    || (sub.status === "ativa" && dias <= 7);

  let extras = "";
  if (sub.status === "pausada" && sub.data_retorno_prevista) {
    extras += avisoHtml(`Plano pausado. O retorno está previsto para <strong>${fmtDataLonga(sub.data_retorno_prevista)}</strong>.`, "tint");
  }
  if (pixPendente?.pix_copia_e_cola) {
    extras += `
      <div class="card">
        <p class="card-titulo">Pagamento pendente</p>
        <p class="card-sub">Copie o código e pague no app do seu banco. A confirmação chega em instantes.</p>
        <div class="pix-row">
          <input id="pix-code-input" class="pix-code" readonly value="${esc(pixPendente.pix_copia_e_cola)}" aria-label="Código PIX" />
          <button class="btn btn-primario pix-copy-btn" onclick="copiarPixJogador()">Copiar</button>
        </div>
        ${pixPendente.payment_link ? `<a href="${esc(pixPendente.payment_link)}" target="_blank" rel="noopener" class="pix-link">Abrir a cobrança</a>` : ""}
      </div>`;
  }

  const acoes = [
    podeRenovar ? `
      <button type="button" class="linha linha-nav com-icone" onclick="abrirRenovarUI('Renovar plano')">
        <span class="icone-quadro q-tint">${ICONE_RENOVAR}</span>
        <span class="linha-texto"><span class="linha-titulo">Renovar plano</span></span>
      </button>` : "",
    podePausar ? `
      <button type="button" class="linha linha-nav com-icone" onclick="abrirPausaUI()">
        <span class="icone-quadro">${ICONE_PAUSA}</span>
        <span class="linha-texto">
          <span class="linha-titulo">Pedir pausa</span>
          <span class="linha-sub">Até 15 dias, em planos de 3 meses ou mais</span>
        </span>
      </button>` : "",
  ].filter(Boolean).join("");

  return `
    <div class="passe">
      ${SVG_QUADRA}
      <div class="passe-topo">${SVG_LOGO}<span class="passe-estado ${est.tom}">${est.rotulo}</span></div>
      <p class="passe-rotulo">Plano</p>
      <p class="passe-plano">${PLANO_LABEL[sub.plano] || esc(sub.plano)}</p>
      <div class="passe-barra" role="progressbar" aria-label="Tempo do plano já usado"
           aria-valuenow="${pct}" aria-valuemin="0" aria-valuemax="100"><div style="width:${pct}%"></div></div>
      <div class="passe-rodape">
        <span>Vence em <strong>${fmtDiaMes(sub.data_expiracao)}</strong></span>
        <span>${dias > 0 ? `Faltam <strong>${dias} ${dias === 1 ? "dia" : "dias"}</strong>` : "<strong>Vencido</strong>"}</span>
      </div>
    </div>
    ${extras}
    ${acoes ? `<div class="grupo">${acoes}</div>` : ""}`;
}

/** Linha de dado: rótulo à esquerda, valor à direita, como nos Contatos. */
function _linhaDado(rotulo, valorHtml) {
  if (!valorHtml) return "";
  return `<div class="linha"><span class="linha-texto"><span class="linha-titulo">${rotulo}</span></span><span class="linha-valor">${valorHtml}</span></div>`;
}

const _hojeBR = () => new Date().toLocaleDateString("sv-SE", { timeZone: FUSO });

/** As folhas do perfil: dados, senha, plano e pausa. Os IDs dos campos são
 *  os mesmos de antes — as funções de salvar não mudaram. */
function _folhasPerfilHtml(p) {
  const v = (x) => esc(x ?? "");
  return `
    <div id="folha-editar" class="folha-fundo" hidden>
      <div class="folha" role="dialog" aria-modal="true" aria-labelledby="t-editar">
        <div class="folha-barra">
          <button type="button" class="btn btn-texto" onclick="fecharEdicaoPerfil()">Cancelar</button>
          <p class="folha-titulo" id="t-editar">Dados pessoais</p>
          <button type="button" class="btn btn-texto forte" onclick="salvarDadosPerfil()">Salvar</button>
        </div>
        <div class="folha-corpo">
          <div class="card">
            <div class="campo"><label for="edit-nome">Nome completo</label><input type="text" id="edit-nome" autocomplete="name" value="${v(p.nome)}" /></div>
            <div class="campo"><label for="edit-apelido">Apelido</label><input type="text" id="edit-apelido" value="${v(p.apelido)}" placeholder="Opcional, aparece no ranking" /></div>
            <div class="campo"><label for="edit-email">E-mail</label><input type="email" id="edit-email" autocomplete="email" inputmode="email" autocapitalize="none" value="${v(p.email)}" /></div>
            <div class="campo"><label for="edit-telefone">Telefone</label><input type="tel" id="edit-telefone" autocomplete="tel" value="${v(p.telefone)}" placeholder="16 99123-4567" /></div>
            <div class="grade-2">
              <div class="campo"><label for="edit-cpf">CPF</label><input type="text" id="edit-cpf" inputmode="numeric" value="${v(p.cpf)}" placeholder="000.000.000-00" maxlength="14" /></div>
              <div class="campo"><label for="edit-nascimento">Nascimento</label><input type="date" id="edit-nascimento" value="${v(p.data_nascimento)}" /></div>
            </div>
          </div>
          <h2 class="grupo-cabecalho">Endereço</h2>
          <div class="card">
            <div class="campo"><label for="edit-rua">Logradouro</label><input type="text" id="edit-rua" autocomplete="address-line1" value="${v(p.rua)}" /></div>
            <div class="grade-2">
              <div class="campo"><label for="edit-numero">Número</label><input type="text" id="edit-numero" value="${v(p.numero)}" /></div>
              <div class="campo"><label for="edit-complemento">Complemento</label><input type="text" id="edit-complemento" autocomplete="address-line2" value="${v(p.complemento)}" /></div>
            </div>
            <div class="campo"><label for="edit-bairro">Bairro</label><input type="text" id="edit-bairro" value="${v(p.bairro)}" /></div>
            <div class="grade-uf">
              <div class="campo"><label for="edit-cidade">Cidade</label><input type="text" id="edit-cidade" autocomplete="address-level2" value="${v(p.cidade)}" /></div>
              <div class="campo"><label for="edit-estado">UF</label><input type="text" id="edit-estado" class="maiusculo" autocomplete="address-level1" value="${v(p.estado)}" maxlength="2" /></div>
            </div>
            <div class="grade-2">
              <div class="campo"><label for="edit-cep">CEP</label><input type="text" id="edit-cep" inputmode="numeric" autocomplete="postal-code" value="${v(p.cep)}" maxlength="9" /></div>
              <div class="campo"><label for="edit-pais">País</label><input type="text" id="edit-pais" autocomplete="country-name" value="${v(p.pais)}" /></div>
            </div>
          </div>
          <p id="edit-perfil-erro" class="erro" hidden></p>
        </div>
      </div>
    </div>

    <div id="folha-senha" class="folha-fundo" hidden>
      <div class="folha" role="dialog" aria-modal="true" aria-labelledby="t-senha">
        <div class="folha-barra">
          <button type="button" class="btn btn-texto" onclick="fecharAlterarSenha()">Cancelar</button>
          <p class="folha-titulo" id="t-senha">Alterar senha</p>
          <button type="button" class="btn btn-texto forte" onclick="confirmarAlterarSenha()">Salvar</button>
        </div>
        <div class="folha-corpo">
          <div class="card">
            <div class="campo"><label for="senha-atual">Senha atual</label><input type="password" id="senha-atual" autocomplete="current-password" /></div>
            <div class="campo"><label for="senha-nova">Nova senha</label><input type="password" id="senha-nova" autocomplete="new-password" /></div>
            <div class="campo"><label for="senha-confirma">Repita a nova senha</label><input type="password" id="senha-confirma" autocomplete="new-password" /></div>
          </div>
          <p class="grupo-rodape">Use pelo menos 6 caracteres.</p>
          <p id="senha-erro" class="erro" hidden></p>
        </div>
      </div>
    </div>

    <div id="folha-renovar" class="folha-fundo" hidden>
      <div class="folha" role="dialog" aria-modal="true" aria-labelledby="renovar-titulo">
        <div class="folha-barra">
          <button type="button" class="btn btn-texto" onclick="fecharRenovarUI()">Cancelar</button>
          <p class="folha-titulo" id="renovar-titulo">Contratar plano</p>
          <span></span>
        </div>
        <div class="folha-corpo">
          <div class="card">
            <div class="campo">
              <label for="renovar-plano">Plano</label>
              <select id="renovar-plano" onchange="atualizarFormasPagamento()">
                <option value="mensal">Mensal</option>
                <option value="trimestral">Trimestral</option>
                <option value="semestral">Semestral</option>
                <option value="anual">Anual</option>
              </select>
            </div>
            <div class="campo">
              <label for="renovar-forma">Forma de pagamento</label>
              <select id="renovar-forma">
                <option value="pix_avista">PIX à vista, com 5% de desconto</option>
                <option value="cartao_parcelado">Cartão de crédito</option>
              </select>
            </div>
            <div class="campo">
              <label for="renovar-cupom">Cupom de desconto</label>
              <div class="campo-com-botao">
                <input type="text" id="renovar-cupom" class="entrada maiusculo" placeholder="Opcional"
                       autocapitalize="characters" oninput="renovarCupomInput()" />
                <button type="button" id="renovar-cupom-btn" class="btn btn-secundario" onclick="aplicarCupomRenovar()">Aplicar</button>
              </div>
              <p id="renovar-cupom-msg" class="campo-dica" hidden></p>
            </div>
          </div>
          <div id="renovar-pix-box" class="pix-box" hidden>
            <p class="pix-label">PIX gerado. Copie o código e pague no app do seu banco.</p>
            <div class="pix-row">
              <input id="renovar-pix-input" class="pix-code" readonly aria-label="Código PIX" />
              <button class="btn btn-primario pix-copy-btn" onclick="copiarPixRenovar()">Copiar</button>
            </div>
          </div>
          <div id="renovar-link-box" class="pix-box" hidden>
            <p class="pix-label">Pagamento gerado</p>
            <a id="renovar-link-anchor" href="#" target="_blank" rel="noopener" class="btn btn-primario btn-largo">Pagar com cartão</a>
          </div>
          <p id="renovar-erro" class="erro" hidden></p>
          <div class="acoes-coluna">
            <button id="renovar-btn" class="btn btn-primario btn-largo" onclick="confirmarRenovar()">Gerar pagamento</button>
          </div>
        </div>
      </div>
    </div>

    <div id="folha-pausa" class="folha-fundo" hidden>
      <div class="folha" role="dialog" aria-modal="true" aria-labelledby="t-pausa">
        <div class="folha-barra">
          <button type="button" class="btn btn-texto" onclick="fecharPausaUI()">Cancelar</button>
          <p class="folha-titulo" id="t-pausa">Pedir pausa</p>
          <button type="button" class="btn btn-texto forte" onclick="confirmarPausa()">Enviar</button>
        </div>
        <div class="folha-corpo">
          <div class="card">
            <div class="campo"><label for="pausa-motivo">Motivo</label><input type="text" id="pausa-motivo" placeholder="Viagem, lesão…" /></div>
            <div class="grade-2">
              <div class="campo"><label for="pausa-data-inicio">A partir de</label><input type="date" id="pausa-data-inicio" min="${_hojeBR()}" /></div>
              <div class="campo"><label for="pausa-dias">Dias</label><input type="number" id="pausa-dias" inputmode="numeric" min="1" max="15" value="7" /></div>
            </div>
          </div>
          <p class="grupo-rodape">Disponível para planos de 3, 6 ou 12 meses, por até 15 dias. A administração analisa e responde.</p>
          <p id="pausa-erro" class="erro" hidden></p>
        </div>
      </div>
    </div>`;
}

async function carregarPerfil() {
  const el = document.getElementById("perfil-info");
  if (!el.innerHTML.trim()) el.innerHTML = carregandoHtml();
  try {
    const [p, sub, pixPendente, filaPos, pagamentos] = await Promise.all([
      apiFetch("/auth/me"),
      apiFetch("/subscriptions/minha-ativa").catch(() => null),
      apiFetch("/subscriptions/pix-pendente").catch(() => null),
      apiFetch("/subscriptions/lista-espera/minha-posicao").catch(() => null),
      apiFetch("/subscriptions/meus-pagamentos").catch(() => []),
    ]);
    if (!p) return;
    _eu = p;
    const emp = await getEmpresa();

    let subHtml;
    if (sub) {
      subHtml = _passeHtml(sub, pixPendente);
    } else if (filaPos) {
      const convocado = filaPos.status === "convocado";
      const expira = convocado && filaPos.data_expiracao_convocacao
        ? new Date(filaPos.data_expiracao_convocacao).toLocaleString("pt-BR", { timeZone: FUSO, day: "numeric", month: "short", hour: "2-digit", minute: "2-digit" })
        : "";
      subHtml = `
        <div class="grupo">
          <div class="linha com-icone">
            <span class="icone-quadro ${convocado ? "q-bom" : ""}">${ICONE_FILA}</span>
            <span class="linha-texto">
              <span class="linha-titulo">${convocado ? "Sua vaga chegou" : "Lista de espera"}</span>
              <span class="linha-sub">${convocado ? "Contrate o plano antes que a vaga expire" : "Avisamos por e-mail quando abrir uma vaga"}</span>
            </span>
            <span class="linha-valor">${filaPos.posicao}º</span>
          </div>
          ${expira ? _linhaDado("A vaga expira em", esc(expira)) : ""}
          ${convocado ? `<button type="button" class="linha linha-centro linha-tint" onclick="abrirRenovarUI()">Contratar plano</button>` : ""}
        </div>
        <div class="grupo"><button type="button" class="linha linha-centro linha-perigo" onclick="sairDaFila()">Sair da lista de espera</button></div>`;
    } else {
      const planosAtivos = emp?.contratacao_planos_ativa !== false;
      subHtml = `
        <div class="sub-card">
          <p class="sub-card-titulo">Sem plano ativo</p>
          <p class="sub-card-texto">Com um plano você entra no ranking e agenda partidas na quadra.</p>
          ${planosAtivos
            ? `<button class="btn btn-primario btn-largo" onclick="abrirRenovarUI()">Contratar plano</button>`
            : avisoHtml(esc(emp?.msg_planos_desabilitado || ""))}
        </div>`;
    }

    // Avisos que impedem de jogar vêm antes de tudo
    let avisos = "";
    if (!p.contrato_assinado && p.contrato_link_assinatura) {
      avisos += avisoHtml(
        `<strong>Contrato pendente.</strong> Assine o termo de adesão para liberar as reservas. `
        + `<a href="${esc(p.contrato_link_assinatura)}" target="_blank" rel="noopener">Abrir o contrato</a>`);
    }
    // Sem foto não há reconhecimento facial: quem chega no portão sem selfie
    // fica do lado de fora. Avisa aqui, que é onde se adiciona a foto.
    if (emp?.acesso_ativo && emp?.acesso_exige_selfie && !p.foto_url) {
      avisos += avisoHtml("<strong>Falta sua foto.</strong> A entrada na quadra é por reconhecimento facial. Adicione uma foto do seu rosto logo acima.");
    }

    const nivel = p.nivel === "nao_classificado" ? "–" : esc(p.nivel);

    el.innerHTML = `
      <div class="perfil-cabeca">
        ${avatarHtml(p, " avatar-lg")}
        <p class="perfil-nome">${esc(p.nome)}</p>
        <p class="perfil-meta">${esc(p.apelido || p.email)}</p>
        <label class="btn btn-secundario btn-pequeno btn-foto" for="inp-foto-upload">${p.foto_url ? "Trocar foto" : "Adicionar foto"}</label>
        <input id="inp-foto-upload" type="file" accept="image/jpeg,image/png,image/webp" hidden />
      </div>
      ${avisos}

      <h2 class="grupo-cabecalho">Assinatura</h2>
      ${subHtml}

      ${_pagamentosHtml(pagamentos)}

      <h2 class="grupo-cabecalho">Desempenho</h2>
      <div class="indicadores">
        <div class="indicador"><span class="indicador-valor">${nivel}</span><span class="indicador-rotulo">Nível</span></div>
        <div class="indicador"><span class="indicador-valor">${Math.round(p.rating_atual)}</span><span class="indicador-rotulo">Rating</span></div>
        <div class="indicador"><span class="indicador-valor">${p.pontos_ranking_temporada_atual}</span><span class="indicador-rotulo">Pontos</span></div>
        <div class="indicador"><span class="indicador-valor">${p.partidas_computadas_rating}</span><span class="indicador-rotulo">Partidas</span></div>
      </div>
      <p class="grupo-rodape">Pontos da temporada atual. Partidas são as que já contam para o rating.</p>

      <div class="grupo-cabecalho">
        <span>Dados pessoais</span>
        <button type="button" class="btn btn-texto" onclick="abrirEdicaoPerfil()">Editar</button>
      </div>
      <div class="grupo">
        ${_linhaDado("Nome", esc(p.nome))}
        ${_linhaDado("Apelido", esc(p.apelido))}
        ${_linhaDado("E-mail", esc(p.email))}
        ${_linhaDado("Telefone", esc(fmtTelefone(p.telefone)))}
        ${_linhaDado("CPF", esc(fmtCPF(p.cpf)))}
        ${_linhaDado("Nascimento", p.data_nascimento ? fmtData(p.data_nascimento + "T12:00:00") : "")}
        ${_temEndereco(p) ? _linhaDado("Endereço", _enderecoTexto(p)) : ""}
      </div>

      <h2 class="grupo-cabecalho">Segurança</h2>
      <div class="grupo">
        <button type="button" class="linha linha-nav com-icone" onclick="abrirAlterarSenha()">
          <span class="icone-quadro">${ICONE_CHAVE}</span>
          <span class="linha-texto"><span class="linha-titulo">Alterar senha</span></span>
        </button>
      </div>

      ${_folhasPerfilHtml(p)}
      ${_folhaPagamentosHtml(pagamentos)}
    `;

    // Preços reais no seletor de plano
    apiFetch("/subscriptions/precos").then(precos => {
      if (!precos) return;
      document.getElementById("renovar-plano").innerHTML = [
        ["mensal",     "Mensal"],
        ["trimestral", "Trimestral"],
        ["semestral",  "Semestral"],
        ["anual",      "Anual"],
      ].map(([v, l]) => {
        const valor = precos[v]?.valor_total;
        return `<option value="${v}">${l}${valor != null ? ` (${fmtBRL(valor)})` : ""}</option>`;
      }).join("");
    }).catch(() => {});

    document.getElementById("inp-foto-upload").addEventListener("change", async (e) => {
      const file = e.target.files[0];
      if (!file) return;
      try {
        await uploadFoto(file);
        _eu = null;
        await Promise.all([carregarPerfil(), carregarRanking()]);
        avisar("Foto atualizada");
      } catch (err) { avisar(err.message, { erro: true }); }
    });
  } catch (e) {
    el.innerHTML = erroHtml(e.message || "Verifique sua conexão e tente de novo.");
  }
}

function abrirAlterarSenha() {
  ["senha-atual", "senha-nova", "senha-confirma"].forEach(id => document.getElementById(id).value = "");
  document.getElementById("senha-erro").hidden = true;
  abrirFolha("folha-senha");
  setTimeout(() => document.getElementById("senha-atual")?.focus(), 350);
}

function fecharAlterarSenha() { fecharFolha("folha-senha"); }

async function confirmarAlterarSenha() {
  const erro = document.getElementById("senha-erro");
  erro.hidden = true;
  const atual    = document.getElementById("senha-atual").value;
  const nova     = document.getElementById("senha-nova").value;
  const confirma = document.getElementById("senha-confirma").value;
  if (!atual || !nova) { erro.textContent = "Preencha todos os campos."; erro.hidden = false; return; }
  if (nova.length < 6)  { erro.textContent = "A nova senha deve ter pelo menos 6 caracteres."; erro.hidden = false; return; }
  if (nova.length > 72) { erro.textContent = "A senha pode ter no máximo 72 caracteres."; erro.hidden = false; return; }
  if (nova !== confirma) { erro.textContent = "As senhas não conferem."; erro.hidden = false; return; }
  try {
    // Trocar a senha derruba toda sessão antiga; a resposta traz os tokens
    // novos desta, senão o app cairia no login logo em seguida
    const res = await apiFetch("/auth/alterar-senha", { method: "POST", body: JSON.stringify({ senha_atual: atual, nova_senha: nova }) });
    if (res?.access_token) Auth.save(res);
    fecharAlterarSenha();
    avisar("Senha alterada");
  } catch (e) {
    erro.textContent = e.message || "Erro ao alterar senha.";
    erro.hidden = false;
  }
}

function abrirEdicaoPerfil() {
  document.getElementById("edit-perfil-erro").hidden = true;
  abrirFolha("folha-editar");
}

function fecharEdicaoPerfil() { fecharFolha("folha-editar"); }

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
    fecharEdicaoPerfil();
    _eu = null;
    await carregarPerfil();
    avisar("Dados salvos");
  } catch (e) {
    erro.textContent = e.message || "Erro ao salvar.";
    erro.hidden = false;
  }
}

async function sairDaFila() {
  const ok = await confirmar(
    "Sair da lista de espera?",
    "Você perde sua posição na fila. Para voltar, entra no fim dela.",
    { acao: "Sair da lista", perigo: true },
  );
  if (!ok) return;
  try {
    await apiFetch("/subscriptions/lista-espera", { method: "DELETE" });
    await carregarPerfil();
    avisar("Você saiu da lista de espera");
  } catch (e) { avisar(e.message, { erro: true }); }
}

function _copiar(texto) {
  if (!texto) return;
  navigator.clipboard.writeText(texto)
    .then(() => avisar("Código PIX copiado"))
    .catch(() => avisar("Não deu para copiar. Toque no código e copie à mão.", { erro: true }));
}
function copiarPixJogador() { _copiar(document.getElementById("pix-code-input")?.value); }
function copiarPixRenovar() { _copiar(document.getElementById("renovar-pix-input")?.value); }

function atualizarFormasPagamento() {
  // PIX disponível para todos os planos com 5% de desconto
}

function abrirRenovarUI(titulo) {
  document.getElementById("renovar-pix-box").hidden = true;
  document.getElementById("renovar-link-box").hidden = true;
  document.getElementById("renovar-erro").hidden = true;
  document.getElementById("renovar-btn").hidden = false;
  document.getElementById("renovar-titulo").textContent = titulo || "Contratar plano";
  if (typeof _cupomRenovarUI !== "undefined") _cupomRenovarUI.limpar();
  atualizarFormasPagamento();
  abrirFolha("folha-renovar");
}
function fecharRenovarUI() {
  // Se um pagamento foi gerado, o passe precisa mostrar a cobrança pendente
  const gerou = !document.getElementById("renovar-pix-box").hidden
    || !document.getElementById("renovar-link-box").hidden;
  fecharFolha("folha-renovar");
  if (gerou) carregarPerfil();
}

// ── Cupom (compartilhado pelos fluxos de pagamento do app) ───────────────────
async function validarCupom(codigo) {
  const c = (codigo || "").trim().toUpperCase();
  if (!c) return { valido: false, msg: "Informe um código." };
  try {
    return await apiFetch("/cupons/validar", { method: "POST", body: JSON.stringify({ codigo: c }) });
  } catch {
    return { valido: false, msg: "Erro ao validar o cupom." };
  }
}

/**
 * Liga um campo de cupom a um estado. Devolve helpers para o fluxo.
 * getState() lê o cupom aplicado; onChange roda ao aplicar/remover.
 */
function criarCupomUI(prefixo, onChange) {
  const inp = () => document.getElementById(`${prefixo}-cupom`);
  const btn = () => document.getElementById(`${prefixo}-cupom-btn`);
  const msg = () => document.getElementById(`${prefixo}-cupom-msg`);
  let estado = null;

  async function aplicar() {
    const codigo = inp().value.trim().toUpperCase();
    if (!codigo) return;
    if (estado) { limpar(true); return; }
    const d = await validarCupom(codigo);
    if (d.valido) {
      estado = { codigo: d.codigo, percentual: d.percentual };
      msg().textContent = `${d.percentual}% de desconto aplicado`;
      msg().className = "campo-dica ok";
      btn().textContent = "Remover";
    } else {
      estado = null;
      msg().textContent = d.msg || "Cupom inválido.";
      msg().className = "campo-dica erro-txt";
    }
    msg().hidden = false;
    if (onChange) onChange(estado);
  }
  function digitou() {
    if (estado) { estado = null; if (onChange) onChange(estado); }
    msg().hidden = true;
    btn().textContent = "Aplicar";
  }
  function limpar(soEstado) {
    estado = null;
    if (!soEstado && inp()) inp().value = "";
    if (msg()) msg().hidden = true;
    if (btn()) btn().textContent = "Aplicar";
    if (onChange) onChange(estado);
  }
  return { aplicar, digitou, limpar, get: () => estado };
}

let _cupomRenovar = null;
const _cupomRenovarUI = criarCupomUI("renovar", (c) => { _cupomRenovar = c; });
function aplicarCupomRenovar() { _cupomRenovarUI.aplicar(); }
function renovarCupomInput() { _cupomRenovarUI.digitou(); }

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
      body: JSON.stringify({ plano, forma_pagamento, cupom_codigo: _cupomRenovar ? _cupomRenovar.codigo : null }),
    });
    if (res?.pix_copia_e_cola) {
      document.getElementById("renovar-pix-input").value = res.pix_copia_e_cola;
      document.getElementById("renovar-pix-box").hidden = false;
      btn.hidden = true;
    } else if (res?.payment_link) {
      document.getElementById("renovar-link-anchor").href = res.payment_link;
      document.getElementById("renovar-link-box").hidden = false;
      btn.hidden = true;
    } else {
      fecharRenovarUI();
      await carregarPerfil();
    }
  } catch (err) {
    erroEl.textContent = err.message;
    erroEl.hidden = false;
  } finally {
    btn.disabled = false; btn.textContent = "Gerar pagamento";
  }
}

function abrirPausaUI() {
  document.getElementById("pausa-erro").hidden = true;
  abrirFolha("folha-pausa");
}
function fecharPausaUI() { fecharFolha("folha-pausa"); }

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
    fecharPausaUI();
    avisar("Pedido de pausa enviado");
  } catch (err) {
    erroEl.textContent = err.message;
    erroEl.hidden = false;
  }
}

// ── Uso semanal ──────────────────────────────────────────────────────────────
// As barras de capacidade dos Ajustes do iPhone: quanto da cota já foi usado.
function _barraUso(label, uso) {
  const pct = uso.limite ? Math.min((uso.usados / uso.limite) * 100, 100) : 0;
  const esgotado = uso.restantes === 0;
  return `
    <div class="uso-linha${esgotado ? " esgotado" : ""}">
      <div class="uso-topo">
        <span class="uso-label">${label}</span>
        <span class="uso-nums">${uso.usados} de ${uso.limite}</span>
      </div>
      <div class="uso-barra" role="progressbar" aria-label="${label}: ${uso.usados} de ${uso.limite} jogos"
           aria-valuenow="${uso.usados}" aria-valuemin="0" aria-valuemax="${uso.limite}">
        <div class="uso-barra-fill" style="width:${pct}%"></div>
      </div>
      <span class="uso-restante">${esgotado
        ? "Cota da semana esgotada"
        : `${uso.restantes} ${uso.restantes === 1 ? "jogo restante" : "jogos restantes"}`}</span>
    </div>`;
}

async function carregarUsoSemanal() {
  const el = document.getElementById("uso-semanal");
  if (!el) return;
  if (!el.innerHTML.trim()) el.innerHTML = carregandoHtml();
  try {
    const u = await apiFetch("/bookings/uso-semanal");
    if (!u) return;
    el.innerHTML = `
      <p class="card-sub">Semana de ${fmtDiaMes(u.semana_inicio, true)} a ${fmtDiaMes(u.semana_fim, true)}</p>
      ${_barraUso("Simples", u.simples)}
      ${_barraUso("Duplas", u.duplas)}`;
  } catch (e) {
    el.innerHTML = erroHtml(e.message || "Não foi possível ler seus jogos da semana.");
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
  ranking_ultima_hora:   { label: "Última hora",        cls: "label-ultima-hora" },
  comercial_ultima_hora: { label: "Última hora",        cls: "label-ultima-hora" },
  ocupado:               { label: "Reservado",          cls: "label-ocupado" },
  passado:               { label: "Encerrado",          cls: "label-indisponivel" },
  comercial:             { label: "Só na última hora",  cls: "label-indisponivel" },
  janela_morta:          { label: "Fora da janela",     cls: "label-indisponivel" },
};

const ICONE_CALENDARIO = `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><rect x="3.5" y="5" width="17" height="15.5" rx="3"/><path d="M3.5 9.5h17"/><path d="M8 3v4M16 3v4"/></svg>`;
const ICONE_BOLA = `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><circle cx="12" cy="12" r="8.5"/><path d="M6.2 5.8c2.4 1.6 3.8 3.6 3.8 6.2s-1.4 4.6-3.8 6.2"/><path d="M17.8 5.8c-2.4 1.6-3.8 3.6-3.8 6.2s1.4 4.6 3.8 6.2"/></svg>`;

function fmtJogadoresSlot(jogadores) {
  if (!jogadores || !jogadores.length) return null;
  const nome = (j) => esc(j.apelido || j.nome.split(" ")[0]);
  const ladoA = jogadores.filter(j => j.lado === "A").map(nome).join(" / ");
  const ladoB = jogadores.filter(j => j.lado === "B").map(nome).join(" / ");
  return ladoA && ladoB ? `${ladoA} × ${ladoB}` : (ladoA || ladoB);
}

async function buscarSlots() {
  const data = document.getElementById("inp-data-jogo").value;
  const tipo = document.querySelector('input[name="tipo-jogo"]:checked').value;
  if (!data) return;

  document.getElementById("slots-container").hidden = false;
  document.getElementById("form-reserva").hidden = true;
  _slotSelecionado = null;

  const lista = document.getElementById("lista-slots");
  lista.innerHTML = carregandoHtml();

  // A regra de antecedência sai da configuração: o "6 h" fixo deixaria de
  // valer quando o admin mudasse o prazo no painel.
  getEmpresa().then((emp) => {
    const min = emp?.ranking_antecedencia_minima_horas;
    document.getElementById("slots-rodape").textContent = min != null
      ? `Reserve com ${min} h ou mais de antecedência, ou na última hora.`
      : "";
  });

  try {
    const slots = await apiFetch(`/bookings/slots?data=${data}&tipo=${tipo}`);
    if (!slots) return;
    _slots = slots;

    if (!slots.length) {
      lista.innerHTML = vazioHtml(ICONE_CALENDARIO, "Sem horários neste dia", "A quadra não abre nesta data. Escolha outro dia.");
      return;
    }

    lista.innerHTML = slots.map((s, i) => {
      const cfg = SLOT_CONFIG[s.tipo_disponibilidade] || { label: s.tipo_disponibilidade, cls: "label-indisponivel" };
      const livre = s.disponivel;
      const nomes = fmtJogadoresSlot(s.jogadores);
      const hora = fmtHora(s.data_hora_inicio);

      let centro = "<span></span>";
      if (nomes) {
        const resultado = s.status_partida === "wo" ? "W.O." : (s.placar ? placarStr(s.placar) : "");
        centro = `<span class="slot-info-centro"><span class="slot-jogadores">${nomes}</span>`
          + `${resultado ? `<span class="slot-placar">${resultado}</span>` : ""}</span>`;
      } else if (s.motivo_indisponibilidade && s.tipo_disponibilidade === "janela_morta") {
        centro = `<span class="slot-motivo-inline">${esc(s.motivo_indisponibilidade)}</span>`;
      }

      return `
        <div class="linha slot-item ${livre ? "slot-livre" : "slot-indisponivel"}"
             ${livre ? `onclick="selecionarSlot(${i})" role="button" tabindex="0" aria-label="Reservar às ${hora}"` : ""}>
          <span class="slot-hora">${hora}</span>
          ${centro}
          <span class="etiqueta slot-label ${cfg.cls}">${cfg.label}</span>
        </div>`;
    }).join("");
  } catch (e) {
    lista.innerHTML = erroHtml(e.message || "Não foi possível buscar os horários.");
  }
}

function fmtBRL(v) {
  return `R$ ${Number(v).toLocaleString("pt-BR", { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`;
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
    <h2 class="grupo-cabecalho">Convidado: ${label.toLowerCase()}</h2>
    <div class="card">
      <div class="campo"><label for="cv-${sel}-nome">Nome completo</label><input type="text" id="cv-${sel}-nome" autocomplete="off" value="${esc(d.nome)}" /></div>
      <div class="grade-2">
        <div class="campo"><label for="cv-${sel}-cpf">CPF</label><input type="text" id="cv-${sel}-cpf" inputmode="numeric" maxlength="14" placeholder="000.000.000-00" value="${esc(d.cpf)}" /></div>
        <div class="campo"><label for="cv-${sel}-nasc">Nascimento</label><input type="date" id="cv-${sel}-nasc" value="${esc(d.nasc)}" /></div>
      </div>
      <div class="campo"><label for="cv-${sel}-tel">WhatsApp</label><input type="tel" id="cv-${sel}-tel" placeholder="16 99123-4567" value="${esc(d.tel)}" /></div>
      <div class="campo"><label for="cv-${sel}-apelido">Apelido</label><input type="text" id="cv-${sel}-apelido" placeholder="Opcional" value="${esc(d.apelido)}" /></div>
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
    const bruto = _precoJogoAvulso * posConv.length;
    const final = _cupomAvulso ? bruto * (1 - _cupomAvulso.percentual / 100) : bruto;
    const riscado = _cupomAvulso ? `<span class="preco-antigo">${fmtBRL(bruto)}</span>` : "";
    const qtd = posConv.length === 1 ? "1 convidado" : `${posConv.length} convidados`;
    total.innerHTML = `<span>Total, ${qtd}</span><span>${riscado}<strong>${fmtBRL(final)}</strong></span>`;
  }
}

let _cupomAvulso = null;
const _cupomAvulsoUI = criarCupomUI("avulso", (c) => { _cupomAvulso = c; _renderFormsConvidados(); });
function aplicarCupomAvulso() { _cupomAvulsoUI.aplicar(); }
function avulsoCupomInput() { _cupomAvulsoUI.digitou(); }

function _renderSelectsJogadores() {
  const opts = _jogadores
    .filter((j) => j.id !== _me?.id)
    .map((j) => `<option value="${j.id}">${esc(j.apelido || j.nome)} (${j.nivel === "nao_classificado" ? "sem nível" : "nível " + esc(j.nivel)})</option>`)
    .join("");
  const optConvidado = _avulsoLigado()
    ? `<option value="convidado">Convidado de fora do ranking</option>`
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
    _precoJogoAvulso = (await getEmpresa())?.preco_jogo_avulso ?? null;
  }

  const ini = _slotSelecionado.data_hora_inicio;
  const dia = _primeiraMaiuscula(new Date(ini).toLocaleDateString("pt-BR", {
    weekday: "long", day: "numeric", month: "long", timeZone: FUSO,
  }));
  document.getElementById("reserva-slot-info").innerHTML =
    `${fmtHora(ini)} às ${fmtHora(_slotSelecionado.data_hora_fim)}<small>${esc(dia)}</small>`;

  _convidadosData = {};
  _cupomAvulsoUI.limpar();
  document.getElementById("chk-jogo-avulso").checked = false;
  document.getElementById("campo-avulso-toggle").hidden = !_slotEhUltimaHora(_slotSelecionado);
  document.getElementById("avulso-cobranca").hidden = true;
  document.getElementById("avulso-cobranca").innerHTML = "";
  document.getElementById("reserva-acoes").hidden = false;

  _renderSelectsJogadores();

  document.getElementById("reserva-erro").hidden = true;
  abrirFolha("form-reserva");
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
        cupom_codigo: _cupomAvulso ? _cupomAvulso.codigo : null,
      }),
    });

    const box = document.getElementById("avulso-cobranca");
    const pagamento = r.invoice_url
      ? `<a href="${esc(r.invoice_url)}" target="_blank" rel="noopener" class="btn btn-primario btn-largo">Pagar com cartão</a>`
      : `<div class="pix-row">
           <input class="pix-code" readonly value="${esc(r.pix_copia_cola || "")}" id="avulso-pix-input" aria-label="Código PIX" />
           <button class="btn btn-primario pix-copy-btn" onclick="copiarPixAvulso()">Copiar</button>
         </div>`;
    box.innerHTML = `
      <div class="card">
        <p class="card-titulo">${fmtBRL(r.valor)}</p>
        <p class="card-sub">${esc(r.msg)}</p>
        ${pagamento}
      </div>
      <button class="btn btn-secundario btn-largo" onclick="fecharReserva()">Concluir</button>`;
    box.hidden = false;
    document.getElementById("reserva-acoes").hidden = true;
  } catch (e) {
    erroEl.textContent = e.message.replace(/^Erro \d+: /, "");
    erroEl.hidden = false;
  } finally {
    btn.disabled = false;
    btn.textContent = "Confirmar reserva";
  }
}

function copiarPixAvulso() { _copiar(document.getElementById("avulso-pix-input")?.value); }

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
    avisar("Partida agendada");
  } catch (e) {
    erroEl.textContent = e.message.replace(/^Erro \d+: /, "");
    erroEl.hidden = false;
  } finally {
    btn.disabled = false;
    btn.textContent = "Confirmar reserva";
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
      if (j.apelido) return esc(j.apelido);
      const partes = j.nome.trim().split(/\s+/);
      return esc(partes.length > 1 ? `${partes[0]} ${partes[partes.length - 1]}` : partes[0]);
    })
    .join(" / ");
}

function placarStr(placar) {
  if (!placar) return "";
  const { games_A, games_B, tiebreak_A, tiebreak_B } = placar;
  const tb = tiebreak_A != null ? ` (TB ${tiebreak_A}–${tiebreak_B})` : "";
  return `${games_A}–${games_B}${tb}`;
}

/** A data em bloco, como no Calendário: dia da semana no tint, número embaixo. */
function _dataBloco(iso, passada) {
  const d = new Date(iso);
  const sem = _primeiraMaiuscula(d.toLocaleDateString("pt-BR", { weekday: "short", timeZone: FUSO }).replace(".", ""));
  const dia = d.toLocaleDateString("pt-BR", { day: "numeric", timeZone: FUSO });
  return `<span class="data-bloco${passada ? " passada" : ""}" aria-hidden="true">`
    + `<span class="dia-semana">${sem}</span><span class="dia-numero">${dia}</span></span>`;
}

function renderPartida(p, aguardandoPlacar) {
  const nA = nomesLado(p, "A", _jogadores);
  const nB = nomesLado(p, "B", _jogadores);
  const quando = new Date(p.data_hora);
  const futura = quando > new Date();
  const realizada = p.status === "realizado";
  const tipo = p.tipo === "simples" ? "Simples" : "Duplas";
  // O bloco à esquerda já diz o dia; o mês só entra quando não é o corrente
  const mesDe = (d) => d.toLocaleDateString("pt-BR", { month: "long", year: "numeric", timeZone: FUSO });
  const outroMes = mesDe(quando) !== mesDe(new Date());
  const mes = quando.toLocaleDateString("pt-BR", { month: "long", timeZone: FUSO });
  const sub = `${tipo} às ${fmtHora(p.data_hora)}${outroMes ? `, em ${mes}` : ""}`
    + (p.avulso ? `. <span class="partida-avulso">Jogo avulso, não pontua</span>` : "");

  const lados = `<span class="partida-lados">`
    + `<span class="${realizada && p.lado_vencedor === "A" ? "venceu" : ""}">${nA}</span>`
    + `<span class="contra">×</span>`
    + `<span class="${realizada && p.lado_vencedor === "B" ? "venceu" : ""}">${nB}</span></span>`;

  // O lado direito diz o que importa agora: lançar o placar, o resultado, ou
  // cancelar. Vitória e derrota são do ponto de vista de quem está olhando.
  let direita;
  if (aguardandoPlacar) {
    direita = `<button class="btn btn-primario btn-pequeno" onclick="abrirFormPlacar(${p.id})">Placar</button>`;
  } else if (realizada && p.placar) {
    const meu = p.participantes.find((x) => x.player_id && x.player_id === _eu?.id);
    const res = meu ? (meu.lado === p.lado_vencedor ? '<small class="vitoria">Vitória</small>' : '<small class="derrota">Derrota</small>') : "";
    direita = `<span class="partida-placar-valor">${placarStr(p.placar)}${res}</span>`;
  } else if (p.status === "wo") {
    direita = `<span class="etiqueta e-critico">W.O.</span>`;
  } else if (p.status === "agendado" && futura) {
    direita = `<button class="btn btn-perigo btn-pequeno" onclick="cancelarPartida(${p.id})">Cancelar</button>`;
  } else if (p.status === "agendado") {
    direita = `<span class="etiqueta">Encerrada</span>`;
  } else {
    direita = `<span class="etiqueta">Cancelada</span>`;
  }

  return `
    <div class="linha com-data">
      ${_dataBloco(p.data_hora, !futura)}
      <span class="linha-texto">${lados}<span class="linha-sub">${sub}${p.status === "wo" && p.cancelado_por_id ? ". Cancelada em cima da hora" : ""}</span></span>
      ${direita}
    </div>`;
}

async function carregarPartidas() {
  const cont = document.getElementById("partidas-lista");
  document.getElementById("form-placar").hidden = true;
  _partidaSelecionada = null;
  if (!cont.innerHTML.trim()) cont.innerHTML = carregandoHtml();

  try {
    await _carregarEu();
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
    // O servidor manda da mais nova para a mais antiga — certo para o
    // histórico, errado para as próximas: a mais próxima tem de vir primeiro.
    proximas.sort((a, b) => new Date(a.data_hora) - new Date(b.data_hora));

    const prazo = (await getEmpresa())?.cancelamento_antecedencia_horas ?? 3;
    const secao = (titulo, itens, aguardandoPlacar, rodape) => !itens.length ? "" : `
      <h2 class="grupo-cabecalho">${titulo}</h2>
      <div class="grupo">${itens.map((p) => renderPartida(p, aguardandoPlacar)).join("")}</div>
      ${rodape ? `<p class="grupo-rodape">${rodape}</p>` : ""}`;

    const html = secao("Aguardando placar", aguardando, true, "Qualquer jogador da partida pode lançar o resultado.")
      + secao("Próximas", proximas, false, `Cancelar com menos de ${prazo} h de antecedência conta como W.O.`)
      + secao("Anteriores", historico, false, "");
    cont.innerHTML = html || vazioHtml(ICONE_BOLA, "Nenhuma partida ainda", "Agende uma partida do ranking na aba Agendar.");
  } catch (e) {
    cont.innerHTML = erroHtml(e.message || "Não foi possível carregar suas partidas.");
  }
}

async function cancelarPartida(matchId) {
  const p = (_partidas || []).find((m) => m.id === matchId);
  const emp = await getEmpresa();
  const prazoH = emp?.cancelamento_antecedencia_horas ?? 3;
  const faltaMs = p ? new Date(p.data_hora) - new Date() : Infinity;
  const tardio = faltaMs < prazoH * 3600 * 1000;

  const ok = await confirmar(
    tardio ? "Cancelar em cima da hora?" : "Cancelar a partida?",
    tardio
      ? `Faltam menos de ${prazoH} h. A partida conta como W.O. e sai do seu saldo da semana.`
      : "O horário volta para a agenda e seu saldo da semana não muda.",
    { acao: "Cancelar partida", perigo: true, voltar: "Manter" },
  );
  if (!ok) return;

  try {
    await apiFetch(`/matches/${matchId}/cancelar-jogador`, { method: "POST" });
    await carregarPartidas();
    carregarUsoSemanal();
    avisar("Partida cancelada");
  } catch (e) {
    avisar(e.message || "Não foi possível cancelar a partida.", { erro: true });
  }
}

function abrirFormPlacar(matchId) {
  _partidaSelecionada = _partidas.find((p) => p.id === matchId);
  if (!_partidaSelecionada) return;

  const nA = nomesLado(_partidaSelecionada, "A", _jogadores);
  const nB = nomesLado(_partidaSelecionada, "B", _jogadores);
  document.getElementById("placar-match-info").textContent =
    _primeiraMaiuscula(fmtDataHora(_partidaSelecionada.data_hora));
  document.getElementById("label-games-a").innerHTML = nA;
  document.getElementById("label-games-b").innerHTML = nB;
  document.getElementById("inp-games-a").value = 0;
  document.getElementById("inp-games-b").value = 0;
  document.getElementById("inp-tb-a").value = 0;
  document.getElementById("inp-tb-b").value = 0;
  document.getElementById("campo-tiebreak").hidden = true;
  document.getElementById("placar-erro").hidden = true;

  abrirFolha("form-placar");
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
  btn.textContent = "Salvando…";
  erroEl.hidden = true;

  try {
    await apiFetch(`/matches/${_partidaSelecionada.id}/placar`, {
      method: "POST",
      body: JSON.stringify({ games_a: gA, games_b: gB, tiebreak_a: tbA, tiebreak_b: tbB }),
    });
    document.getElementById("form-placar").hidden = true;
    _partidaSelecionada = null;
    await carregarPartidas();
    avisar("Placar registrado");
  } catch (e) {
    erroEl.textContent = e.message.replace(/^Erro \d+: /, "");
    erroEl.hidden = false;
  } finally {
    btn.disabled = false;
    btn.textContent = "Salvar";
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
  const hoje = _hojeBR();
  document.getElementById("loc-data").value = hoje;
  document.getElementById("loc-data").min = hoje;
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
  slotsEl.innerHTML = carregandoHtml();
  locIrStep(2);

  try {
    const res = await fetch(`/api/v1/public/disponibilidade?data=${data}`);
    if (!res.ok) {
      const err = await res.json().catch(() => ({}));
      throw new Error(err.detail || "Erro ao buscar horários");
    }
    const d = await res.json();
    _locPrecoHora = d.preco_hora;

    document.getElementById("loc-data-label").textContent = _primeiraMaiuscula(
      new Date(`${data}T12:00:00`).toLocaleDateString("pt-BR", { weekday: "long", day: "numeric", month: "long" }));
    document.getElementById("loc-preco-info").textContent =
      `${fmtBRL(_locPrecoHora)} por hora. O horário fica guardado por 10 minutos enquanto você paga.`;

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
      slotsEl.innerHTML = vazioHtml(ICONE_CALENDARIO, "Nenhum horário livre", `Não há ${numHoras === 1 ? "1 hora" : numHoras + " horas"} seguidas livres nesta data. Tente outra duração ou outro dia.`);
      return;
    }

    slotsEl.innerHTML = validos.map(s => {
      const hFim = String(parseInt(s.hora_inicio) + numHoras).padStart(2, "0") + ":00";
      return `
        <button type="button" class="linha linha-nav" onclick="locSelecionarSlot('${data}','${s.hora_inicio}',${numHoras})">
          <span class="linha-texto"><span class="linha-titulo tabular">${s.hora_inicio} às ${hFim}</span></span>
          <span class="linha-valor tabular">${fmtBRL(_locPrecoHora * numHoras)}</span>
        </button>`;
    }).join("");

  } catch (e) {
    slotsEl.innerHTML = erroHtml(e.message || "Não foi possível buscar os horários.");
  }
});

function _locRenderResumo() {
  if (!_locSelecionado) return;
  const { data, hora, numHoras } = _locSelecionado;
  const hFim = String(parseInt(hora) + numHoras).padStart(2, "0") + ":00";
  const dia = _primeiraMaiuscula(new Date(`${data}T12:00:00`)
    .toLocaleDateString("pt-BR", { weekday: "long", day: "numeric", month: "long" }));
  const bruto = _locPrecoHora * numHoras;
  const final = _cupomLoc ? bruto * (1 - _cupomLoc.percentual / 100) : bruto;
  const riscado = _cupomLoc ? `<span class="preco-antigo">${fmtBRL(bruto)}</span>` : "";
  document.getElementById("loc-s3-info").innerHTML =
    `<strong>${dia}</strong>, das ${hora} às ${hFim}<br>`
    + `${numHoras === 1 ? "1 hora" : numHoras + " horas"} por ${riscado}<strong>${fmtBRL(final)}</strong>`;
}

function locSelecionarSlot(data, hora, numHoras) {
  _locSelecionado = { data, hora, numHoras };
  _cupomLocUI.limpar();
  _locRenderResumo();
  document.getElementById("loc-s3-erro").hidden = true;
  const pixRadio = document.querySelector('input[name="loc-pagto"][value="pix"]');
  if (pixRadio) pixRadio.checked = true;
  locIrStep(3);
}

let _cupomLoc = null;
const _cupomLocUI = criarCupomUI("loc", (c) => { _cupomLoc = c; _locRenderResumo(); });
function aplicarCupomLoc() { _cupomLocUI.aplicar(); }
function locCupomInput() { _cupomLocUI.digitou(); }

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
        cupom_codigo: _cupomLoc ? _cupomLoc.codigo : null,
      }),
    });

    document.getElementById("loc-s4-msg").textContent = resp.msg;
    document.getElementById("loc-pix").hidden = true;
    document.getElementById("loc-cartao").hidden = true;

    if (metodo === "pix" && resp.pix_qrcode) {
      document.getElementById("loc-pix-qr").src = `data:image/png;base64,${resp.pix_qrcode}`;
      document.getElementById("loc-pix-chave").textContent = resp.pix_copia_cola || "";
      document.getElementById("btn-copiar-pix").onclick = () => _copiar(resp.pix_copia_cola);
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
