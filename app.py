import threading
import time
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

import altair as alt
import pandas as pd
import streamlit as st


st.set_page_config(
    page_title="中央線快速 遅延リスク予測・遅延実績",
    layout="wide",
)

st.markdown(
    """
    <style>
    .stApp {
        background:
            radial-gradient(ellipse at 85% 4%, rgba(190, 160, 105, 0.09), transparent 27%),
            #f6f4ef;
        color: #252a31;
        font-family: "Yu Gothic UI", "Meiryo", "Noto Sans JP", serif;
    }
    .main .block-container {
        max-width: 1120px;
        padding: 5.2rem 2rem 4.5rem;
    }
    /* ページの切り替えは上のメニューで行うので、Streamlit 標準の左サイドバーは出さない */
    section[data-testid="stSidebar"],
    [data-testid="stSidebarCollapsedControl"],
    [data-testid="stExpandSidebarButton"] {
        display: none !important;
    }
    .hero h1 [data-testid="stHeaderActionElements"] {
        display: none;                  /* 見出しの横に出るリンク用アイコン（タイトルの下に余白を作る原因） */
    }
    header[data-testid="stHeader"] {
        background: #f6f4ef;            /* 透明だと、スクロールした中身が上のすき間に透けて見えるので、背景と同じ色で塗る */
    }
    .hero {
        position: relative;
        overflow: hidden;
        padding: 2.55rem 2.7rem;
        margin: 0 0 2rem;
        border: 1px solid rgba(226, 198, 139, 0.35);
        border-radius: 5px;
        color: white;
        background:
            radial-gradient(ellipse at 88% 20%, rgba(179, 147, 87, 0.17), transparent 35%),
            linear-gradient(112deg, #171b20 0%, #222831 60%, #30353a 100%);
        box-shadow: 0 18px 42px rgba(33, 36, 40, 0.16);
    }
    .hero::after {
        position: absolute;
        top: 50%;
        right: 3.5rem;
        width: 150px;
        height: 150px;
        border: 1px solid rgba(214, 189, 131,  0.22);
        border-radius: 50%;
        content: "";
        opacity: 0.8;
        transform: translateY(-50%);
    }
    .hero-kicker::after {
        display: block;
        width: 44px;
        height: 1px;
        margin-top: 0.7rem;
        background: #b69b63;
        content: "";
    }
    .hero::before {
        position: absolute;
        top: 0;
        left: 2.7rem;
        width: 66px;
        height: 3px;
        background: #d6bd83;
        content: "";
    }
    .hero-kicker {
        margin-bottom: 0.75rem;
        color: #d8c493;
        font-family: "Yu Gothic UI", "Meiryo", sans-serif;
        font-size: 0.7rem;
        font-weight: 700;
        letter-spacing: 0.22em;
        text-transform: uppercase;
    }
    .hero-title {
        margin: 0;
        color: white;
        font-size: clamp(1.8rem, 3vw, 2.5rem);
        font-weight: 650;
        letter-spacing: 0.08em;
        line-height: 1.45;
    }
    .hero-caption {
        margin: 0.8rem 0 0;
        color: #c6c5c0;
        font-family: "Yu Gothic UI", "Meiryo", sans-serif;
        font-size: 0.9rem;
        letter-spacing: 0.04em;
    }
    .home-nav {
        position: fixed;
        top: 3rem;
        left: 0;
        z-index: 1000000;
        display: flex;
        justify-content: center;
        gap: 0.65rem;
        overflow-x: auto;
        width: 100%;
        box-sizing: border-box;
        padding: 0.75rem max(1.2rem, calc((100% - 1120px) / 2));
        border-bottom: 1px solid rgba(214, 189, 131, 0.42);
        background: rgba(27, 30, 34, 0.97);
        box-shadow: 0 8px 24px rgba(28, 29, 30, 0.16);
        backdrop-filter: blur(16px);
        scrollbar-width: thin;
    }
    .home-nav a {
        flex: 0 0 auto;
        position: relative;
        z-index: 1;
        display: inline-flex;
        align-items: center;
        padding: 0.42rem 0.85rem;
        border: 1px solid transparent;
        border-radius: 3px;
        color: #e4dfd3 !important;
        font-family: "Yu Gothic UI", "Meiryo", sans-serif;
        font-size: 0.82rem;
        font-weight: 600;
        letter-spacing: 0.03em;
        text-decoration: none !important;
        cursor: pointer;
        pointer-events: auto;
        touch-action: manipulation;
        transition: color 160ms ease, background 160ms ease, border-color 160ms ease, transform 160ms ease;
    }
    .home-nav a::before {
        margin-right: 0.5rem;
        color: #c6aa70;
        font-family: "Yu Gothic UI", "Meiryo", sans-serif;
        font-size: 0.68rem;
        font-weight: 700;
        letter-spacing: 0.08em;
    }
    .home-nav a:nth-child(1)::before { content: "01"; }
    .home-nav a:nth-child(2)::before { content: "02"; }
    .home-nav a:nth-child(3)::before { content: "03"; }
    .home-nav a:nth-child(4)::before { content: "04"; }
    .home-nav a:nth-child(5)::before { content: "05"; }
    .home-nav a:nth-child(6)::before { content: "06"; }
    .home-nav a:hover {
        border-color: rgba(214, 189, 131, 0.55);
        color: #fff !important;
        background: rgba(214, 189, 131, 0.11);
        transform: translateY(-1px);
    }
    html {
        scroll-behavior: smooth;
        scroll-padding-top: 8rem;
    }
    .section-heading {
        scroll-margin-top: 8rem;
        display: flex;
        align-items: center;
        gap: 0.8rem;
        margin: 2.35rem 0 1rem;
        color: #292c30;
        font-size: 1.16rem;
        font-weight: 700;
        letter-spacing: 0.045em;
    }
    .section-heading::after {
        width: 36px;
        height: 1px;
        background: #b59a61;
        content: "";
    }
    .chart-axis-label {
        margin: 0.4rem 0 0.2rem 0.5rem;
        color: #65635d;
        font-family: "Yu Gothic UI", "Meiryo", sans-serif;
        font-size: 0.82rem;
        font-weight: 600;
        letter-spacing: 0.025em;
    }
    div[data-testid="stVerticalBlockBorderWrapper"] {
        border-color: #e6e0d4;
        border-radius: 5px;
        background: rgba(255, 254, 251, 0.88);
        box-shadow: 0 8px 24px rgba(46, 42, 34, 0.045);
    }
    div[data-testid="stMetric"] {
        min-height: 116px;
        padding: 1.1rem 1.15rem;
        border: 1px solid #ece6db;
        border-top: 2px solid #b69b63;
        border-radius: 4px;
        background: linear-gradient(145deg, #fffefb, #f8f6f0);
    }
    div[data-testid="stMetricLabel"] {
        color: #77736a;
        font-family: "Yu Gothic UI", "Meiryo", sans-serif;
        font-size: 0.82rem;
        font-weight: 600;
        letter-spacing: 0.04em;
    }
    div[data-testid="stMetricValue"] {
        color: #252a31;
        font-weight: 700;
    }
    div[data-testid="stSelectbox"] label,
    div[data-testid="stFileUploader"] label {
        color: #484943;
        font-family: "Yu Gothic UI", "Meiryo", sans-serif;
        font-weight: 600;
        letter-spacing: 0.025em;
    }
    div[data-testid="stSelectbox"] [data-baseweb="select"] > div {
        border-color: #ded8cb;
        border-radius: 4px;
        background: #fffefb;
    }
    div[data-testid="stProgress"] > div > div {
        background: linear-gradient(90deg, #9b8351, #c9b47f);
    }
    div[data-testid="stFileUploader"] section {
        border-color: #d9d1c1;
        border-radius: 4px;
        background: #fffefb;
    }
    div[data-testid="stMarkdownContainer"] p {
        color: #65635d;
    }
    hr {
        border-color: #e4ded2;
    }
    .hero h1.hero-title {
        padding: 0 !important;
        margin: 0 !important;
        font-size: clamp(1.8rem, 3vw, 2.5rem) !important;
    }
    .hero p.hero-caption {
        margin: 0.8rem 0 0 !important;
        color: #c6c5c0 !important;      /* 暗い背景でも読める明るさにする */
        font-size: 0.9rem !important;
    }
    .wx-grid {
        display: grid;
        grid-template-columns: repeat(3, 1fr);     /* PC は3列 */
        gap: 0.8rem;
        margin: 0.2rem 0 0.9rem;
    }
    .wx-card {
        padding: 1rem 1.1rem;
        border: 1px solid #ece6db;
        border-top: 2px solid #b69b63;
        border-radius: 4px;
        background: linear-gradient(145deg, #fffefb, #f8f6f0);
        font-family: "Yu Gothic UI", "Meiryo", sans-serif;
    }
    .wx-label {
        color: #77736a;
        font-size: 0.82rem;
        font-weight: 600;
        letter-spacing: 0.04em;
    }
    .wx-value {
        margin-top: 0.3rem;
        color: #252a31;
        font-size: 1.7rem;
        font-weight: 700;
        line-height: 1.3;
    }
    .wx-value small {
        margin-left: 0.25rem;
        color: #77736a;
        font-size: 0.8rem;
        font-weight: 600;
    }
    .wx-value.wx-none {
        color: #a9a59b;
        font-size: 1rem;
    }
    .pred-grid {
        display: grid;
        grid-template-columns: repeat(5, 1fr);     /* PC は5つの時間帯を横に並べる */
        gap: 0.7rem;
        margin: 0.6rem 0 0.4rem;
        font-family: "Yu Gothic UI", "Meiryo", sans-serif;
    }
    .pred-card {
        padding: 0.9rem 1rem 1rem;
        border: 1px solid #ece6db;
        border-top: 3px solid var(--pred-color);
        border-radius: 4px;
        background: linear-gradient(145deg, #fffefb, #f8f6f0);
    }
    .pred-low { --pred-color: #4f8a5b; }
    .pred-mid { --pred-color: #b7862c; }
    .pred-high { --pred-color: #b5483a; }
    .pred-slot {
        color: #484943;
        font-size: 0.84rem;
        font-weight: 700;
    }
    .pred-prob {
        margin: 0.25rem 0 0.45rem;
        color: #252a31;
        font-size: 1.9rem;
        font-weight: 700;
        line-height: 1.2;
    }
    .pred-prob small {
        margin-left: 0.1rem;
        color: #77736a;
        font-size: 0.9rem;
    }
    .pred-track {
        height: 6px;
        border-radius: 3px;
        background: #ebe6dc;
        overflow: hidden;
    }
    .pred-fill {
        height: 100%;
        border-radius: 3px;
        background: var(--pred-color);
    }
    .pred-badge {
        display: inline-block;
        margin-top: 0.6rem;
        padding: 0.12rem 0.55rem;
        border-radius: 999px;
        color: #fff;
        background: var(--pred-color);
        font-size: 0.74rem;
        font-weight: 700;
        letter-spacing: 0.04em;
    }
    .hero-title span {
        display: inline-block;        /* 「中央線快速」「遅延実績」の途中では改行しない */
    }
    .delay-row {
        display: grid;
        grid-template-columns: 6.2rem 1fr 3.4rem;
        align-items: center;
        gap: 0.7rem;
        padding: 0.55rem 0.2rem;
        border-top: 1px solid #efe9de;
        font-family: "Yu Gothic UI", "Meiryo", sans-serif;
    }
    .delay-name {
        color: #484943;
        font-size: 0.86rem;
        font-weight: 600;
    }
    .delay-track {
        height: 8px;
        border-radius: 4px;
        background: #ebe6dc;
        overflow: hidden;
    }
    .delay-fill {
        height: 100%;
        border-radius: 4px;
        background: linear-gradient(90deg, #9b8351, #c9b47f);
    }
    .delay-value {
        color: #252a31;
        font-size: 0.9rem;
        font-weight: 700;
        text-align: right;
    }
    /* ---------------- スマホ（幅700px以下） ---------------- */
    @media (max-width: 700px) {
        .main .block-container,
        [data-testid="stMainBlockContainer"] {
            padding: 6.6rem 0.85rem 3rem;
        }
        .hero {
            padding: 1.7rem 1.3rem 1.5rem;
            margin-bottom: 1.2rem;
        }
        .hero h1.hero-title {
            font-size: clamp(1.35rem, 6.4vw, 1.9rem) !important;
            letter-spacing: 0.05em;
            line-height: 1.3;
        }
        .pred-grid {
            grid-template-columns: 1fr;             /* スマホは縦に並べ、1行に「時間帯・確率・危険度」を収める */
            gap: 0.45rem;
        }
        .pred-card {
            display: grid;
            grid-template-columns: 5.2rem 3.6rem 1fr auto;
            align-items: center;
            gap: 0.6rem;
            padding: 0.6rem 0.75rem;
            border-top-width: 1px;
            border-left: 4px solid var(--pred-color);
        }
        .pred-prob {
            margin: 0;
            font-size: 1.3rem;
            text-align: right;
        }
        .pred-badge {
            margin-top: 0;
        }
        .wx-grid {
            grid-template-columns: repeat(2, 1fr);  /* スマホは2列 */
            gap: 0.55rem;
        }
        .wx-card {
            padding: 0.7rem 0.8rem;
        }
        .wx-label {
            font-size: 0.74rem;
        }
        .wx-value {
            font-size: 1.3rem;
        }
        .hero p.hero-caption {
            font-size: 0.8rem !important;
        }
        .home-nav {
            top: 2.9rem;
            gap: 0.1rem;
            padding: 0.45rem 0.35rem;
            justify-content: space-between;
        }
        .home-nav a {
            padding: 0.55rem 0.34rem;    /* 6つが1行に収まり、指でも押せる大きさ */
            font-size: 0.74rem;
            letter-spacing: 0;
        }
        .home-nav a::before {
            display: none;               /* 01, 02 … の番号は省いて、5つが1行に収まるようにする */
        }
        .section-heading {
            margin: 1.6rem 0 0.7rem;
            font-size: 1.02rem;
        }
        /* 数値カードは、スマホでも2列に並べる（縦に長くなりすぎないように） */
        .st-key-delay_result [data-testid="stHorizontalBlock"] {
            flex-direction: row !important;
            flex-wrap: wrap !important;
            gap: 0.6rem !important;
        }
        .st-key-delay_result [data-testid="stColumn"] {
            flex: 1 1 calc(50% - 0.6rem) !important;
            width: calc(50% - 0.6rem) !important;
            min-width: calc(50% - 0.6rem) !important;
        }
        div[data-testid="stMetric"] {
            min-height: 0;
            padding: 0.75rem 0.8rem;
        }
        div[data-testid="stMetricLabel"] {
            font-size: 0.74rem;
        }
        div[data-testid="stMetricValue"] {
            font-size: 1.35rem;
        }
        .delay-row {
            grid-template-columns: 5.4rem 1fr 3rem;
            gap: 0.5rem;
        }
        .hero::after {
            right: 1rem;
            width: 90px;
            height: 90px;
        }
        .hero::before {
            left: 1.45rem;
        }
        .home-nav {
            justify-content: flex-start;
        }
    }
    </style>
    """,
    unsafe_allow_html=True,
)

