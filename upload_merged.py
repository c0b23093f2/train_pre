"""merged.csv を Supabase の merged_daily テーブルに入れる（何度実行しても重複しない）。

使い方:
    python upload_merged.py                 # 同じフォルダーの merged.csv を入れる
    python upload_merged.py 別のファイル.csv

接続情報は .streamlit/secrets.toml の [supabase] url / key を使う。
先に merged_table.sql を Supabase の SQL Editor で実行しておくこと。
"""
import sys
from pathlib import Path

import pandas as pd
from supabase import create_client

TABLE = "merged_daily"
DELAY_COLUMNS = {            # CSV の列名 → テーブルの列名
    "start_7": "d_start_7",
    "7_10": "d_7_10",
    "10_16": "d_10_16",
    "16_21": "d_16_21",
    "21_end": "d_21_end",
    "max_delay": "max_delay",
    "total_delay": "total_delay",
}
STATIONS = {"東京": "tokyo", "八王子": "hachioji", "世田谷": "setagaya", "青梅": "ome"}
FIELDS = {
    "最深積雪(cm)": "snow_cm",
    "降水量の合計(mm)": "precip_mm",
    "平均気温(℃)": "temp_c",
    "平均風速(m/s)": "wind_ms",
    "平均蒸気圧(hPa)": "vapor_hpa",
    "平均雲量(10分比)": "cloud",
}
WEATHER_COLUMNS = {
    f"{station}_{field}": f"{station_id}_{field_id}"
    for station, station_id in STATIONS.items()
    for field, field_id in FIELDS.items()
}
INTEGER_COLUMNS = set(DELAY_COLUMNS.values())


def load_secrets() -> dict:
    path = Path(__file__).resolve().parent / ".streamlit" / "secrets.toml"
    if not path.is_file():
        raise SystemExit(f"{path} がありません。[supabase] の url と key を書いたファイルを作ってください。")
    try:
        import tomllib                      # Python 3.11 以上
    except ImportError:
        import toml as tomllib              # それより古い場合（Streamlit と一緒に入る）
        return tomllib.load(path)["supabase"]
    with open(path, "rb") as file:
        return tomllib.load(file)["supabase"]


def csv_to_records(csv_path: Path) -> list[dict]:
    """CSV を、テーブルに入れられる形（列名を変換・空欄は None）にする。"""
    frame = pd.read_csv(csv_path, encoding="utf-8-sig")
    missing = [name for name in ["date", "line", *list(DELAY_COLUMNS)[:5]] if name not in frame.columns]
    if missing:
        raise SystemExit(f"CSV に必要な列がありません: {missing}")
    unknown = [c for c in frame.columns if c not in {"date", "line", *DELAY_COLUMNS, *WEATHER_COLUMNS}]
    if unknown:
        print(f"注意：次の列はテーブルに無いので入れません: {unknown}")

    dates = pd.to_datetime(frame["date"], errors="coerce")
    frame = frame.loc[dates.notna()].copy()
    frame["date"] = dates.dropna().dt.strftime("%Y-%m-%d")
    frame = frame.drop_duplicates(["date", "line"], keep="last")

    records = []
    for _, row in frame.iterrows():
        record = {"date": row["date"], "line": str(row["line"])}
        for csv_name, db_name in {**DELAY_COLUMNS, **WEATHER_COLUMNS}.items():
            if csv_name not in frame.columns:
                continue
            value = pd.to_numeric(row[csv_name], errors="coerce")
            if pd.isna(value):
                record[db_name] = None
            else:
                record[db_name] = int(value) if db_name in INTEGER_COLUMNS else float(value)
        records.append(record)
    return records


def main() -> None:
    folder = Path(__file__).resolve().parent
    csv_path = Path(sys.argv[1]) if len(sys.argv) > 1 else folder / "merged.csv"
    if not csv_path.is_file():
        raise SystemExit(f"{csv_path} がありません。")
    records = csv_to_records(csv_path)
    if not records:
        raise SystemExit("CSV に有効な行がありません。何も変更していません。")

    secrets = load_secrets()
    client = create_client(secrets["url"], secrets["key"])
    for start in range(0, len(records), 500):
        client.table(TABLE).upsert(records[start:start + 500], on_conflict="date,line").execute()

    total = client.table(TABLE).select("date", count="exact").limit(1).execute().count
    print(f"{csv_path.name} の {len(records)} 行を入れました（{records[0]['date']}〜{records[-1]['date']}）。")
    if total is not None:
        print(f"いま {TABLE} には {total} 行あります。")


if __name__ == "__main__":
    main()
