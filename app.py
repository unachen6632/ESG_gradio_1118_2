"""公開資料 CSV 查詢器 — Gradio 6 + PWA + RWD，可部署於 Render / 本機

啟動方式：
    python app.py                      （本機或 Render 的 Start Command）
    uvicorn app:app --host 0.0.0.0     （等價）
"""
import html as _html
import inspect
import io
import os
import tempfile
import uuid

import pandas as pd
import requests
import urllib3
import gradio as gr
from fastapi import FastAPI

from pwa_support import InjectHeadMiddleware, build_head, setup_pwa

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

# 注意：網址中的 L = 上市、O = 上櫃（英文字母 O，不是數字 0）
PRESETS = {
    "上市公司 ESG－溫室氣體排放": "https://mopsfin.twse.com.tw/opendata/t187ap46_L_1.csv",
    "上櫃公司 ESG－溫室氣體排放": "https://mopsfin.twse.com.tw/opendata/t187ap46_O_1.csv",
    "上市公司基本資料": "https://mopsfin.twse.com.tw/opendata/t187ap03_L.csv",
}
CUSTOM = "自訂（手動輸入連結）"
DEFAULT_PRESET = "上市公司 ESG－溫室氣體排放"
DEFAULT_URL = PRESETS[DEFAULT_PRESET]
HEADERS = {"User-Agent": "Mozilla/5.0 (Gradio CSV Viewer)"}
MAX_ROWS = 500  # 畫面最多顯示幾筆（完整資料可下載）


# ---------------------------------------------------------------------------
# 工具函式
# ---------------------------------------------------------------------------
def export_csv(df):
    """每次匯出都用獨立檔名，避免多位使用者同時使用時互相覆蓋。"""
    path = os.path.join(tempfile.gettempdir(), f"data_{uuid.uuid4().hex[:8]}.csv")
    df.to_csv(path, index=False, encoding="utf-8-sig")
    return path


def render_table(df, placeholder="請先按「🚀 下載並載入」"):
    """固定高度的 HTML 表格：版面不會因資料變動而跳動，手機可左右滑動。"""
    if df is None or len(df) == 0:
        return f"<div class='tbl-wrap'><div class='tbl-empty'>{_html.escape(placeholder)}</div></div>"
    shown = df.head(MAX_ROWS)
    table = shown.to_html(index=False, border=0, classes="tbl", na_rep="", escape=True)
    note = ""
    if len(df) > MAX_ROWS:
        note = (f"<div class='tbl-note'>畫面僅顯示前 {MAX_ROWS:,} 筆，共 {len(df):,} 筆；"
                f"完整結果請用下方按鈕下載。</div>")
    return f"<div class='tbl-wrap'>{table}</div>{note}"


def build_stats(df, raw_rows):
    removed = raw_rows - len(df)
    return (
        "| 📄 資料筆數 | 🧱 欄位數 | 🧹 移除筆數 |\n"
        "|:---:|:---:|:---:|\n"
        f"| **{len(df):,}** | **{df.shape[1]}** | **{removed:,}** |"
    )


# ---------------------------------------------------------------------------
# 核心功能
# ---------------------------------------------------------------------------
def _download(url, verify):
    resp = requests.get(url, verify=verify, timeout=30, headers=HEADERS)
    resp.raise_for_status()
    return resp


def fetch_data(url, drop_na, verify_ssl):
    url = (url or "").strip()
    if not url:
        return (None, render_table(None), "⚠️ 請輸入 CSV 連結。", "",
                gr.update(choices=[], value=[]), None)
    note = ""
    try:
        try:
            resp = _download(url, verify_ssl)
        except requests.HTTPError as e:
            # 常見筆誤：代表「上櫃」的英文字母 O 被寫成數字 0（t187ap46_0_1 → t187ap46_O_1）
            code = e.response.status_code if e.response is not None else None
            if code == 404 and "_0_" in url:
                url = url.replace("_0_", "_O_")
                resp = _download(url, verify_ssl)
                note = f"\n\n🔧 原網址找不到，已自動把數字 0 改成英文字母 O：{url}"
            else:
                raise

        df = pd.read_csv(io.BytesIO(resp.content), encoding="utf-8-sig")  # 繁體中文
        raw_rows = len(df)
        if drop_na:
            df = df.dropna()

        status = f"✅ 下載成功！原始 **{raw_rows:,}** 筆，目前保留 **{len(df):,}** 筆資料。{note}"
        return (
            df,
            render_table(df, "（沒有資料）"),
            status,
            build_stats(df, raw_rows),
            gr.update(choices=list(df.columns), value=[]),
            export_csv(df),
        )
    except requests.HTTPError as e:
        code = e.response.status_code if e.response is not None else "?"
        hint = "網址不存在，請確認連結是否正確，或從上方「資料集」選單挑選。" if code == 404 else "伺服器拒絕或發生錯誤。"
        msg = f"❌ HTTP {code}：{hint}\n\n連結：{url}"
    except Exception as e:
        msg = f"❌ 發生錯誤：{e}"
    return (None, render_table(None), msg, "", gr.update(choices=[], value=[]), None)