st.markdown(
    """
    <nav class="home-nav" aria-label="ページ内ナビゲーション">
        <a href="#prediction" target="_self">予測</a>
        <a href="#conditions" target="_self">条件設定</a>
        <a href="#delay-result" target="_self">遅延実績</a>
        <a href="#weather" target="_self">気象情報</a>
        <a href="#time-risks" target="_self">時間帯別</a>
        <a href="model_info" target="_self">モデル情報</a>
    </nav>
    """,
    unsafe_allow_html=True,
)

st.markdown(
    """
    <div class="hero">
        <div class="hero-kicker">Railway Insight · Tokyo</div>
        <h1 class="hero-title"><span>中央線快速</span> <span>遅延リスク予測</span></h1>
        <p class="hero-caption">天気予報からの遅延リスク予測と、過去の運行状況・気象データをひと目で確認。</p>
    </div>
    """,
    unsafe_allow_html=True,
)


def section_heading(title, anchor_id):
    st.markdown(
        f'<div id="{anchor_id}" class="section-heading">{title}</div>',
        unsafe_allow_html=True,
    )

# ---------------------------------------------------------------------------
# 遅延リスク予測（モデルは delay_model.py・太刀岡さん作。天気予報は weather_forecast.py）
# ---------------------------------------------------------------------------
PREDICTION_DAYS_AHEAD = 7          # 今日から何日先まで予測できるか（天気予報が取れる範囲）
RANK_CLASS = {"低": "pred-low", "中": "pred-mid", "高": "pred-high"}
DELAY_SLOT_COLUMNS = ["start_7", "7_10", "10_16", "16_21", "21_end"]


