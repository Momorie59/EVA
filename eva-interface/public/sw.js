/* Service worker d'EVA : rend l'application installable (Android/Chrome) et garde l'enveloppe de l'interface
   pour s'ouvrir même quand le NAS est injoignable (l'interface affiche alors « hors ligne »).
   Jamais de cache pour l'API, le WebSocket, la voix : seulement l'interface elle-même. */
const CACHE = "eva-shell-v1";
const SHELL = ["/", "/manifest.webmanifest", "/icon-192.png", "/icon-512.png", "/favicon.svg", "/eva-logo.svg"];

self.addEventListener("install", (e) => {
  e.waitUntil(caches.open(CACHE).then((c) => c.addAll(SHELL)).then(() => self.skipWaiting()));
});

self.addEventListener("activate", (e) => {
  e.waitUntil(caches.keys().then((ks) => Promise.all(ks.filter((k) => k !== CACHE).map((k) => caches.delete(k)))).then(() => self.clients.claim()));
});

self.addEventListener("fetch", (e) => {
  const req = e.request;
  const url = new URL(req.url);
  if (req.method !== "GET" || url.origin !== self.location.origin) return;
  if (/^\/(api|ws|stt|tts|voice|docs|openapi)/.test(url.pathname)) return;           // données vivantes : toujours le réseau
  if (req.mode === "navigate") {                                                       // page : réseau d'abord, enveloppe en secours
    e.respondWith(fetch(req).then((r) => { const copy = r.clone(); caches.open(CACHE).then((c) => c.put("/", copy)); return r; })
      .catch(() => caches.match("/").then((r) => r || Response.error())));
    return;
  }
  e.respondWith(caches.match(req).then((hit) => {                                      // fichiers de l'interface : cache puis mise à jour
    const net = fetch(req).then((r) => { if (r.ok) { const copy = r.clone(); caches.open(CACHE).then((c) => c.put(req, copy)); } return r; }).catch(() => hit);
    return hit || net;
  }));
});
