// Rede primeiro, cache só sem internet.
//
// Antes era cache primeiro: HTML e JS vinham do cache e a rede nem era
// consultada, por isso todo deploy exigia subir o CACHE_NAME e o PWA ficava
// dias servindo a versão antiga. Agora a página sempre tenta a rede e guarda
// a resposta; o cache entra quando a rede falha (quadra sem sinal). O
// CACHE_NAME ainda existe para descartar o cache antigo de quem instalou a
// versão anterior.
const CACHE_NAME = "romatenis-v65";
const STATIC_ASSETS = ["/", "/app/", "/css/style.css", "/css/landing.css", "/js/app.js", "/app/manifest.json", "/admin/", "/admin/js/admin.js", "/redefinir-senha"];

self.addEventListener("install", (event) => {
  event.waitUntil(
    caches.open(CACHE_NAME).then((cache) => cache.addAll(STATIC_ASSETS))
  );
  self.skipWaiting();
});

self.addEventListener("activate", (event) => {
  event.waitUntil(
    caches.keys().then((keys) =>
      Promise.all(keys.filter((k) => k !== CACHE_NAME).map((k) => caches.delete(k)))
    )
  );
  self.clients.claim();
});

self.addEventListener("fetch", (event) => {
  if (event.request.method !== "GET") return;
  const url = new URL(event.request.url);
  // Outros domínios (fontes do Google) e o que não pode ficar guardado: API e
  // fotos de pessoas vão direto à rede, sem passar pelo cache.
  if (url.origin !== location.origin) return;
  if (url.pathname.startsWith("/api/") || url.pathname.startsWith("/uploads/")) return;

  event.respondWith(
    fetch(event.request)
      .then((resposta) => {
        if (resposta.ok && resposta.type === "basic") {
          const copia = resposta.clone();
          caches.open(CACHE_NAME).then((cache) => cache.put(event.request, copia));
        }
        return resposta;
      })
      .catch(() =>
        caches.match(event.request).then((guardada) =>
          guardada || (event.request.mode === "navigate" ? caches.match("/app/") : Response.error())
        )
      )
  );
});