@st.cache_resource(show_spinner="予測モデルを読み込んでいます…")
def get_model():
    from delay_model import load_model

    return load_model()                # models/delay_model.pkl を読む。失敗すると ModelLoadError


@st.cache_data(ttl=3600, show_spinner="天気予報を取得しています…")
def _forecast_cached():
    from weather_forecast import fetch_tokyo_forecast

    return fetch_tokyo_forecast()      # 1時間は結果を使い回す（API へのアクセスを減らす）


def get_forecast():
    """(予報, エラーメッセージ) を返す。取得できなければ (None, 理由)。"""
    try:
        return _forecast_cached(), None
    except Exception as error:
        return None, str(error)


def previous_day_max_delay(history, day):
    """前日の最大遅延（分）。データベースにその日が無ければ None。"""
    if history is None:
        return None
    rows = history.loc[history["date"].eq(day - timedelta(days=1)), DELAY_SLOT_COLUMNS]
    if rows.empty:
        return None
    value = pd.to_numeric(rows.iloc[0], errors="coerce").max()
    return None if pd.isna(value) else float(value)


def show_prediction(history):
    """予測の画面。history は過去の実績の表（無ければ None でもよい）。"""
    section_heading("遅延リスク予測", "prediction")
    try:
        from delay_model import predict_all_slots

        model = get_model()
    except Exception as error:         # ファイルが無い・壊れている・scikit-learn のバージョン違いなど
        message = str(error)
        st.error(message if "モデルが読み込めません" in message else f"モデルが読み込めません（{type(error).__name__}）")
        st.caption("models/delay_model.pkl があるか、requirements.txt の scikit-learn のバージョンが学習時と同じかを確認してください。")
        return

    today = datetime.now(ZoneInfo("Asia/Tokyo")).date()
    with st.container(border=True, key="prediction_box"):
        day = st.date_input(
            "予測する日", value=today, min_value=today,
            max_value=today + timedelta(days=PREDICTION_DAYS_AHEAD), format="YYYY/MM/DD", key="prediction_day",
        )
        manual = st.toggle(
            "天気を手入力して試す", key="prediction_manual",
            help="天気予報の代わりに自分で数値を入れて、遅延リスクがどう変わるかを試せます。",
        )
        forecast, forecast_error = (None, None) if manual else get_forecast()
        if not manual and forecast is None:
            st.warning(f"天気予報を取得できませんでした。{forecast_error} 下の欄に天気を入力すると予測できます。")
            manual = True

        if manual:
            rain_column, previous_column, wind_column = st.columns(3)
            precip = rain_column.number_input("当日の降水量 (mm)", 0.0, 500.0, 0.0, 5.0, key="prediction_rain")
            prev_precip = previous_column.number_input("前日の降水量 (mm)", 0.0, 500.0, 0.0, 5.0, key="prediction_previous")
            wind = wind_column.number_input("平均風速 (m/s)", 0.0, 40.0, 2.5, 0.5, key="prediction_wind")
            source = "手入力"
        else:
            precip = forecast.get(day, {}).get("precip")
            wind = forecast.get(day, {}).get("wind")
            prev_precip = forecast.get(day - timedelta(days=1), {}).get("precip")
            source = "天気予報（東京）"
        prev_delay = previous_day_max_delay(history, day)

        result = predict_all_slots(model, day, precip=precip, prev_precip=prev_precip, wind=wind, prev_delay=prev_delay)

        cards_html = ""
        for _, row in result.iterrows():
            percent = float(row["遅延確率"]) * 100
            cards_html += (
                f'<div class="pred-card {RANK_CLASS.get(row["危険度"], "pred-low")}">'
                f'<div class="pred-slot">{row["時間帯"]}</div>'
                f'<div class="pred-prob">{percent:.0f}<small>%</small></div>'
                f'<div class="pred-track"><div class="pred-fill" style="width:{min(percent, 100):.0f}%"></div></div>'
                f'<span class="pred-badge">危険度 {row["危険度"]}</span></div>'
            )
        st.markdown(f'<div class="pred-grid">{cards_html}</div>', unsafe_allow_html=True)

        for note in dict.fromkeys(text for text in result["注意"] if text):      # 同じ注意は1回だけ表示
            st.warning(note)

        def shown(value, unit):
            return "不明" if value is None or pd.isna(value) else f"{value:g}{unit}"

        st.caption(
            f"{day:%m/%d} の「30分以上の遅延」が起きる確率です。予測に使った値（{source}）："
            f"降水量 {shown(precip, 'mm')}・平均風速 {shown(wind, 'm/s')}・前日の降水量 {shown(prev_precip, 'mm')}・"
            f"前日の最大遅延 {shown(prev_delay, '分')}。不明の項目は、学習データの中央値で補っています。"
        )
    low, high = model["rank_thresholds"]
    st.caption(
        f"危険度の目安：低＝{low:.0%}未満 / 中＝{low:.0%}以上 / 高＝{high:.0%}以上。"
        "予測は主に時間帯の傾向にもとづく目安で、事故・点検などによる遅延は予測できません。最新の運行情報もあわせて確認してください。"
    )
    try:
        st.page_link("pages/2_model_info.py", label="予測の根拠・モデル情報を見る →")
    except Exception:                  # ページが置かれていない場合は、リンクを出さない
        pass


