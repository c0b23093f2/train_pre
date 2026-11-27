import threading
import time
from datetime import datetime
from zoneinfo import ZoneInfo

import altair as alt
import pandas as pd
import streamlit as st


st.set_page_config(
    page_title="中央線快速 遅延実績",
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
    header[data-testid="stHeader"] {
        background: transparent;
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
    @media (max-width: 700px) {
        .main .block-container {
            padding: 7.5rem 1rem 3rem;
        }
        .hero {
            padding: 2rem 1.45rem;
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
        <a href="#data-source" target="_self">データ</a>
        <a href="#conditions" target="_self">条件設定</a>
        <a href="#delay-result" target="_self">遅延実績</a>
        <a href="#weather" target="_self">気象情報</a>
        <a href="#time-risks" target="_self">時間帯別</a>
    </nav>
    """,
    unsafe_allow_html=True,
)

st.markdown(
    """
    <div class="hero">
        <div class="hero-kicker">Railway Insight · Tokyo</div>
        <h1 class="hero-title">中央線快速 遅延実績</h1>
        <p class="hero-caption">過去の運行状況と、各地の気象データをひと目で確認。</p>
    </div>
    """,
    unsafe_allow_html=True,
)


def section_heading(title, anchor_id):
    st.markdown(
        f'<div id="{anchor_id}" class="section-heading">{title}</div>',
        unsafe_allow_html=True,
    )

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
    st.stop()

# ---- データの自動更新（JR東日本・気象庁 → Supabase） ---------------------------------
#   ボタンは無く、次の2つのタイミングで自動的に実行する。
#     1. アプリが起動したとき（Community Cloud では、スリープから起きたとき・再起動したときも含む）
#     2. 下の UPDATE_TIMES の時刻になったとき（アプリが起きている間だけ）
UPDATE_TIMES = ["06:00"]           # 毎日この時刻（日本時間）に更新する。["06:00", "18:00"] のように複数も可
JST = ZoneInfo("Asia/Tokyo")


def _update_once(state, url, key, trigger):
    """1回ぶんの更新。失敗してもアプリは止めず、結果だけ記録する。"""
    try:
        import auto_pick
        from supabase import create_client

        report = auto_pick.run_update(create_client(url, key))
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

try:
    data = load_from_supabase(supabase_url, supabase_key, state["version"]).copy()
except Exception as error:
    st.error(f"データベースから読み込めませんでした（{type(error).__name__}: {str(error)[:150]}）。")
    st.stop()

if data.empty:
    st.error("データベースにまだデータがありません。上の「データの更新状況」の結果を確認してください。")
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

with st.container(border=True):
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

with st.container(border=True):
    for location in display_locations:
        st.markdown(f"**{location}**")
        location_weather_fields = weather_by_location[location]
        if location != "東京":
            display_weather_fields = list(weather_fields)
        else:
            display_weather_fields = list(location_weather_fields)
        weather_columns = st.columns(min(len(display_weather_fields), 3))
        for index, field in enumerate(display_weather_fields):
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
            with weather_columns[index % len(weather_columns)]:
                metric_label = f"{label}（東京参考）" if reference_value else label
                metric_value = (
                    f"{value:g} {unit}"
                    if value is not None and not pd.isna(value)
                    else "データなし"
                )
                st.metric(metric_label, metric_value)
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
    time_risk_chart = pd.DataFrame(
        {
            "時間帯": list(time_columns),
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
            sort=list(time_columns),
            axis=alt.Axis(
                title="時間帯",
                labelAngle=0,
                labelLimit=140,
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

    for time_name, column in time_columns.items():
        value = selected_record[column]
        label_column, bar_column = st.columns([2, 5])
        with label_column:
            st.write(time_name)
        with bar_column:
            if pd.isna(value):
                st.caption("データなし")
            else:
                st.progress(min(max(float(value) / 60, 0), 1))
                st.caption(f"{value:g}分")

st.caption(
    f"データ期間: {min(available_dates):%Y/%m/%d}～{max(available_dates):%Y/%m/%d}。"
    "表示しているのはデータベース（Supabase）の過去実績で、将来の予測ではありません。起動時と毎日の決まった時刻に、自動で最新のデータを取得します。"
)
