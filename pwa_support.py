"""PWA 支援模組：路由 (manifest / service worker / 離線頁 / 圖示) 與 <head> 注入。

做法與 Gradio 版本無關：
  * setup_pwa(app)            在 FastAPI 上加入 PWA 需要的路由（要在 mount Gradio 之前呼叫）
  * InjectHeadMiddleware      在首頁 HTML 的 </head> 前插入 manifest、圖示、樣式與註冊 SW 的腳本
"""
from pathlib import Path

from fastapi import FastAPI
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

PWA_DIR = Path(__file__).resolve().parent / "static"  # 網址對外仍掛在 /pwa，避免與 Gradio 內建的 /static 衝突
THEME_COLOR = "#4f46e5"

# ---------------------------------------------------------------------------
# 要注入到 <head> 的內容（__CSS__ 會被 app.py 的樣式取代）
# ---------------------------------------------------------------------------
HEAD_TEMPLATE = """
<link rel="manifest" href="/manifest.webmanifest">
<meta name="theme-color" content="%(theme)s">
<meta name="mobile-web-app-capable" content="yes">
<meta name="apple-mobile-web-app-capable" content="yes">
<meta name="apple-mobile-web-app-status-bar-style" content="black-translucent">
<meta name="apple-mobile-web-app-title" content="CSV 查詢器">
<link rel="apple-touch-icon" href="/pwa/icons/apple-touch-icon.png">
<link rel="icon" type="image/png" sizes="32x32" href="/pwa/icons/favicon-32.png">
<link rel="icon" type="image/png" sizes="192x192" href="/pwa/icons/icon-192.png">
<style>
__CSS__

/* ---- PWA：安裝按鈕與離線提示 ---- */
#pwa-install {
  position: fixed; right: max(16px, env(safe-area-inset-right));
  bottom: max(16px, env(safe-area-inset-bottom)); z-index: 9999;
  min-height: 44px; padding: 0 18px; border: 0; border-radius: 999px; cursor: pointer;
  font-size: 15px; font-weight: 600; color: #fff; background: %(theme)s;
  box-shadow: 0 6px 20px rgba(15, 23, 42, .35);
}
#pwa-install[hidden] {display: none;}
#pwa-offline {
  position: fixed; left: 0; right: 0; top: 0; z-index: 9999; text-align: center;
  padding: calc(8px + env(safe-area-inset-top)) 12px 8px; font-size: 14px;
  color: #fff; background: #dc2626;
}
#pwa-offline[hidden] {display: none;}
</style>
<script>
(function () {
  if ("serviceWorker" in navigator) {
    window.addEventListener("load", function () {
      navigator.serviceWorker.register("/sw.js", { scope: "/" }).catch(function (e) {
        console.warn("Service worker 註冊失敗", e);
      });
    });
  }

  var isStandalone = window.matchMedia("(display-mode: standalone)").matches || navigator.standalone === true;
  var isIOS = /iphone|ipad|ipod/i.test(navigator.userAgent);
  var deferred = null;

  function ready(fn) {
    if (document.readyState !== "loading") fn(); else document.addEventListener("DOMContentLoaded", fn);
  }

  ready(function () {
    var btn = document.createElement("button");
    btn.id = "pwa-install"; btn.type = "button"; btn.hidden = true; btn.textContent = "📲 安裝 App";
    document.body.appendChild(btn);

    var bar = document.createElement("div");
    bar.id = "pwa-offline"; bar.hidden = true; bar.textContent = "目前離線：下載與搜尋功能暫時無法使用";
    document.body.appendChild(bar);

    function updateNet() { bar.hidden = navigator.onLine; }
    window.addEventListener("online", updateNet);
    window.addEventListener("offline", updateNet);
    updateNet();

    // Android / 桌面 Chrome、Edge：使用瀏覽器的安裝提示
    window.addEventListener("beforeinstallprompt", function (e) {
      e.preventDefault(); deferred = e;
      if (!isStandalone) btn.hidden = false;
    });
    btn.addEventListener("click", function () {
      if (deferred) {
        deferred.prompt();
        deferred.userChoice.then(function () { deferred = null; btn.hidden = true; });
      } else if (isIOS) {
        alert("請點 Safari 下方的「分享」按鈕，再選擇「加入主畫面」。");
      }
    });
    window.addEventListener("appinstalled", function () { btn.hidden = true; });

    // iOS Safari 沒有 beforeinstallprompt，改用說明提示
    if (isIOS && !isStandalone) btn.hidden = false;
  });
})();
</script>
"""


def build_head(css: str) -> str:
    return (HEAD_TEMPLATE % {"theme": THEME_COLOR}).replace("__CSS__", css)


# ---------------------------------------------------------------------------
# ASGI middleware：把 head 內容插進首頁 HTML
# ---------------------------------------------------------------------------
class InjectHeadMiddleware:
    def __init__(self, app, head_html: str):
        self.app = app
        self.head_html = head_html

    async def __call__(self, scope, receive, send):
        is_index = (
            scope["type"] == "http"
            and scope.get("method") == "GET"
            and scope.get("path") in ("/", "")
        )
        if not is_index:
            await self.app(scope, receive, send)
            return

        # 不接受壓縮，才能直接改寫 HTML
        scope = dict(scope)
        scope["headers"] = [(k, v) for k, v in scope["headers"] if k.lower() != b"accept-encoding"]

        start_message = None
        chunks = []

        async def send_wrapper(message):
            nonlocal start_message
            if message["type"] == "http.response.start":
                start_message = message
                return
            if message["type"] != "http.response.body":
                await send(message)
                return

            chunks.append(message.get("body", b""))
            if message.get("more_body"):
                return

            body = b"".join(chunks)
            headers = list(start_message["headers"])
            content_type = dict((k.lower(), v) for k, v in headers).get(b"content-type", b"")
            if b"text/html" in content_type:
                text = body.decode("utf-8", errors="replace")
                if "</head>" in text:
                    text = text.replace("</head>", self.head_html + "</head>", 1)
                    body = text.encode("utf-8")
            headers = [(k, v) for k, v in headers if k.lower() != b"content-length"]
            headers.append((b"content-length", str(len(body)).encode()))
            await send({**start_message, "headers": headers})
            await send({"type": "http.response.body", "body": body})

        await self.app(scope, receive, send_wrapper)


# ---------------------------------------------------------------------------
# 路由
# ---------------------------------------------------------------------------
def setup_pwa(app: FastAPI) -> None:
    """加入 PWA 路由。請在 gr.mount_gradio_app(...) 之前呼叫。"""

    @app.get("/manifest.webmanifest", include_in_schema=False)
    def manifest():
        return FileResponse(
            PWA_DIR / "manifest.webmanifest",
            media_type="application/manifest+json",
            headers={"Cache-Control": "no-cache"},
        )

    @app.get("/sw.js", include_in_schema=False)
    def service_worker():
        # Service worker 必須從網站根目錄提供，才能控制整個 "/" 範圍
        return FileResponse(
            PWA_DIR / "sw.js",
            media_type="application/javascript",
            headers={"Cache-Control": "no-cache", "Service-Worker-Allowed": "/"},
        )

    @app.get("/offline", include_in_schema=False)
    def offline():
        return FileResponse(PWA_DIR / "offline.html", media_type="text/html")

    @app.get("/healthz", include_in_schema=False)
    def healthz():
        return JSONResponse({"status": "ok"})

    app.mount("/pwa", StaticFiles(directory=PWA_DIR), name="pwa")
