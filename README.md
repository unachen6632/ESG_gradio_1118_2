# 📊 公開資料 CSV 查詢器（PWA + RWD）

使用 **Gradio 6** 製作的網頁工具：輸入 CSV 連結後，一鍵下載、清理（移除空值）、關鍵字搜尋、選擇顯示欄位，並匯出結果為 CSV（UTF-8-SIG，Excel 開啟不亂碼）。

- ✅ **PWA**：可安裝到手機主畫面 / 桌面，以獨立視窗開啟，有圖示與離線提示頁
- ✅ **RWD**：桌機左右分欄、平板與手機自動改為上下堆疊，表格可左右滑動、第一欄固定

預設資料來源：`https://mopsfin.twse.com.tw/opendata/t187ap46_0_1.csv`

## 專案結構

```
.
├── .python-version      # Render 使用的 Python 版本 (3.12.3)
├── app.py               # Gradio 介面 + FastAPI 組裝
├── pwa_support.py       # PWA 路由、<head> 注入（manifest / 圖示 / 安裝按鈕）
├── static/
│   ├── manifest.webmanifest
│   ├── sw.js            # Service Worker
│   ├── offline.html     # 離線提示頁
│   └── icons/           # 192 / 512 / maskable / apple-touch / favicon
├── tools/make_icons.py  # 重新產生圖示（需 Pillow，非部署必要）
├── requirements.txt
├── render.yaml          # Render Blueprint（可選）
└── README.md
```

## 本機執行

```bash
python -m venv .venv
source .venv/bin/activate          # Windows: .venv\Scripts\activate
pip install -r requirements.txt
python app.py
```

開啟 http://localhost:7860 。`localhost` 視為安全來源，因此本機也能測試 PWA。

## 部署到 Render

1. 把專案推到 GitHub。
2. Render → **New +** → **Web Service** → 選擇該 repo。
3. 設定：

   | 欄位 | 值 |
   |---|---|
   | Runtime | Python 3 |
   | Build Command | `pip install -r requirements.txt` |
   | Start Command | `python app.py` |
   | Health Check Path | `/healthz` |
   | 環境變數 | `PYTHON_VERSION` = `3.12.3` |

   或直接用 **New + → Blueprint**，Render 會讀取 `render.yaml`。
4. 部署完成後用 Render 提供的 `https://xxx.onrender.com` 開啟。**PWA 必須在 HTTPS 下才能安裝**，Render 預設就是 HTTPS。

## 安裝成 App

| 裝置 | 方式 |
|---|---|
| Android Chrome / 桌面 Chrome、Edge | 點畫面右下角「📲 安裝 App」，或網址列的安裝圖示 |
| iPhone / iPad（Safari） | 點「分享」→「加入主畫面」（畫面右下角的按鈕會顯示操作說明） |

## PWA 運作說明

- `static/` 資料夾的內容對外網址掛在 `/pwa/...`（例如 `/pwa/icons/icon-192.png`），這是刻意避開 Gradio 內建使用的 `/static` 路徑，否則會讓 Gradio 自己的資源 404。

- `pwa_support.py` 在首頁 HTML 的 `</head>` 前插入 manifest、圖示、主題色、安裝按鈕與註冊 Service Worker 的腳本。這個做法不依賴 Gradio 的版本。
- `/sw.js` 由根路徑提供（含 `Service-Worker-Allowed: /`），才能控制整個網站範圍。
- Service Worker 策略：頁面導覽網路優先、失敗顯示離線頁；圖示快取優先；其他靜態資源網路優先。**Gradio 的 API 路徑一律不快取**。
- **離線限制**：資料下載與搜尋都在伺服器端執行，離線時無法使用，只會顯示離線提示。
- 改版後請把 `static/sw.js` 裡的 `VERSION` 加一（例如 `csv-viewer-v2`），讓舊快取被清除。
- Render 免費方案閒置會休眠，PWA 開啟時可能要等數十秒喚醒。

## RWD 斷點

| 寬度 | 行為 |
|---|---|
| > 900px | 左側設定、右側結果並排 |
| ≤ 900px | 上下堆疊，欄位滿版 |
| ≤ 600px | 按鈕觸控區 ≥ 44px、輸入框 16px（避免 iOS 自動放大）、表格第一欄固定 |

樣式都在 `app.py` 的 `CSS` 變數裡。

## 自訂

- 換圖示：修改 `tools/make_icons.py` 後執行 `python tools/make_icons.py`
- 改名稱 / 主題色：編輯 `static/manifest.webmanifest` 與 `pwa_support.py` 的 `THEME_COLOR`
- 畫面顯示筆數：`app.py` 的 `MAX_ROWS`（完整資料仍可下載）

## 檢查 PWA 是否正確

Chrome 開發者工具 → **Application** 分頁：看 Manifest、Service Workers 是否正常；或用 **Lighthouse** 的 PWA 項目檢查。

## 注意

- 預設關閉 SSL 驗證是為了相容部分政府網站的憑證問題；若來源憑證正常，建議勾選「驗證 SSL 憑證」。
- 本專案沒有登入機制，任何人都能輸入網址讓伺服器去下載。若要公開使用，建議加上網域白名單或存取限制。

## 授權

MIT