st.markdown('<div id="data-source"></div>', unsafe_allow_html=True)
# ---------------------------------------------------------------------------
# データの読み込み：Supabase の merged_daily テーブルから自動で読む（アップロード不要）
#   接続情報は .streamlit/secrets.toml の [supabase] url / key
#   （Streamlit Community Cloud では、アプリの Settings → Secrets に同じ内容を貼る）
#   データの更新は auto_pick.py が行う：1日1回、JR東日本と気象庁から取得して Supabase に保存する。
#   手元の merged.csv を入れたいときは upload_merged.py（python upload_merged.py）。
# ---------------------------------------------------------------------------
TABLE = "merged_daily"
DB_DELAY_COLUMNS = {         # テーブルの列名 → この画面で使う列名（merged.csv と同じ）
    "d_start_7": "start_7",
    "d_7_10": "7_10",
    "d_10_16": "10_16",
    "d_16_21": "16_21",
    "d_21_end": "21_end",
    "max_delay": "max_delay",
    "total_delay": "total_delay",
}
DB_STATIONS = {"tokyo": "東京", "hachioji": "八王子", "setagaya": "世田谷", "ome": "青梅"}
DB_FIELDS = {
    "snow_cm": "最深積雪(cm)",
    "precip_mm": "降水量の合計(mm)",
    "temp_c": "平均気温(℃)",
    "wind_ms": "平均風速(m/s)",
    "vapor_hpa": "平均蒸気圧(hPa)",
    "cloud": "平均雲量(10分比)",
}
DB_WEATHER_COLUMNS = {
    f"{station_id}_{field_id}": f"{station}_{field}"
    for station_id, station in DB_STATIONS.items()
    for field_id, field in DB_FIELDS.items()
}


