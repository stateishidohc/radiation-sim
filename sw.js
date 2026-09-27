/* 被ばく予測・リスコミツール — Service Worker
   - HTML等はネットワーク優先（更新をすぐ反映）、圏外時のみキャッシュで動作
   - アイコン・地図ライブラリ（CDN）はキャッシュ優先
   - モニタリングデータ（GitHub の raw）はネットワーク優先、圏外時は最後に取得したデータ
   - 地図タイル（国土地理院）はキャッシュしない（オンライン時のみ表示） */
const CACHE = "radsim-v2.5";
const ASSETS = [
  "./",
  "./index.html",
  "./manifest.json",
  "./icons/icon-192.png",
  "./icons/icon-512.png",
  "./icons/apple-touch-icon.png",
  "./icons/favicon-32.png",
];
const CDN = [
  "https://cdn.jsdelivr.net/npm/leaflet@1.9.4/dist/leaflet.css",
  "https://cdn.jsdelivr.net/npm/leaflet@1.9.4/dist/leaflet.js",
];

self.addEventListener("install", e => {
  e.waitUntil(
    caches.open(CACHE).then(async c => {
      await c.addAll(ASSETS);
      // CDN は失敗してもインストールを止めない
      await Promise.all(CDN.map(u => c.add(new Request(u, { mode: "cors" })).catch(() => {})));
    }).then(() => self.skipWaiting())
  );
});

self.addEventListener("activate", e => {
  e.waitUntil(
    caches.keys().then(keys => Promise.all(keys.filter(k => k !== CACHE).map(k => caches.delete(k))))
      .then(() => self.clients.claim())
  );
});

self.addEventListener("fetch", e => {
  if (e.request.method !== "GET") return;
  const url = new URL(e.request.url);
  const sameOrigin = url.origin === location.origin;
  const isCdn = url.hostname === "cdn.jsdelivr.net";
  const isData = url.hostname === "raw.githubusercontent.com" || url.pathname.endsWith("monitoring.json");
  if (!sameOrigin && !isCdn && !isData) return; // 地図タイル等は素通し

  const isFresh = isData || (sameOrigin && (e.request.mode === "navigate" ||
    url.pathname.endsWith("/") || url.pathname.endsWith(".html") || url.pathname.endsWith("manifest.json")));

  if (isFresh) {
    e.respondWith(
      fetch(e.request).then(res => {
        if (res.ok) { const clone = res.clone(); caches.open(CACHE).then(c => c.put(e.request, clone)); }
        return res;
      }).catch(() => caches.match(e.request, { ignoreSearch: true }).then(r => r || caches.match("./index.html")))
    );
  } else {
    e.respondWith(
      caches.match(e.request).then(cached => {
        const fetched = fetch(e.request).then(res => {
          if (res.ok) { const clone = res.clone(); caches.open(CACHE).then(c => c.put(e.request, clone)); }
          return res;
        }).catch(() => cached);
        return cached || fetched;
      })
    );
  }
});
