// App-shell service worker for the CoA-Agent PWA.
//
// Not registered from index.html yet — this file is inert until something
// calls navigator.serviceWorker.register("/sw.js"). See the "activating
// this later" note wherever this was introduced for the couple of lines
// that turn it on.
//
// Bump CACHE_NAME on every deploy that changes cached files; the activate
// handler below deletes any cache that doesn't match, so stale clients
// don't get stuck on old assets.
const CACHE_NAME = "coa-agent-shell-v1";
const APP_SHELL = ["/", "/index.html", "/manifest.json"];

self.addEventListener("install", (event) => {
  event.waitUntil(caches.open(CACHE_NAME).then((cache) => cache.addAll(APP_SHELL)));
  self.skipWaiting();
});

self.addEventListener("activate", (event) => {
  event.waitUntil(
    caches.keys().then((names) =>
      Promise.all(names.filter((name) => name !== CACHE_NAME).map((name) => caches.delete(name))),
    ),
  );
  self.clients.claim();
});

self.addEventListener("fetch", (event) => {
  const url = new URL(event.request.url);

  // Never cache API calls — chat, auth, and preferences must always hit the
  // network fresh. This also matters for correctness, not just freshness:
  // caching a POST /api/chat response would be actively wrong.
  if (url.pathname.startsWith("/api/")) return;
  if (event.request.method !== "GET") return;

  // Network-first for the app shell: this project is under active
  // development, so a stale cached index.html/JS after a deploy would be
  // a worse experience than just requiring network on first load. Cache is
  // only a fallback for when the network is unavailable.
  event.respondWith(
    fetch(event.request)
      .then((response) => {
        const copy = response.clone();
        caches.open(CACHE_NAME).then((cache) => cache.put(event.request, copy));
        return response;
      })
      .catch(() => caches.match(event.request)),
  );
});
