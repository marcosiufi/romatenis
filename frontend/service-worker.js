const CACHE_NAME = "romatenis-v14";
const STATIC_ASSETS = ["/", "/css/style.css", "/js/app.js", "/manifest.json", "/admin/", "/admin/js/admin.js"];

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
  if (event.request.url.includes("/api/")) return; // Nunca cacheia chamadas de API

  event.respondWith(
    caches.match(event.request).then((cached) => cached || fetch(event.request))
  );
});
