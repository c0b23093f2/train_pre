"""Supabase にたまったデータで予測モデルを学習し直す（PC で実行する）。

使い方:
    python train_from_db.py

やること:
    1. Supabase の merged_daily を全部読む（.streamlit/secrets.toml の接続情報を使う）
    2. delay_model.py（太刀岡さん作）が読める形の CSV に直す
    3. delay_model.train_and_save() で学習し、models/ と reports/ を作り直す

学習のあと、models/delay_model.pkl と models/model_metrics.json を GitHub に push すると、
公開アプリの予測にも反映される。
"""
import tempfile
from pathlib import Path

import pandas as pd
from supabase import create_client

import delay_model
from upload_merged import DELAY_COLUMNS, TABLE, WEATHER_COLUMNS, load_secrets


def load_table() -> pd.DataFrame:
    secrets = load_secrets()
    client = create_client(secrets["url"], secrets["key"])
    rows, start = [], 0
    while True:                                   # Supabase は1回で最大1000行なので、分けて読む
        page = client.table(TABLE).select("*").order("date").range(start, start + 999).execute().data or []
        rows.extend(page)
        if len(page) < 1000:
            break
        start += 1000
    if not rows:
        raise SystemExit("Supabase にデータがありません。先に python auto_pick.py を実行してください。")
    # テーブルの列名 → merged.csv の列名（start_7、東京_降水量の合計(mm) など）
    to_csv_name = {db: name for name, db in {**DELAY_COLUMNS, **WEATHER_COLUMNS}.items()}
    return pd.DataFrame(rows).rename(columns=to_csv_name).drop(columns=["updated_at"], errors="ignore")


def main() -> None:
    frame = load_table()
    print(f"Supabase から {len(frame)} 日分を読み込みました（{frame['date'].min()}〜{frame['date'].max()}）。")
    print("学習中（並べ替え検定があるため1〜2分かかります）…")
    with tempfile.TemporaryDirectory() as folder:
        csv_path = Path(folder) / "merged_supabase.csv"
        frame.to_csv(csv_path, index=False, encoding="utf-8-sig")
        metrics = delay_model.train_and_save([csv_path])

    data = metrics["data"]
    print(f"データ: {data['days']}日 × 5時間帯 = {data['rows']}件（{data['start']}〜{data['end']}）"
          f" / 30分以上の遅延: {data['positive']}件（{data['positive_rate']:.1%}）")
    for warning in data["warnings"]:
        print("  注意:", warning)
    for key, scores in metrics["evaluation"].items():
        print(f"  {delay_model.MODEL_LABELS[key]}: ROC-AUC {scores['roc_auc']:.3f} / ブライア {scores['brier']:.3f}")
    print(f"予測に使うモデル: {delay_model.MODEL_LABELS[metrics['best_model']]}")
    print(f"保存先: {delay_model.MODEL_PATH} / {delay_model.METRICS_PATH}")


if __name__ == "__main__":
    main()
