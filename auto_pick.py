"""JR東日本の遅延履歴と気象庁の気象データを取得し、Supabase の merged_daily テーブルに保存する。

元の update_all.py（CSV を作り直す版・名前を auto_pick.py に変更）を、Streamlit Community Cloud で動くように直したもの。
Community Cloud ではファイルに書いても再起動で消えるので、CSV の代わりにデータベースへ保存する。

使い方
  - PC から    ：python auto_pick.py   （遅延＋気象を更新。週に1回ほど実行する）
                 .streamlit/secrets.toml の接続情報を使う
  - アプリから：app.py が起動時と定時に呼ぶ（気象だけを更新）
                 Community Cloud からは JR東日本に接続できない（403）ため、遅延は PC から更新する

必要なライブラリ：supabase, certifi（pandas・lxml・requests は使わない）

方針
  - 遅延：ページにある直近およそ45日を保存する。同じ日付は上書き、古い日付は消さない（＝たまっていく）。
  - 気象：遅延データがあるのに気象がまだ入っていない日だけ、その月のページを取りに行く。
  - 途中で失敗しても、保存済みのデータは消さない。JR と気象庁の片方が失敗しても、もう片方は続ける。
"""
from __future__ import annotations

import re
import ssl
import time
import urllib.request
from datetime import date, datetime, timedelta
from html.parser import HTMLParser
from zoneinfo import ZoneInfo

import certifi

TABLE = "merged_daily"
LINE = "中央線快速"
JR_URL = "https://traininfo.jreast.co.jp/train_info/line.aspx?gid=1&lineid=chuoline_rapidservice"
JMA_BASE = "https://www.data.jma.go.jp/stats/etrn/view/"
DELAY_COLUMNS = ["d_start_7", "d_7_10", "d_10_16", "d_16_21", "d_21_end"]

# 気象庁の地点：（テーブルの列名の頭, ページの種類, 地点番号）。都府県番号は 44（東京）
#   s1 = 気象台など（1行21列）、a1 = アメダス（1行18列）
STATIONS = {
    "東京": ("tokyo", "s1", "47662"),
    "八王子": ("hachioji", "a1", "0366"),
    "世田谷": ("setagaya", "a1", "0368"),
    "青梅": ("ome", "a1", "1001"),
}
# 表の何列目（0始まり）にどの値があるか。テーブルの列名の末尾 → 列番号
LAYOUTS = {
    "s1": {"cells": 21, "precip_mm": 3, "temp_c": 6, "wind_ms": 11, "snow_cm": 18},
    "a1": {"cells": 18, "precip_mm": 1, "temp_c": 4, "wind_ms": 9},
}
ZERO_WHEN_NONE = {"precip_mm", "snow_cm"}      # 「--」（現象なし）を 0 として扱う項目
WEATHER_DELAY_DAYS = 2                         # 気象庁の公開の遅れを見て、2日前までを対象にする
JMA_WAIT_SECONDS = 1.0                         # 気象庁へのアクセスの間隔（秒）
MAX_MONTHS_PER_RUN = 6                         # 1回の更新で取得する月数の上限（1か月 = 4ページ）
NUMBER = re.compile(r"-?\d+(?:\.\d+)?")


# ----------------------------------------------------------------------------
# HTML の表を読む（Python 標準の機能だけ）
# ----------------------------------------------------------------------------
class TableReader(HTMLParser):
    """HTML 内の <table> を「行のリスト（各行はセル文字列のリスト）」として集める。"""

    def __init__(self):
        super().__init__()
        self.tables = []
        self.depth = 0
        self.row = None
        self.cell = None

    def handle_starttag(self, tag, attrs):
        if tag == "table":
            self.depth += 1
            if self.depth == 1:
                self.tables.append([])
        elif tag == "tr" and self.depth:
            self.row = []
        elif tag in ("td", "th") and self.row is not None:
            self.cell = []

    def handle_endtag(self, tag):
        if tag in ("td", "th") and self.cell is not None and self.row is not None:
            self.row.append(" ".join("".join(self.cell).split()))
            self.cell = None
        elif tag == "tr" and self.row is not None:
            if self.tables:
                self.tables[-1].append(self.row)
            self.row = None
        elif tag == "table" and self.depth:
            self.depth -= 1

    def handle_data(self, data):
        if self.cell is not None:
            self.cell.append(data)


def download_text(url: str) -> str:
    request = urllib.request.Request(
        url, headers={"User-Agent": "university-class-project (data analysis practice)"}
    )
    context = ssl.create_default_context(cafile=certifi.where())
    with urllib.request.urlopen(request, timeout=30, context=context) as response:
        return response.read().decode("utf-8", errors="replace")