@st.cache_data(ttl=600, show_spinner="データベースから読み込んでいます…")
def load_from_supabase(url, key, version):
    """merged_daily を全部読み、merged.csv と同じ列名の表にして返す（10分間は結果を使い回す）。

    version は「これまでに更新した回数」。更新のたびに値が変わり、読み直しになる。
    """
    from supabase import create_client

    client = create_client(url, key)
    rows, start, page_size = [], 0, 1000          # Supabase は1回で最大1000行なので、分けて読む
    while True:
        page = client.table(TABLE).select("*").order("date").range(start, start + page_size - 1).execute().data or []
        rows.extend(page)
        if len(page) < page_size:
            break
        start += page_size
    frame = pd.DataFrame(rows).rename(columns={**DB_DELAY_COLUMNS, **DB_WEATHER_COLUMNS})
    weather_names = [name for name in DB_WEATHER_COLUMNS.values() if name in frame.columns]
    empty = [name for name in weather_names if frame[name].isna().all()]
    return frame.drop(columns=empty)              # 1件も値が無い項目（観測していない項目）は列ごと外す


try:
    supabase_url = st.secrets["supabase"]["url"]
    supabase_key = st.secrets["supabase"]["key"]
except Exception:
    st.error(
        "Supabase の接続情報がありません。.streamlit/secrets.toml に [supabase] の url と key を書いてください"
        "（Community Cloud では Settings → Secrets）。"
    )
    show_prediction(None)              # データベースが使えなくても、予測は表示する
    st.stop()

