/* يعمل بدون إنترنت: الواجهة من الذاكرة، والبيانات من الشبكة أولًا ثم الذاكرة */
const CACHE = "vision-news-v1";
const SHELL = ["./", "index.html", "styles.css", "app.js", "icon.svg", "icon-192.png", "manifest.webmanifest"];
self.addEventListener("install", (e) => { e.waitUntil(caches.open(CACHE).then((c) => c.addAll(SHELL))); self.skipWaiting(); });
self.addEventListener("activate", (e) => { e.waitUntil(caches.keys().then((ks) => Promise.all(ks.filter((k) => k !== CACHE).map((k) => caches.delete(k))))); self.clients.claim(); });
self.addEventListener("fetch", (e) => {
  const url = new URL(e.request.url);
  if (e.request.method !== "GET") return;
  const net = fetch(e.request).then((r) => { if (r.ok && (url.origin === location.origin || url.hostname.includes("fonts."))) { const c = r.clone(); caches.open(CACHE).then((x) => x.put(e.request, c)); } return r; });
  if (url.pathname.includes("/data/") || SHELL.some((s) => url.pathname.endsWith(s.replace("./", "/")))) {
    e.respondWith(net.catch(() => caches.match(e.request)));   // الشبكة أولًا
  } else {
    e.respondWith(caches.match(e.request).then((m) => m || net)); // الذاكرة أولًا (الخطوط)
  }
});