def pick_preset(name):
    return PRESETS[name] if name in PRESETS else gr.update()


def filter_data(full_df, keyword, show_cols):
    if full_df is None or len(full_df) == 0:
        return render_table(None), "⚠️ 請先下載資料。", None

    df = full_df.copy()
    keyword = (keyword or "").strip()

    if keyword:
        mask = df.astype(str).apply(
            lambda col: col.str.contains(keyword, case=False, na=False, regex=False)
        ).any(axis=1)
        df = df[mask]

    if show_cols:
        df = df[show_cols]

    msg = f"🔎 符合條件：**{len(df):,}** 筆"
    if keyword:
        msg += f"（關鍵字：`{keyword}`）"
    return render_table(df, "沒有符合的資料"), msg, export_csv(df)


def reset_filter(full_df):
    if full_df is None:
        return render_table(None), "", [], None, ""
    return render_table(full_df), f"🔄 已重設，共 **{len(full_df):,}** 筆", [], export_csv(full_df), ""


# ---------------------------------------------------------------------------
# 樣式（含 RWD）— 由 pwa_support 注入 <head>，不依賴 Gradio 版本
# ---------------------------------------------------------------------------
CSS = """
/* ===== 基礎 ===== */
.gradio-container {
  max-width: 1200px !important; margin: 0 auto !important;
  padding-left: max(12px, env(safe-area-inset-left)) !important;
  padding-right: max(12px, env(safe-area-inset-right)) !important;
  padding-bottom: calc(80px + env(safe-area-inset-bottom)) !important;  /* 留空間給安裝按鈕 */
}
.gradio-container .prose, .gradio-container .prose * {overflow-wrap: anywhere; word-break: break-word;}
#title {text-align: center; padding: 18px 0 4px;}
#title h1 {font-size: clamp(1.4rem, 4.5vw, 2rem); margin-bottom: 4px;}
#title p {color: #64748b; font-size: clamp(.85rem, 2.6vw, 1rem);}

/* ===== 表格（固定高度、可雙向捲動、表頭固定）===== */
.tbl-wrap {
  height: clamp(280px, 62vh, 560px); overflow: auto; -webkit-overflow-scrolling: touch;
  border: 1px solid var(--border-color-primary); border-radius: 10px;
}
.tbl {border-collapse: collapse; width: max-content; min-width: 100%; font-size: 14px;}
.tbl th, .tbl td {
  padding: 8px 12px; white-space: nowrap; text-align: left;
  border-bottom: 1px solid var(--border-color-primary);
}
.tbl th {
  position: sticky; top: 0; z-index: 2;
  background: var(--background-fill-secondary); font-weight: 600;
}
.tbl tbody tr:hover td {background: var(--background-fill-secondary);}
.tbl-empty {padding: 40px 16px; text-align: center; color: #94a3b8;}
.tbl-note {margin-top: 6px; font-size: 13px; color: #94a3b8;}

/* ===== 平板與手機：左右欄改為上下堆疊 ===== */
@media (max-width: 900px) {
  .app-row {flex-direction: column !important; gap: 16px !important;}
  .side-col, .main-col {
    width: 100% !important; min-width: 0 !important; max-width: 100% !important; flex: none !important;
  }
}

/* ===== 手機：加大觸控區、縮小字級 ===== */
@media (max-width: 600px) {
  .gradio-container button {min-height: 44px;}
  .gradio-container input, .gradio-container textarea {font-size: 16px !important;}  /* 避免 iOS 聚焦時自動放大 */
  .tbl {font-size: 13px;}
  .tbl th, .tbl td {padding: 7px 10px;}
  /* 第一欄固定，左右滑動時仍看得到代號/名稱 */
  .tbl th:first-child, .tbl td:first-child {
    position: sticky; left: 0; z-index: 1; background: var(--background-fill-primary);
    box-shadow: 1px 0 0 var(--border-color-primary);
  }
  .tbl th:first-child {z-index: 3; background: var(--background-fill-secondary);}
}
"""