# ---- データの自動更新（JR東日本・気象庁 → Supabase） ---------------------------------
#   ボタンは無く、次の2つのタイミングで自動的に実行する。
#     1. アプリが起動したとき（Community Cloud では、スリープから起きたとき・再起動したときも含む）
#     2. 下の UPDATE_TIMES の時刻になったとき（アプリが起きている間だけ）
FETCH_JR_FROM_APP = False          # JR東日本は Community Cloud からの接続を拒否する（403）ので、アプリからは取得しない
                                   #   遅延データは、PC で「python auto_pick.py」を週1回ほど実行して更新する
UPDATE_TIMES = ["06:00"]           # 毎日この時刻（日本時間）に更新する。["06:00", "18:00"] のように複数も可
JST = ZoneInfo("Asia/Tokyo")


def _update_once(state, url, key, trigger):
    """1回ぶんの更新。失敗してもアプリは止めず、結果だけ記録する。"""
    try:
        import auto_pick
        from supabase import create_client

        report = auto_pick.run_update(create_client(url, key), include_delay=FETCH_JR_FROM_APP)
    except Exception as error:
        report = [{"name": "データ更新", "ok": False, "message": f"{type(error).__name__}: {str(error)[:150]}"}]
    state.update(
        when=datetime.now(JST), trigger=trigger, report=report,
        ok=all(step["ok"] for step in report), version=state["version"] + 1,
    )


def _update_loop(state, url, key):
    """決まった時刻まで待って更新する、を繰り返す（画面とは別に、裏で動き続ける）。"""
    import auto_pick

    while True:
        state["next"] = auto_pick.next_run_time(datetime.now(JST), UPDATE_TIMES)
        time.sleep(max(1.0, (state["next"] - datetime.now(JST)).total_seconds()))
        _update_once(state, url, key, "定時")


@st.cache_resource(show_spinner="起動時のデータ更新をしています…（10〜30秒ほど）")
def start_auto_update(url, key):
    """アプリの起動時に1回だけ呼ばれる：まず更新し、そのあと定時更新を裏で始める。"""
    state = {"when": None, "trigger": None, "ok": None, "report": [], "version": 0, "next": None}
    _update_once(state, url, key, "起動時")
    threading.Thread(target=_update_loop, args=(state, url, key), daemon=True).start()
    return state


