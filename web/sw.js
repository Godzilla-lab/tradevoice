// TradeVoice offline: the app itself opens without internet (network first, last good copy if offline).
// Voice notes recorded offline wait in the phone (IndexedDB, see app.js) and send themselves when back online.
const CACHE = "tv-shell-v1";
const SHELL = ["/app", "/static/style.css", "/static/app.js", "/static/customers.js", "/static/logo.svg"];

self.addEventListener("install", (e) => {
  e.waitUntil(caches.open(CACHE).then((c) => c.addAll(SHELL)).catch(() => {}));
  self.skipWaiting();
});
self.addEventListener("activate", (e) => {
  e.waitUntil(caches.keys().then((ks) => Promise.all(ks.filter((k) => k !== CACHE).map((k) => caches.delete(k)))));
  self.clients.claim();
});
self.addEventListener("fetch", (e) => {
  const url = new URL(e.request.url);
  if (e.request.method !== "GET" || url.origin !== location.origin) return;
  if (!(url.pathname === "/app" || url.pathname.startsWith("/static/"))) return;  // the book itself is never cached
  e.respondWith(fetch(e.request).then((r) => {
    if (r.ok) { const copy = r.clone(); caches.open(CACHE).then((c) => c.put(e.request, copy)); }
    return r;
  }).catch(() => caches.match(e.request)));
});