theme = gr.themes.Soft(primary_hue="indigo", secondary_hue="sky", neutral_hue="slate")


def _accepted(func, **kwargs):
    """只傳入該函式支援的參數，讓程式同時相容 Gradio 5 / 6。"""
    params = inspect.signature(func).parameters
    return {k: v for k, v in kwargs.items() if k in params}


# Gradio 5：theme 在 Blocks()；Gradio 6：theme 移到 launch()/mount_gradio_app()
_blocks_kw = _accepted(gr.Blocks.__init__, theme=theme)
_mount_kw = {} if _blocks_kw else _accepted(gr.mount_gradio_app, theme=theme)

# ---------------------------------------------------------------------------
# 介面
# ---------------------------------------------------------------------------
with gr.Blocks(title="公開資料 CSV 查詢器", **_blocks_kw) as demo:
    full_df_state = gr.State(None)

    gr.HTML(
        """
        <div id="title">
          <h1>📊 公開資料 CSV 查詢器</h1>
          <p>輸入 CSV 連結，一鍵下載、清理、搜尋並匯出資料</p>
        </div>
        """
    )

    with gr.Row(elem_classes="app-row"):
        with gr.Column(scale=1, min_width=280, elem_classes="side-col"):
            gr.Markdown("### ⚙️ 資料來源")
            preset_in = gr.Dropdown(
                label="資料集", choices=list(PRESETS) + [CUSTOM], value=DEFAULT_PRESET
            )
            url_in = gr.Textbox(label="CSV 連結", value=DEFAULT_URL, lines=2)
            drop_na = gr.Checkbox(label="移除含空值的資料列 (dropna)", value=True)
            verify_ssl = gr.Checkbox(label="驗證 SSL 憑證 (verify)", value=False)
            fetch_btn = gr.Button("🚀 下載並載入", variant="primary", size="lg")
            status_md = gr.Markdown()
            stats_md = gr.Markdown()

            gr.Markdown("### 🔍 搜尋與篩選")
            keyword_in = gr.Textbox(label="關鍵字", placeholder="例如：公司名稱、代號…")
            cols_in = gr.Dropdown(label="只顯示指定欄位（留空＝全部）", choices=[], multiselect=True)
            with gr.Row():
                search_btn = gr.Button("搜尋", variant="primary")
                reset_btn = gr.Button("重設")
            filter_md = gr.Markdown()

        with gr.Column(scale=3, min_width=280, elem_classes="main-col"):
            gr.Markdown("### 📋 資料預覽")
            table = gr.HTML(render_table(None))
            file_out = gr.File(label="⬇️ 下載目前結果 (CSV, UTF-8-SIG)")

    gr.Markdown(
        "<center style='color:#94a3b8'>Made with Gradio · 資料來源：使用者提供之公開 CSV 連結</center>"
    )

    preset_in.change(pick_preset, inputs=preset_in, outputs=url_in)
    fetch_btn.click(
        fetch_data,
        inputs=[url_in, drop_na, verify_ssl],
        outputs=[full_df_state, table, status_md, stats_md, cols_in, file_out],
    )
    search_btn.click(
        filter_data,
        inputs=[full_df_state, keyword_in, cols_in],
        outputs=[table, filter_md, file_out],
    )
    keyword_in.submit(
        filter_data,
        inputs=[full_df_state, keyword_in, cols_in],
        outputs=[table, filter_md, file_out],
    )
    reset_btn.click(
        reset_filter,
        inputs=[full_df_state],
        outputs=[table, filter_md, cols_in, file_out, keyword_in],
    )

# ---------------------------------------------------------------------------
# FastAPI 組裝：先加 PWA 路由，再把 Gradio 掛在根目錄
# ---------------------------------------------------------------------------
app = FastAPI(title="CSV Viewer")
setup_pwa(app)
app = gr.mount_gradio_app(app, demo, path="/", **_mount_kw)
app.add_middleware(InjectHeadMiddleware, head_html=build_head(CSS))


if __name__ == "__main__":
    import uvicorn

    # Render 會提供 PORT 環境變數，且必須綁定 0.0.0.0；proxy_headers 讓 https 判斷正確
    port = int(os.environ.get("PORT", 7860))
    uvicorn.run(app, host="0.0.0.0", port=port, proxy_headers=True, forwarded_allow_ips="*")
