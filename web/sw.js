// The old app (before TradeVoice 2.0) kept an offline copy of itself on phones. This worker removes that copy and
// itself, then reloads open tabs, so everyone gets the new design.
self.addEventListener("install", () => self.skipWaiting());
self.addEventListener("activate", (e) => e.waitUntil((async () => {
  for (const k of await caches.keys()) await caches.delete(k);
  await self.registration.unregister();
  for (const c of await self.clients.matchAll({ type: "window" })) c.navigate(c.url);
})()));
