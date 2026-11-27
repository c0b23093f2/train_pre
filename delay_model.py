"""
予測モデル構築・保存（担当：太刀岡）

チームの既存プログラムをもとに、「時間帯ごと」の予測に対応させたもの。

  使ったもの（元のプログラム）
  - ロジスティック回帰 …… train_delay_model.py の build_model（欠損補完→標準化→ロジスティック回帰）
  - ランダムフォレスト …… main.ipynb の設定（木1000本、葉に3件以上、class_weight="balanced"）
  - 特徴量           …… main.ipynb でしぼり込んだ5つ
                          （降水量、平均風速、平日、前日降水量、前日最大遅延分）＋時間帯
  - 祝日             …… tree_v2.ipynb と同じ（9/21・9/22・9/23・10/12 を休日扱い）
  - 検証             …… train_delay_model.py の「9日分を評価用に取り分ける」を、
                          tree_v2.ipynb と同じく日付ごとにまとめて分ける方式にしたもの
  - 並べ替え検定     …… tree_v2.ipynb の perm_test（日単位で答えを入れ替える）
  - 決定木のルール   …… tree_v2.ipynb の分析C（深さ3、葉に8件以上）と leaf_rules

  既存プログラムから変えたところ
  - 1日単位（その日のどこかで30分以上）→ 日×時間帯ごと（その時間帯で30分以上）
  - merged.csv の新しい列名（start_7 など、地点名つきの気象列）に対応

使い方（学習）:
    python delay_model.py                  # data フォルダの CSV をすべて使う
    python delay_model.py --data a.csv b.csv

使い方（アプリから予測）:
    from delay_model import load_model, predict_all_slots
    bundle = load_model()
    result = predict_all_slots(bundle, date, 降水量, 前日降水量, 平均風速)
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import re
from pathlib import Path

import joblib
import numpy as np
import pandas as pd
import sklearn
from sklearn.ensemble import RandomForestClassifier
from sklearn.impute import SimpleImputer
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import (
    accuracy_score,
    balanced_accuracy_score,
    brier_score_loss,
    confusion_matrix,
    f1_score,
    log_loss,
    precision_score,
    recall_score,
    roc_auc_score,
)
from sklearn.model_selection import GroupShuffleSplit
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import StandardScaler
from sklearn.tree import DecisionTreeClassifier

# ---------------------------------------------------------------------------
# 設定
# ---------------------------------------------------------------------------
BASE_DIR = Path(__file__).resolve().parent
# 学習データ：data フォルダの CSV をすべて読み込んで日付でつなげる（ファイル名は何でもよい）
# data フォルダがなければ、同じフォルダの merged.csv などを1つ使う
DATA_DIR = BASE_DIR / "data"
DATA_CANDIDATES = [BASE_DIR / "merged (1).csv", BASE_DIR / "merged.csv"]


def find_data_files() -> list[Path]:
    files = sorted(DATA_DIR.glob("*.csv")) if DATA_DIR.is_dir() else []
    if files:
        return files
    return [p for p in DATA_CANDIDATES if p.exists()][:1]
MODEL_PATH = BASE_DIR / "models" / "delay_model.pkl"
METRICS_PATH = BASE_DIR / "models" / "model_metrics.json"
PREDICTIONS_PATH = BASE_DIR / "reports" / "delay_predictions.csv"

TARGET_THRESHOLD_MINUTES = 30      # 30分以上を「遅延あり」とする（既存プログラムと同じ）
STATION = "東京"                   # 気象データの地点（main.ipynb の「降水量(mm)」「平均風速(m/s)」と同じ地点）
TEST_SIZE = 9                      # 評価用に取り分ける日数（train_delay_model.py と同じ）
CV_REPEATS = 20                    # 取り分けを変えて評価する回数（元は5回。データが少なく結果がぶれるので増やした）
N_PERMUTATIONS = 200               # 並べ替え検定の回数（tree_v2.ipynb と同じ）
PREDICT_THRESHOLD = 0.5            # この確率以上を「遅延あり」の予測とする（既存プログラムと同じ）
RANK_THRESHOLDS = (0.15, 0.30)     # 確率 <15%: 低, <30%: 中, それ以上: 高（遅延の発生率 約20% を基準にした目安）

# 時間帯：表示名と、merged.csv での列名（新しい形式・古い形式の両方に対応）
TIME_SLOTS = ["始発〜7時", "7〜10時", "10〜16時", "16〜21時", "21時〜終電"]
SLOT_COLUMN_CANDIDATES = [
    ["start_7", "始発～7時"],
    ["7_10", "7時～10時"],
    ["10_16", "10時～16時"],
    ["16_21", "16時～21時"],
    ["21_end", "21時～終電"],
]

# 特徴量（main.ipynb の5つ＋時間帯）
DAY_FEATURES = ["降水量", "平均風速", "平日", "前日降水量", "前日最大遅延分"]
SLOT_FEATURES = [f"時間帯_{s}" for s in TIME_SLOTS]
FEATURES = DAY_FEATURES + SLOT_FEATURES
WEATHER_FEATURES = ["降水量", "平均風速", "前日降水量"]
NUMERIC_FEATURES = ["降水量", "平均風速", "前日降水量", "前日最大遅延分"]
UNITS = {"降水量": "mm", "前日降水量": "mm", "平均風速": "m/s", "前日最大遅延分": "分"}

# 祝日（tree_v2.ipynb と同じ期間内の祝日に、2026年のほかの祝日を足したもの）
JP_HOLIDAYS_2026 = {
    "2026-01-01", "2026-01-12", "2026-02-11", "2026-02-23", "2026-03-20", "2026-04-29",
    "2026-05-03", "2026-05-04", "2026-05-05", "2026-05-06", "2026-07-20", "2026-08-11",
    "2026-09-21", "2026-09-22", "2026-09-23", "2026-10-12", "2026-11-03", "2026-11-23",
}

MODEL_LABELS = {"logistic": "ロジスティック回帰", "random_forest": "ランダムフォレスト"}


class ModelLoadError(Exception):
    """学習済みモデルが見つからない・読み込めないときのエラー"""


# ---------------------------------------------------------------------------
# モデル（既存プログラムの設定をそのまま使う）
# ---------------------------------------------------------------------------
def build_logistic():
    """train_delay_model.py の build_model と同じ"""
    return make_pipeline(
        SimpleImputer(strategy="median"),
        StandardScaler(),
        LogisticRegression(max_iter=2000, random_state=42),
    )


def build_random_forest():
    """main.ipynb のランダムフォレストと同じ設定"""
    return make_pipeline(
        SimpleImputer(strategy="median"),
        RandomForestClassifier(
            n_estimators=1000,
            max_depth=None,
            min_samples_leaf=3,
            max_features=None,
            class_weight="balanced",
            random_state=0,
        ),
    )


MODEL_BUILDERS = {"logistic": build_logistic, "random_forest": build_random_forest}


def build_tree():
    """tree_v2.ipynb の分析C と同じ決定木（説明用）"""
    return DecisionTreeClassifier(max_depth=3, min_samples_leaf=8, class_weight="balanced", random_state=0)


# ---------------------------------------------------------------------------
# データの準備
# ---------------------------------------------------------------------------
def parse_delay_minutes(value) -> float:
    """「-」→0、「61分以上」→61、「10分」→10、空欄→0（train_delay_model.py / tree_v2.ipynb と同じ考え方）"""
    if pd.isna(value):
        return 0.0
    text = str(value).strip()
    if text in {"", "-", "ー", "nan"}:
        return 0.0
    match = re.search(r"\d+", text)
    return float(match.group()) if match else 0.0


def is_weekday(d: dt.date) -> int:
    """平日なら1、土日祝なら0"""
    if d.weekday() >= 5:
        return 0
    try:
        import jpholiday  # 入っていれば2027年以降の祝日にも対応できる

        return 0 if jpholiday.is_holiday(d) else 1
    except ImportError:
        return 0 if d.isoformat() in JP_HOLIDAYS_2026 else 1


def normalize_time_slot(value) -> int | None:
    """時間帯の表記（「7〜10時」「7時～10時」「7_10」、0〜4の番号）を 0〜4 にそろえる"""
    if isinstance(value, (int, np.integer)):
        return int(value) if 0 <= int(value) <= 4 else None
    s = str(value).strip()
    for i, names in enumerate(SLOT_COLUMN_CANDIDATES):
        if s in names or s == TIME_SLOTS[i]:
            return i
    if "始発" in s or "初電" in s or s.lower().startswith("start"):
        return 0
    if "終電" in s or s.lower().endswith("end"):
        return 4
    m = re.search(r"\d+", s)
    if not m:
        return None
    start = int(m.group())
    return 0 if start < 7 else 1 if start < 10 else 2 if start < 16 else 3 if start < 21 else 4


def _weather_column(frame: pd.DataFrame, item: str, warnings: list) -> pd.Series:
    """「東京_降水量の合計(mm)」のような列を探す。なければ他の地点の平均で代用する"""
    preferred = [c for c in frame.columns if c.startswith(f"{STATION}_") and item in c]
    if preferred:
        return pd.to_numeric(frame[preferred[0]], errors="coerce")
    plain = [c for c in frame.columns if c.startswith(item)]  # 古い形式（地点名なし）
    if plain:
        return pd.to_numeric(frame[plain[0]], errors="coerce")
    others = [c for c in frame.columns if item in c]
    if others:
        warnings.append(f"{STATION}の「{item}」がないため、ほかの地点の平均を使いました")
        return frame[others].apply(pd.to_numeric, errors="coerce").mean(axis=1)
    warnings.append(f"「{item}」の列がないため、欠損として扱いました")
    return pd.Series(np.nan, index=frame.index)


def prepare_daily(frame: pd.DataFrame) -> tuple[pd.DataFrame, list]:
    """1日＝1行の表（日付・各時間帯の遅延分・特徴量）を作る"""
    warnings: list[str] = []
    frame = frame.copy()
    frame.columns = [str(c).strip() for c in frame.columns]

    # 「date」を優先（merge.py の出力には「11月26日」形式の「日付」列もあるため）
    date_col = next((c for c in ("date", "年月日", "日付") if c in frame.columns), None)
    if date_col is None:
        raise ValueError("CSVに日付の列（date）がありません。")
    if "line" in frame.columns and frame["line"].eq("中央線快速").any():
        frame = frame[frame["line"].eq("中央線快速")]

    slot_cols = []
    for names in SLOT_COLUMN_CANDIDATES:
        col = next((n for n in names if n in frame.columns), None)
        if col is None:
            raise ValueError(f"CSVに時間帯の列がありません: {names[0]}（または {names[1]}）")
        slot_cols.append(col)

    daily = pd.DataFrame({"date": pd.to_datetime(frame[date_col], errors="coerce")})
    if daily["date"].isna().any():
        warnings.append(f"日付として読めない行を {int(daily['date'].isna().sum())} 行除外しました")
    for i, col in enumerate(slot_cols):
        daily[f"遅延_{i}"] = frame[col].map(parse_delay_minutes).values
    daily["降水量"] = _weather_column(frame, "降水量の合計", warnings).values
    daily["平均風速"] = _weather_column(frame, "平均風速", warnings).values
    daily = daily.dropna(subset=["date"]).sort_values("date").reset_index(drop=True)
    return add_calendar_features(daily), warnings


def add_calendar_features(daily: pd.DataFrame) -> pd.DataFrame:
    """main.ipynb と同じ：曜日・祝日から平日、前日の値は前の日の行から"""
    daily = daily.copy()
    daily["平日"] = daily["date"].dt.date.map(is_weekday)
    daily["最大遅延分"] = daily[[f"遅延_{i}" for i in range(5)]].max(axis=1)
    prev_day = daily["date"] - pd.Timedelta(days=1)
    by_date = daily.set_index("date")
    daily["前日降水量"] = prev_day.map(by_date["降水量"]).values
    daily["前日最大遅延分"] = prev_day.map(by_date["最大遅延分"]).values
    return daily


def load_daily(paths) -> tuple[pd.DataFrame, list, list]:
    """CSV（1つでも複数でも）を読み込み、日付でつなげた1日＝1行の表にする。
    9/8〜の merged.csv（fetch_data.py 形式）と 10/13〜の merged.csv（merge.py 形式）を混ぜてもよい。
    同じ日が複数のファイルにあるときは、天気のデータがあるほう（両方あれば後のファイル）を使う。"""
    paths = [Path(p) for p in ([paths] if isinstance(paths, (str, Path)) else paths)]
    if not paths:
        raise FileNotFoundError(
            "学習データが見つかりません。data フォルダに merged.csv を入れてください"
            "（複数入れてもよく、ファイル名は何でもよい）。")
    missing = [str(p) for p in paths if not p.exists()]
    if missing:
        raise FileNotFoundError(f"学習データが見つかりません: {', '.join(missing)}")

    parts, warnings = [], []
    for order, path in enumerate(paths):
        daily, w = prepare_daily(pd.read_csv(path, encoding="utf-8-sig"))
        warnings += [f"{path.name}: {x}" for x in w]
        parts.append(daily.assign(_order=order, _has_weather=daily["降水量"].notna()))
    both = pd.concat(parts, ignore_index=True)
    both = (both.sort_values(["date", "_has_weather", "_order"])
                .drop_duplicates("date", keep="last"))
    no_weather = both.loc[~both["_has_weather"], "date"]
    if len(no_weather):
        warnings.append("天気のデータがない日を学習から除外しました: "
                        + "、".join(f"{d:%m/%d}" for d in no_weather))
        both = both[both["_has_weather"]]
    daily = both.drop(columns=["_order", "_has_weather"]).sort_values("date").reset_index(drop=True)
    gaps = pd.date_range(daily["date"].min(), daily["date"].max()).difference(daily["date"])
    if len(gaps):
        warnings.append(f"データがない日が {len(gaps)} 日あります（例：{gaps[0]:%m/%d}）")
    return add_calendar_features(daily), warnings, [p.name for p in paths]


def to_slot_rows(daily: pd.DataFrame) -> tuple[pd.DataFrame, pd.Series, pd.Series]:
    """1日＝1行の表を、日×時間帯（1日5行）の表に広げる。tree_v2.ipynb の分析C と同じ形"""
    rows = []
    for _, d in daily.iterrows():
        for i in range(5):
            row = {c: d[c] for c in DAY_FEATURES}
            for j, col in enumerate(SLOT_FEATURES):
                row[col] = int(i == j)
            row["_y"] = int(d[f"遅延_{i}"] >= TARGET_THRESHOLD_MINUTES)
            row["_date"] = d["date"]
            rows.append(row)
    long = pd.DataFrame(rows)
    return long[FEATURES].astype(float), long["_y"], long["_date"]


# ---------------------------------------------------------------------------
# 評価
# ---------------------------------------------------------------------------
def grouped_cv_predictions(build, X, y, groups, repeats=CV_REPEATS, seed=42):
    """train_delay_model.py の「9日分を評価用に取り分ける」を、日付ごとにまとめて行う（同じ日の5行を分けない）"""
    splitter = GroupShuffleSplit(n_splits=repeats, test_size=TEST_SIZE, random_state=seed)
    out = []
    for fold, (tr, te) in enumerate(splitter.split(X, y, groups), start=1):
        if y.iloc[tr].nunique() < 2:
            continue
        model = build().fit(X.iloc[tr], y.iloc[tr])
        proba = model.predict_proba(X.iloc[te])[:, 1]
        out.append(pd.DataFrame({"交差検証回": fold, "index": te, "確率": proba}))
    return pd.concat(out, ignore_index=True)


def score(y_true, proba) -> dict:
    """train_delay_model.py と同じ評価指標＋ROC-AUC"""
    pred = (proba >= PREDICT_THRESHOLD).astype(int)
    return {
        "accuracy": round(float(accuracy_score(y_true, pred)), 3),
        "balanced_accuracy": round(float(balanced_accuracy_score(y_true, pred)), 3),
        "precision": round(float(precision_score(y_true, pred, zero_division=0)), 3),
        "recall": round(float(recall_score(y_true, pred, zero_division=0)), 3),
        "f1": round(float(f1_score(y_true, pred, zero_division=0)), 3),
        "roc_auc": round(float(roc_auc_score(y_true, proba)), 3),
        "brier": round(float(brier_score_loss(y_true, proba)), 3),
        "log_loss": round(float(log_loss(y_true, proba, labels=[0, 1])), 3),
        "confusion_matrix": confusion_matrix(y_true, pred, labels=[0, 1]).tolist(),
    }


def _auc_of(build, X, y, groups, repeats) -> float:
    oof = grouped_cv_predictions(build, X, y, groups, repeats=repeats)
    return float(roc_auc_score(y.iloc[oof["index"]], oof["確率"]))


def permutation_test(X, y, groups, n=N_PERMUTATIONS, repeats=5, seed=0) -> dict:
    """tree_v2.ipynb の perm_test と同じ考え方：
    日単位で答え（その日の5時間帯ぶん）を別の日と入れ替え、天気・曜日などと無関係にしても
    同じくらい当たるかを見る。時間帯ごとの遅れやすさはそのまま残るので、
    「その日の条件（天気・平日・前日の遅延）が、時間帯の傾向以上に役立っているか」を確かめられる。"""
    rng = np.random.default_rng(seed)
    y_arr, g = np.asarray(y), np.asarray(groups)
    days = np.unique(g)
    idx = {d: np.where(g == d)[0] for d in days}
    observed = _auc_of(build_logistic, X, y, groups, repeats)
    scores = []
    for _ in range(n):
        yp = np.empty_like(y_arr)
        for d, d2 in zip(days, rng.permutation(days)):
            yp[idx[d]] = y_arr[idx[d2]]
        scores.append(_auc_of(build_logistic, X, pd.Series(yp), groups, repeats))
    scores = np.array(scores)
    return {
        "observed_auc": round(observed, 3),
        "shuffled_mean_auc": round(float(scores.mean()), 3),
        "p_value": round(float((np.sum(scores >= observed) + 1) / (n + 1)), 3),
        "n": n,
    }


def leaf_rules(clf, names, X, y) -> list[dict]:
    """tree_v2.ipynb の leaf_rules をもとに、葉ごとの条件・件数・遅延の割合を表にする
    （同じ特徴量の条件は「21.0〜74.8mm」のようにまとめる）"""
    t = clf.tree_
    texts = {}

    def describe(bounds):
        parts = []
        for name, (lo, hi) in bounds.items():
            if name.startswith("時間帯_"):
                parts.append(f"時間帯が{name[4:]}" + ("" if lo is not None else "以外"))
            elif name == "平日":
                parts.append("平日" if lo is not None else "土日祝")
            else:
                u = UNITS.get(name, "")
                if lo is not None and hi is not None:
                    parts.append(f"{name} {lo:.1f}〜{hi:.1f}{u}")
                elif lo is not None:
                    parts.append(f"{name} > {lo:.1f}{u}")
                else:
                    parts.append(f"{name} ≤ {hi:.1f}{u}")
        return " かつ ".join(parts) or "（全体）"

    def rec(node, bounds):
        if t.children_left[node] == -1:
            texts[node] = describe(bounds)
            return
        f, th = names[t.feature[node]], float(t.threshold[node])
        lo, hi = bounds.get(f, (None, None))
        left = dict(bounds); left[f] = (lo, th if hi is None else min(hi, th))
        right = dict(bounds); right[f] = (th if lo is None else max(lo, th), hi)
        rec(t.children_left[node], left)
        rec(t.children_right[node], right)

    rec(0, {})
    leaf_id = clf.apply(X)
    y_arr = np.asarray(y)
    rows = []
    for lid in np.unique(leaf_id):
        m = leaf_id == lid
        rows.append({"条件": texts[lid], "件数": int(m.sum()), "うち遅延": int(y_arr[m].sum()),
                     "遅延の割合": round(float(y_arr[m].mean()), 3)})
    return sorted(rows, key=lambda r: r["遅延の割合"], reverse=True)


# ---------------------------------------------------------------------------
# 学習して保存
# ---------------------------------------------------------------------------
def train_and_save(data_path=None, model_path=MODEL_PATH, metrics_path=METRICS_PATH,
                   predictions_path=PREDICTIONS_PATH, n_permutations=N_PERMUTATIONS) -> dict:
    daily, warnings, file_names = load_daily(data_path if data_path else find_data_files())
    X, y, dates = to_slot_rows(daily)

    if len(daily) <= TEST_SIZE:
        raise ValueError(f"評価用{TEST_SIZE}日と学習用データを確保するには、{TEST_SIZE + 1}日分以上必要です。")
    if y.nunique() < 2 or y.value_counts().min() < 2:
        raise ValueError("30分以上の遅延あり・なしが、それぞれ2件以上必要です。")

    # 1. 交差検証（日付ごとに9日分を取り分けて評価、を CV_REPEATS 回）
    evaluation, oof_all = {}, {}
    for key, build in MODEL_BUILDERS.items():
        oof = grouped_cv_predictions(build, X, y, dates)
        evaluation[key] = score(y.iloc[oof["index"]].to_numpy(), oof["確率"].to_numpy())
        oof_all[key] = oof
    # 画面には「確率」を表示するので、確率のずれ（ブライアスコア）が小さいほうを採用する。
    # （ランダムフォレストは main.ipynb の class_weight="balanced" のため確率が高めに出やすい）
    best = min(evaluation, key=lambda k: evaluation[k]["brier"])

    # 評価用の予測結果CSV（train_delay_model.py と同じ形式＋時間帯）
    oof = oof_all[best]
    slot_idx = np.argmax(X[SLOT_FEATURES].to_numpy(), axis=1)
    actual = y.iloc[oof["index"]].to_numpy()
    Path(predictions_path).parent.mkdir(parents=True, exist_ok=True)
    pd.DataFrame({
        "交差検証回": oof["交差検証回"],
        "日付": dates.iloc[oof["index"]].dt.strftime("%Y-%m-%d").to_numpy(),
        "時間帯": [TIME_SLOTS[i] for i in slot_idx[oof["index"]]],
        "実際の結果": np.where(actual == 1, "30分以上", "30分未満"),
        "予測結果": np.where(oof["確率"] >= PREDICT_THRESHOLD, "30分以上", "30分未満"),
        "30分以上の遅延確率": oof["確率"].round(3),
    }).to_csv(predictions_path, index=False, encoding="utf-8-sig")

    # 2. 特徴量の組み合わせ別（ロジスティック回帰）
    groups = {"天気のみ": WEATHER_FEATURES, "時間帯・平日のみ": ["平日"] + SLOT_FEATURES, "すべて": FEATURES}
    group_auc = {name: round(_auc_of(lambda c=cols: _subset_logistic(c), X, y, dates, CV_REPEATS), 3)
                 for name, cols in groups.items()}

    # 3. 並べ替え検定（tree_v2.ipynb と同じ考え方）
    perm = permutation_test(X, y, dates, n=n_permutations) if n_permutations else None

    # 4. 全データで学習し直して保存（既存プログラムと同じ）
    models = {key: build().fit(X, y) for key, build in MODEL_BUILDERS.items()}
    lr = models["logistic"][-1]
    rf = models["random_forest"][-1]
    importance = {
        "random_forest": dict(zip(FEATURES, np.round(rf.feature_importances_, 4).tolist())),
        "logistic": dict(zip(FEATURES, np.round(lr.coef_[0], 4).tolist())),
    }
    tree = build_tree().fit(X.fillna(X.median()), y)
    rules = leaf_rules(tree, FEATURES, X.fillna(X.median()), y)

    trained_at = dt.datetime.now().strftime("%Y-%m-%d %H:%M")
    n_pos = int(y.sum())
    bundle = {
        # train_delay_model.py と同じキー
        "model": models[best],
        "feature_columns": FEATURES,
        "target_threshold_minutes": TARGET_THRESHOLD_MINUTES,
        # アプリ用に追加したキー
        "models": models,
        "best_model": best,
        "train_min": {c: float(X[c].min()) for c in NUMERIC_FEATURES if X[c].notna().any()},
        "train_max": {c: float(X[c].max()) for c in NUMERIC_FEATURES if X[c].notna().any()},
        "rank_thresholds": RANK_THRESHOLDS,
        "trained_at": trained_at,
        "sklearn_version": sklearn.__version__,
    }
    metrics = {
        "trained_at": trained_at,
        "data": {
            "rows": int(len(y)), "days": int(len(daily)),
            "start": f"{daily['date'].min():%Y-%m-%d}", "end": f"{daily['date'].max():%Y-%m-%d}",
            "positive": n_pos, "positive_rate": round(n_pos / len(y), 3),
            "missing_counts": {c: int(X[c].isna().sum()) for c in NUMERIC_FEATURES},
            "warnings": warnings,
            "files": file_names,
        },
        "test_days": TEST_SIZE,
        "cv_repeats": CV_REPEATS,
        "eval_threshold": PREDICT_THRESHOLD,
        "baseline_accuracy": round(1 - n_pos / len(y), 3),
        "best_model": best,
        "evaluation": evaluation,
        "feature_group_auc": group_auc,
        "permutation_test": perm,
        "feature_importance": importance,
        "tree_rules": rules,
        "rank_thresholds": list(RANK_THRESHOLDS),
        "train_max": {k: v for k, v in bundle["train_max"].items() if k != "前日最大遅延分"},
        "source_programs": {
            "ロジスティック回帰": "train_delay_model.py",
            "ランダムフォレスト・特徴量": "main.ipynb",
            "祝日・検証方法・並べ替え検定・決定木": "tree_v2.ipynb",
        },
    }
    Path(model_path).parent.mkdir(parents=True, exist_ok=True)
    Path(metrics_path).parent.mkdir(parents=True, exist_ok=True)
    joblib.dump(bundle, model_path)
    Path(metrics_path).write_text(json.dumps(metrics, ensure_ascii=False, indent=2), encoding="utf-8")
    return metrics


def _subset_logistic(cols):
    """特徴量の一部だけを使うロジスティック回帰（組み合わせ別の比較用）"""
    from sklearn.compose import ColumnTransformer

    return make_pipeline(ColumnTransformer([("use", "passthrough", cols)]), build_logistic())


# ---------------------------------------------------------------------------
# 読み込み・予測（アプリから使う関数）
# ---------------------------------------------------------------------------
def load_model(model_path=MODEL_PATH) -> dict:
    """学習済みモデルを読み込む。失敗したら ModelLoadError を出す"""
    model_path = Path(model_path)
    if not model_path.exists():
        raise ModelLoadError(f"モデルが読み込めません（ファイルがありません: {model_path.name}）")
    try:
        bundle = joblib.load(model_path)
    except Exception as e:  # 壊れたファイル・scikit-learn のバージョン違いなど
        raise ModelLoadError(f"モデルが読み込めません（{type(e).__name__}）") from e
    if not isinstance(bundle, dict) or "models" not in bundle:
        raise ModelLoadError("モデルが読み込めません（ファイルの形式が違います）")
    return bundle


def load_metrics(metrics_path=METRICS_PATH) -> dict:
    metrics_path = Path(metrics_path)
    if not metrics_path.exists():
        raise ModelLoadError(f"評価指標ファイルがありません: {metrics_path.name}")
    return json.loads(metrics_path.read_text(encoding="utf-8"))


def risk_rank(probability: float, thresholds=RANK_THRESHOLDS) -> str:
    low, high = thresholds
    return "低" if probability < low else "中" if probability < high else "高"


def make_features(date: dt.date, time_slot, precip=None, prev_precip=None, wind=None,
                  prev_delay=None) -> pd.DataFrame:
    """1日・1時間帯ぶんの特徴量（値がないものは None でよい。学習データの中央値で補完される）

    precip: 当日の降水量(mm/日)、prev_precip: 前日の降水量(mm)、wind: 日平均風速(m/s)、
    prev_delay: 前日の最大遅延分（分からなければ None）。いずれも東京の値。
    """
    slot = normalize_time_slot(time_slot)
    if slot is None:
        raise ValueError(f"時間帯が正しくありません: {time_slot}")
    row = {"降水量": precip, "平均風速": wind, "平日": is_weekday(date),
           "前日降水量": prev_precip, "前日最大遅延分": prev_delay}
    for i, col in enumerate(SLOT_FEATURES):
        row[col] = int(i == slot)
    return pd.DataFrame([row], columns=FEATURES).astype(float)


def predict_delay(bundle: dict, date: dt.date, time_slot, precip=None, prev_precip=None, wind=None,
                  temp=None, prev_delay=None, model_name: str | None = None) -> dict:
    """遅延確率・危険度・注意メッセージを返す（temp は互換性のための引数で、使わない）"""
    X = make_features(date, time_slot, precip, prev_precip, wind, prev_delay)

    notes = []
    if pd.isna(X.at[0, "降水量"]):
        notes.append("降水量のデータが不足しているため参考値です")
    over = [c for c, mx in bundle["train_max"].items() if pd.notna(X.at[0, c]) and X.at[0, c] > mx]
    if over:
        notes.append("過去データにない気象条件のため参考値です。最新の運行情報を確認してください")
    # 学習データの範囲の外へ引き延ばさない（範囲の端の値で予測する）
    for c, lo in bundle["train_min"].items():
        X[c] = X[c].clip(lower=lo, upper=bundle["train_max"][c])

    model = bundle["models"][model_name or bundle["best_model"]]
    prob = float(model.predict_proba(X[bundle["feature_columns"]])[0, 1])
    return {"probability": prob, "rank": risk_rank(prob, bundle["rank_thresholds"]),
            "is_reference": bool(notes), "notes": notes}


def predict_all_slots(bundle: dict, date: dt.date, precip=None, prev_precip=None, wind=None,
                      temp=None, prev_delay=None, model_name: str | None = None) -> pd.DataFrame:
    """5つの時間帯すべての遅延確率を表で返す（ホーム画面の横並び表示用）"""
    rows = []
    for i, slot in enumerate(TIME_SLOTS):
        r = predict_delay(bundle, date, i, precip, prev_precip, wind, temp, prev_delay, model_name)
        rows.append({"時間帯": slot, "遅延確率": r["probability"], "危険度": r["rank"],
                     "参考値": r["is_reference"], "注意": " / ".join(r["notes"])})
    return pd.DataFrame(rows)


# ---------------------------------------------------------------------------
if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="時間帯ごとの30分以上の遅延を予測するモデルを学習して保存する")
    parser.add_argument("--data", nargs="+", help="使う CSV（複数可）。省略すると data フォルダの CSV をすべて使う")
    parser.add_argument("--permutations", type=int, default=N_PERMUTATIONS, help="並べ替え検定の回数（0で省略）")
    args = parser.parse_args()

    print("学習中（並べ替え検定があるため1〜2分かかります）…")
    m = train_and_save(args.data, n_permutations=args.permutations)
    d = m["data"]
    print("読み込んだファイル:", "、".join(d["files"]))
    print(f"データ: {d['days']}日 × 5時間帯 = {d['rows']}件（{d['start']}〜{d['end']}）"
          f" / 30分以上の遅延: {d['positive']}件（{d['positive_rate']:.1%}）")
    for w in d["warnings"]:
        print("  注意:", w)
    print(f"検証: 日付ごとに{m['test_days']}日分を評価用に取り分ける × {m['cv_repeats']}回")
    for key, s in m["evaluation"].items():
        print(f"  {MODEL_LABELS[key]}: ROC-AUC {s['roc_auc']:.3f}  均衡正解率 {s['balanced_accuracy']:.3f}"
              f"  正解率 {s['accuracy']:.3f}  再現率 {s['recall']:.3f}  ブライア {s['brier']:.3f}")
    print("特徴量の組み合わせ別 ROC-AUC:", m["feature_group_auc"])
    if m["permutation_test"]:
        p = m["permutation_test"]
        print(f"並べ替え検定: 本物 {p['observed_auc']:.3f} / シャッフル平均 {p['shuffled_mean_auc']:.3f} / p={p['p_value']:.3f}")
    print(f"予測に使うモデル: {MODEL_LABELS[m['best_model']]}")
    print(f"保存先: {MODEL_PATH} / {METRICS_PATH} / {PREDICTIONS_PATH}")
