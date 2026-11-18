/* Service Worker — 公開資料 CSV 查詢器
 * 改版後請把 VERSION 加一，讓舊快取被清掉。
 * 注意：Gradio 的資料處理在伺服器端，離線時無法下載/搜尋資料，
 * 因此這裡只負責「可安裝」、「圖示/靜態資源快取」與「離線提示頁」。 */
const VERSION = "csv-viewer-v1";
const CORE = [
  "/offline",
  "/manifest.webmanifest",
  "/pwa/icons/icon-192.png",
  "/pwa/icons/icon-512.png",
];
// 這些路徑是 Gradio 的動態 API，絕對不能被快取
const BYPASS = ["/gradio_api", "/queue", "/upload", "/file=", "/stream", "/heartbeat",
                "/config", "/info", "/login", "/logout", "/run", "/api", "/healthz"];

self.addEventListener("install", (event) => {
  event.waitUntil(
    caches.open(VERSION).then((c) => c.addAll(CORE)).then(() => self.skipWaiting())
  );
});

self.addEventListener("activate", (event) => {
  event.waitUntil(
    caches.keys()
      .then((keys) => Promise.all(keys.filter((k) => k !== VERSION).map((k) => caches.delete(k))))
      .then(() => self.clients.claim())
  );
});

self.addEventListener("fetch", (event) => {
  const req = event.request;
  if (req.method !== "GET") return;

  const url = new URL(req.url);
  if (url.origin !== self.location.origin) return;
  if (BYPASS.some((p) => url.pathname.startsWith(p))) return;

  // 頁面導覽：優先走網路，失敗才顯示離線頁
  if (req.mode === "navigate") {
    event.respondWith(fetch(req).catch(() => caches.match("/offline")));
    return;
  }

  // 圖示：快取優先
  if (url.pathname.startsWith("/pwa/icons/")) {
    event.respondWith(caches.match(req).then((hit) => hit || fetch(req)));
    return;
  }

  // 其他靜態資源：網路優先，失敗時用快取
  if (["style", "script", "font", "image"].includes(req.destination)) {
    event.respondWith(
      fetch(req)
        .then((res) => {
          if (res && res.ok) {
            const copy = res.clone();
            caches.open(VERSION).then((c) => c.put(req, copy));
          }
          return res;
        })
        .catch(() => caches.match(req))
    );
  }
});
