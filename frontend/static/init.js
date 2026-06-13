// The app's only hand-written JS. Kept in a file (never inline, never eval'd)
// so the CSP can stay script-src 'self' + the htmx CDN, with no 'unsafe-eval'.
//
// Besides registering the service worker, this replaces the two htmx features
// that would otherwise need eval (and so are blocked by the CSP):
//   - hx-on::after-request="...this.reset()"  -> [data-reset]
//   - hx-trigger="keyup[key=='Enter']"        -> [data-enter-trigger]

if ("serviceWorker" in navigator) navigator.serviceWorker.register("/sw.js");

// Reset any form marked [data-reset] after a successful htmx request.
document.body.addEventListener("htmx:afterRequest", (e) => {
  const form = e.detail.elt;
  if (e.detail.successful && form instanceof HTMLFormElement && form.hasAttribute("data-reset")) {
    form.reset();
  }
});

// Fire an htmx request on Enter for inputs marked [data-enter-trigger]; the
// element listens for hx-trigger="enter-trigger". preventDefault stops the
// surrounding form from also submitting.
document.body.addEventListener("keydown", (e) => {
  const el = e.target;
  if (e.key === "Enter" && el instanceof HTMLElement && el.hasAttribute("data-enter-trigger")) {
    e.preventDefault();
    window.htmx.trigger(el, "enter-trigger");
  }
});