state = start_auto_update(supabase_url, supabase_key)

with st.expander("データの更新状況（自動）", expanded=state["ok"] is False):
    lines = "\n\n".join(
        ("【成功】" if step["ok"] else "【失敗】") + f"{step['name']}：{step['message']}" for step in state["report"]
    )
    st.markdown(f"**最後の更新：{state['when']:%m/%d %H:%M}（{state['trigger']}）**\n\n{lines}")
    if state["next"]:
        st.caption(f"次の定時更新：{state['next']:%m/%d %H:%M}（アプリが起きている場合）。起動したときにも自動で更新します。")
    if not FETCH_JR_FROM_APP:
        st.caption("遅延データ（JR東日本）は、PC で「python auto_pick.py」を実行したときに更新されます。ここでは気象データだけを自動更新します。")

try:
    data = load_from_supabase(supabase_url, supabase_key, state["version"]).copy()
except Exception as error:
    st.error(f"データベースから読み込めませんでした（{type(error).__name__}: {str(error)[:150]}）。")
    show_prediction(None)
    st.stop()

if data.empty:
    st.error("データベースにまだデータがありません。上の「データの更新状況」の結果を確認してください。")
    show_prediction(None)
    st.stop()

time_columns = {
    "始発～7時": "start_7",
    "7時～10時": "7_10",
    "10時～16時": "10_16",
    "16時～21時": "16_21",
    "21時～終電": "21_end",
}

weather_fields = {
    "最深積雪(cm)": ("最深積雪", "cm"),
    "降水量の合計(mm)": ("降水量", "mm"),
    "平均気温(℃)": ("平均気温", "℃"),
    "平均風速(m/s)": ("平均風速", "m/s"),
    "平均蒸気圧(hPa)": ("平均蒸気圧", "hPa"),
    "平均雲量(10分比)": ("平均雲量", "10分比"),
}
weather_by_location = {}
for column in data.columns:
    if "_" not in column:
        continue
    location, field = column.split("_", maxsplit=1)
    if field in weather_fields:
        weather_by_location.setdefault(location, {})[field] = column

if not weather_by_location:
    st.error("地点別の気象データがありません。")
    st.stop()

required_columns = {"date", "line", *time_columns.values()}
missing_columns = sorted(required_columns.difference(data.columns))
if missing_columns:
    st.error(f"データに必要な列がありません: {', '.join(missing_columns)}")
    st.stop()

data["date"] = pd.to_datetime(data["date"], errors="coerce").dt.date
data = data.loc[
    data["line"].eq("中央線快速") & data["date"].notna()
].copy()
for column in [*time_columns.values(), *(
    column
    for fields in weather_by_location.values()
    for column in fields.values()
)]:
    data[column] = pd.to_numeric(data[column], errors="coerce")

if data.empty:
    st.error("有効な中央線快速の遅延データがありません。")
    st.stop()

show_prediction(data)

available_dates = sorted(data["date"].unique())
# 最初に選ぶ日付：気象データまでそろっている最新の日（気象庁の公開は1〜2日遅れるため）
weather_ready = data.loc[
    data[[column for fields in weather_by_location.values() for column in fields.values()]].notna().any(axis=1),
    "date",
]
default_date = weather_ready.max() if not weather_ready.empty else available_dates[-1]
section_heading("過去の実績を確認", "conditions")
with st.container(border=True):
    date_column, time_column, location_column = st.columns(3)

    with date_column:
        selected_date = st.selectbox(
            "日付",
            available_dates,
            index=available_dates.index(default_date),
            format_func=lambda value: value.strftime("%Y/%m/%d"),
        )

    with time_column:
        selected_time = st.selectbox("時間帯", list(time_columns))

    with location_column:
        locations = list(weather_by_location)
        default_location = locations.index("東京") if "東京" in locations else 0
        selected_location = st.selectbox(
            "気象データの地点",
            locations,
            index=default_location,
        )

selected_rows = data.loc[data["date"].eq(selected_date)]
selected_record = selected_rows.iloc[0]
delay_minutes = selected_record[time_columns[selected_time]]

section_heading("選択した日時の遅延実績", "delay-result")

if pd.isna(delay_minutes):
    st.error("選択した時間帯の遅延データがありません。")
    st.stop()

if delay_minutes < 20:
    level = "低"
elif delay_minutes < 50:
    level = "中"
else:
    level = "高"

