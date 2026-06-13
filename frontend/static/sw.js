// Minimal service worker: required for PWA installability.
// Network-first for same-origin GETs; falls back to cache for the app shell
// when offline.
//
// Cross-origin requests (the Google Fonts CSS, the htmx CDN, chrome-extension
// probes) are deliberately NOT intercepted: a fetch() issued from inside the
// SW is governed by the page's `connect-src` directive, so re-fetching them
// here would trip the strict CSP (connect-src 'self'). Leaving respondWith
// uncalled lets the browser load them directly under style-src/script-src.
const CACHE = "diary-v1";
const SHELL = ["/", "/static/app.css", "/static/icon.svg"];

self.addEventListener("install", (e) => {
  e.waitUntil(caches.open(CACHE).then((c) => c.addAll(SHELL)));
  self.skipWaiting();
});

self.addEventListener("activate", (e) => {
  e.waitUntil(
    caches
      .keys()
      .then((keys) => Promise.all(keys.filter((k) => k !== CACHE).map((k) => caches.delete(k))))
      .then(() => self.clients.claim())
  );
});

self.addEventListener("fetch", (e) => {
  const req = e.request;
  if (req.method !== "GET") return;
  // Only ever handle our own origin over http(s); everything else falls
  // through to the browser untouched (see header comment).
  if (new URL(req.url).origin !== self.location.origin) return;

  e.respondWith(
    fetch(req)
      .then((res) => {
        const copy = res.clone();
        caches.open(CACHE).then((c) => c.put(req, copy));
        return res;
      })
      .catch(async () => {
        const cached = (await caches.match(req)) || (req.mode === "navigate" && (await caches.match("/")));
        return cached || Response.error();
      })
  );
});
