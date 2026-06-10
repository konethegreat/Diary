// The app's only hand-written JS: PWA service worker registration.
// Lives in a file (not inline) so CSP can stay script-src 'self' + htmx CDN.
if ("serviceWorker" in navigator) navigator.serviceWorker.register("/sw.js");