with st.container(border=True, key="delay_result"):
    result_column, level_column = st.columns(2)

    with result_column:
        st.metric("遅延時間（実績）", f"{delay_minutes:g}分")

    with level_column:
        st.metric("危険度", level)

st.caption("危険度は遅延時間の実績に基づく目安です（20分未満: 低、20分以上50分未満: 中、50分以上: 高）。")

section_heading("気象データ", "weather")
display_locations = []
if "東京" in weather_by_location:
    display_locations.append("東京")
if selected_location != "東京":
    display_locations.append(selected_location)

with st.container(border=True, key="weather_box"):
    for location in display_locations:
        st.markdown(f"**{location}**")
        location_weather_fields = weather_by_location[location]
        if location != "東京":
            display_weather_fields = list(weather_fields)
        else:
            display_weather_fields = list(location_weather_fields)
        cards_html = ""
        for field in display_weather_fields:
            label, unit = weather_fields[field]
            column = location_weather_fields.get(field)
            reference_value = False
            if (
                (column is None or pd.isna(selected_record[column]))
                and "東京" in weather_by_location
            ):
                reference_column = weather_by_location["東京"].get(field)
                if reference_column is not None and not pd.isna(selected_record[reference_column]):
                    column = reference_column
                    reference_value = True
            value = selected_record[column] if column is not None else None
            card_label = f"{label}（東京参考）" if reference_value else label
            if value is not None and not pd.isna(value):
                card_value = f'<div class="wx-value">{value:g}<small>{unit}</small></div>'
            else:
                card_value = '<div class="wx-value wx-none">データなし</div>'
            cards_html += f'<div class="wx-card"><div class="wx-label">{card_label}</div>{card_value}</div>'
        st.markdown(f'<div class="wx-grid">{cards_html}</div>', unsafe_allow_html=True)
        if location != "東京":
            st.caption(
                f"{location}で観測値がない項目は、東京の観測値を参考値として表示しています。"
            )

section_heading("選択日の時間帯別遅延実績", "time-risks")
with st.container(border=True):
    st.caption("時間帯ごとの遅延分数の推移です。下のバーでも各時間帯の値を確認できます。")
    st.markdown(
        '<div class="chart-axis-label">遅延時間（分）</div>',
        unsafe_allow_html=True,
    )
    short_labels = ["始発～7", "7～10", "10～16", "16～21", "21～終電"]      # スマホでも重ならない短い表記
    time_risk_chart = pd.DataFrame(
        {
            "時間帯": short_labels,
            "遅延時間（分）": [
                selected_record[column]
                for column in time_columns.values()
            ],
        }
    )
    delay_line = alt.Chart(time_risk_chart).mark_line(
        color="#a68b54",
        strokeDash=[4, 4],
        strokeWidth=2,
        point=alt.OverlayMarkDef(
            filled=True,
            fill="#fffefb",
            stroke="#947844",
            strokeWidth=2,
            size=105,
        ),
    ).encode(
        x=alt.X(
            "時間帯:N",
            sort=short_labels,
            axis=alt.Axis(
                title="時間帯（時）",
                labelAngle=0,
                labelLimit=90,
                labelFontSize=11,
                labelOverlap=False,
                labelPadding=8,
                tickSize=0,
                domainColor="#d8d1c4",
            ),
        ),
        y=alt.Y(
            "遅延時間（分）:Q",
            axis=alt.Axis(
                title=None,
                gridColor="#ebe6dc",
                tickMinStep=1,
            ),
            scale=alt.Scale(zero=True),
        ),
        tooltip=[
            alt.Tooltip("時間帯:N", title="時間帯"),
            alt.Tooltip("遅延時間（分）:Q", title="遅延時間", format=".1f"),
        ],
    ).properties(
        height=300,
    )
    st.altair_chart(
        delay_line,
        width="stretch",
    )

    rows_html = ""
    for time_name, column in time_columns.items():
        value = selected_record[column]
        if pd.isna(value):
            width, text = 0, "—"
        else:
            width, text = min(max(float(value) / 60, 0), 1) * 100, f"{value:g}分"
        rows_html += (
            f'<div class="delay-row"><span class="delay-name">{time_name}</span>'
            f'<div class="delay-track"><div class="delay-fill" style="width:{width:.0f}%"></div></div>'
            f'<span class="delay-value">{text}</span></div>'
        )
    st.markdown(rows_html, unsafe_allow_html=True)

st.caption(
    f"データ期間: {min(available_dates):%Y/%m/%d}～{max(available_dates):%Y/%m/%d}。"
    "表示しているのはデータベース（Supabase）の過去実績で、将来の予測ではありません。起動時と毎日の決まった時刻に、自動で最新のデータを取得します。"
)