# ----------------------------------------------------------------------------
# JR東日本：遅延証明書の履歴
# ----------------------------------------------------------------------------
def parse_jr_html(html: str, today: date) -> list[dict]:
    """ページの HTML → テーブルに入れる行のリスト。'-' → 0、'10分' → 10、'61分以上' → 61。"""
    reader = TableReader()
    reader.feed(html)
    table = next(
        (t for t in reader.tables if any(row and re.match(r"\s*\d+月\d+日", row[0]) for row in t)), None
    )
    if table is None:
        raise RuntimeError("JR東日本の遅延履歴テーブルが見つかりませんでした。")

    records, year, previous_month = [], today.year, None
    for row in table:
        match = re.match(r"\s*(\d+)月(\d+)日", row[0]) if row else None
        if not match:
            continue
        month, day = map(int, match.groups())
        if previous_month is None and date(year, month, day) > today:
            year -= 1                       # 1月に「12月31日」の行を見た場合など
        elif previous_month is not None and month > previous_month:
            year -= 1                       # 月の数字が増えた → 前の年に入った
        previous_month = month
        observed = date(year, month, day)
        if observed >= today or len(row) < 6:
            continue                        # 当日分は値がまだ変わるので入れない
        values = []
        for cell in row[1:6]:
            number = re.match(r"\s*(\d+)", cell.replace("別ウィンドウで開きます", ""))
            values.append(int(number.group(1)) if number else 0)
        record = {"date": observed.isoformat(), "line": LINE, **dict(zip(DELAY_COLUMNS, values))}
        record["max_delay"] = max(values)
        record["total_delay"] = sum(values)
        records.append(record)

    if len(records) < 5:
        raise RuntimeError(f"JR東日本の履歴が {len(records)} 日分しか読めませんでした。ページの構造が変わった可能性があります。")
    unique = {record["date"]: record for record in records}
    return [unique[key] for key in sorted(unique)]


# ----------------------------------------------------------------------------
# 気象庁：過去の気象データ検索（1地点・1か月ぶんが1ページ）
# ----------------------------------------------------------------------------
def _number(text: str, field: str):
    """セルの文字 → 数値。'12.5 )' → 12.5、'--' → 0（降水・積雪のみ）、'///'・'×'・空欄 → None。"""
    text = text.strip()
    if text == "--":
        return 0.0 if field in ZERO_WHEN_NONE else None
    match = NUMBER.match(text)
    return float(match.group()) if match else None


def parse_jma_html(html: str, kind: str) -> dict[int, dict]:
    """1か月ぶんのページ → {日: {"precip_mm": 値, ...}}。列数が想定と違えばエラーにする。"""
    layout = LAYOUTS[kind]
    reader = TableReader()
    reader.feed(html)
    day_rows = [
        row for table in reader.tables for row in table
        if row and row[0].strip().isdigit() and 1 <= int(row[0].strip()) <= 31 and len(row) >= 10
    ]
    if not day_rows:
        raise RuntimeError("気象庁のページに日ごとの表が見つかりませんでした。")
    wrong = [row for row in day_rows if len(row) != layout["cells"]]
    if wrong:
        raise RuntimeError(
            f"気象庁の表の列数が想定と違います（{len(wrong[0])} 列 / 想定 {layout['cells']} 列）。ページの構造が変わった可能性があります。"
        )
    fields = [name for name in layout if name != "cells"]
    return {int(row[0].strip()): {field: _number(row[layout[field]], field) for field in fields} for row in day_rows}


def fetch_jma_month(station: str, year: int, month: int) -> dict[int, dict]:
    _, kind, block_no = STATIONS[station]
    url = f"{JMA_BASE}daily_{kind}.php?prec_no=44&block_no={block_no}&year={year}&month={month}&day=&view="
    return parse_jma_html(download_text(url), kind)


def weather_columns() -> list[str]:
    """気象庁から取得してテーブルに入れる列（蒸気圧・雲量は日ごとのページに無いので含まない）。"""
    return [
        f"{prefix}_{field}"
        for prefix, kind, _ in STATIONS.values()
        for field in LAYOUTS[kind] if field != "cells"
    ]


# ----------------------------------------------------------------------------
# Supabase との読み書き
# ----------------------------------------------------------------------------
def _upsert(client, records: list[dict]) -> None:
    """同じ (date, line) があれば、渡した列だけを上書き。無ければ追加。"""
    for start in range(0, len(records), 500):
        client.table(TABLE).upsert(records[start:start + 500], on_conflict="date,line").execute()


def _dates_without_weather(client, last_day: date) -> list[date]:
    """遅延データはあるのに、気象（東京の降水量）がまだ入っていない日。"""
    rows, start = [], 0
    while True:
        page = (client.table(TABLE).select("date,line,tokyo_precip_mm").eq("line", LINE)
                .order("date").range(start, start + 999).execute().data or [])
        rows.extend(page)
        if len(page) < 1000:
            break
        start += 1000
    dates = [
        date.fromisoformat(str(row["date"])[:10]) for row in rows
        if row.get("line") == LINE and row.get("tokyo_precip_mm") is None
    ]
    return sorted(day for day in dates if day <= last_day)


def _short(problem: Exception) -> str:
    text = f"{type(problem).__name__}: {problem}"
    return text if len(text) <= 160 else text[:160] + "…"


def update_delay(client, today: date) -> str:
    records = parse_jr_html(download_text(JR_URL), today)       # 失敗したら例外 → 何も書かない
    _upsert(client, records)
    return f"{len(records)}日分を保存しました（{records[0]['date']}〜{records[-1]['date']}）。"


def update_weather(client, today: date, progress) -> tuple[bool, str]:
    needed = _dates_without_weather(client, today - timedelta(days=WEATHER_DELAY_DAYS))
    if not needed:
        return True, "新しく取得する日はありません。"
    months = sorted({(day.year, day.month) for day in needed}, reverse=True)       # 新しい月から
    columns = weather_columns()
    records, error, done, first_request = [], None, 0, True
    for year, month in months[:MAX_MONTHS_PER_RUN]:
        by_station = {}
        try:
            for station in STATIONS:
                if not first_request:
                    time.sleep(JMA_WAIT_SECONDS)                 # 気象庁のサーバーに負荷をかけない
                first_request = False
                progress(f"気象庁：{station} {year}年{month}月")
                by_station[station] = fetch_jma_month(station, year, month)
        except Exception as problem:
            error = f"{year}年{month}月の取得に失敗しました（{_short(problem)}）"
            break                                               # 続けて失敗しそうなので、ここで止める
        done += 1
        for day in needed:
            if (day.year, day.month) != (year, month):
                continue
            record = {"date": day.isoformat(), "line": LINE, **{column: None for column in columns}}
            for station, (prefix, _, _) in STATIONS.items():
                for field, value in by_station[station].get(day.day, {}).items():
                    record[f"{prefix}_{field}"] = value
            if any(record[column] is not None for column in columns):
                records.append(record)                          # まだ公開されていない日は入れない
    if records:
        _upsert(client, records)

    message = f"{len(records)}日分を保存しました（{done}か月分のページ）。"
    if error:
        return False, f"{message} {error}。保存済みのデータはそのままです。"
    if len(months) > MAX_MONTHS_PER_RUN:
        message += f" 残り {len(months) - MAX_MONTHS_PER_RUN} か月分は次回に取得します。"
    return True, message


def run_update(client, today: date | None = None, progress=None, include_delay: bool = True) -> list[dict]:
    """遅延 → 気象の順に更新する。結果を [{"name", "ok", "message"}, ...] で返す。

    include_delay=False にすると、JR東日本には接続せず、気象だけを更新する
    （Streamlit Community Cloud からは JR東日本に接続できないため、アプリからはこの形で呼ぶ）。
    """
    progress = progress or (lambda text: None)
    today = today or datetime.now(ZoneInfo("Asia/Tokyo")).date()
    report = []

    if include_delay:
        progress("JR東日本：遅延証明書の履歴")
        try:
            report.append({"name": "遅延データ（JR東日本）", "ok": True, "message": update_delay(client, today)})
        except Exception as problem:
            report.append({
                "name": "遅延データ（JR東日本）", "ok": False,
                "message": f"更新に失敗しました（{_short(problem)}）。保存済みのデータはそのままです。",
            })
    try:
        ok, message = update_weather(client, today, progress)
    except Exception as problem:
        ok, message = False, f"更新に失敗しました（{_short(problem)}）。保存済みのデータはそのままです。"
    report.append({"name": "気象データ（気象庁）", "ok": ok, "message": message})
    return report


def next_run_time(now: datetime, times: list[str]) -> datetime:
    """決まった時刻（例 ["06:00", "18:00"]）のうち、now のあとで最初に来る日時を返す。"""
    candidates = []
    for text in times:
        hour, minute = map(int, text.split(":"))
        moment = now.replace(hour=hour, minute=minute, second=0, microsecond=0)
        candidates.append(moment if moment > now else moment + timedelta(days=1))
    return min(candidates)


def main() -> None:
    from pathlib import Path

    from supabase import create_client

    path = Path(__file__).resolve().parent / ".streamlit" / "secrets.toml"
    if not path.is_file():
        raise SystemExit(f"{path} がありません。[supabase] の url と key を書いたファイルを作ってください。")
    try:
        import tomllib                      # Python 3.11 以上
        with open(path, "rb") as file:
            secrets = tomllib.load(file)["supabase"]
    except ImportError:
        import toml                         # それより古い場合（Streamlit と一緒に入る）
        secrets = toml.load(path)["supabase"]

    report = run_update(create_client(secrets["url"], secrets["key"]), progress=print)
    for step in report:
        print(("【成功】" if step["ok"] else "【失敗】") + f"{step['name']}：{step['message']}")
    if not all(step["ok"] for step in report):
        raise SystemExit(1)


if __name__ == "__main__":
    main()
