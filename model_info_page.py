"""
予測根拠・モデル情報画面（担当：太刀岡）

単体で確認:   streamlit run model_info_page.py
アプリに組み込む: from model_info_page import show  →  タブやページの中で show() を呼ぶ
"""

from __future__ import annotations

import altair as alt
import pandas as pd
import streamlit as st

from delay_model import METRICS_PATH, MODEL_LABELS, ModelLoadError, load_metrics

INDICATOR_LABELS = {
    "roc_auc": "ROC-AUC",
    "balanced_accuracy": "均衡正解率",
    "accuracy": "正解率",
    "precision": "適合率",
    "recall": "再現率",
    "f1": "F1スコア",
    "brier": "ブライアスコア",
}


THEME_CSS = """
<style>
.stApp { background: #f6f4ef; color: #252a31;
         font-family: "Yu Gothic UI", "Meiryo", "Noto Sans JP", sans-serif; }
div[data-testid="stMetric"] { padding: 1rem 1.1rem; border: 1px solid #ece6db;
         border-top: 2px solid #b69b63; border-radius: 4px;
         background: linear-gradient(145deg, #fffefb, #f8f6f0); }
div[data-testid="stMetricLabel"] { color: #77736a; font-weight: 600; letter-spacing: 0.04em; }
div[data-testid="stMetricValue"] { color: #252a31; font-weight: 700; }
div[data-testid="stMetricValue"] div { white-space: normal !important; overflow: visible !important;
         text-overflow: clip !important; }
</style>
"""


def apply_theme():
    """app.py（ホーム）と同じ配色にする。単独ページとして開くときに呼ぶ"""
    st.markdown(THEME_CSS, unsafe_allow_html=True)


@st.cache_data
def _load_metrics_cached(_mtime: float):
    # ファイルの更新時刻をキーにして、再学習したら自動で読み直す
    return load_metrics()


def _importance_chart(values: dict, signed: bool) -> alt.Chart:
    df = pd.DataFrame({"特徴量": list(values.keys()), "値": list(values.values())})
    df["向き"] = df["値"].map(lambda v: "遅延しやすくなる" if v > 0 else "遅延しにくくなる")
    df = df.reindex(df["値"].abs().sort_values(ascending=False).index)
    color = (
        alt.Color("向き:N", scale=alt.Scale(domain=["遅延しやすくなる", "遅延しにくくなる"],
                                            range=["#d6604d", "#4393c3"]),
                  legend=alt.Legend(orient="bottom", title=None))
        if signed else alt.value("#4c78a8")
    )
    return (
        alt.Chart(df)
        .mark_bar()
        .encode(
            x=alt.X("値:Q", title="係数（標準化後）" if signed else "重要度"),
            y=alt.Y("特徴量:N", sort=None, title=None, axis=alt.Axis(labelLimit=200, labelOverlap=False)),
            color=color,
            tooltip=["特徴量", alt.Tooltip("値:Q", format=".3f")],
        )
        .properties(height=34 * len(df))
    )


def show():
    st.header("予測根拠・モデル情報")
    st.caption("遅延リスクをどのように予測しているか、学習データと評価結果を表示します。")

    try:
        if not METRICS_PATH.exists():
            raise ModelLoadError(f"評価指標ファイルがありません: {METRICS_PATH.name}")
        m = _load_metrics_cached(METRICS_PATH.stat().st_mtime)
    except (ModelLoadError, ValueError) as e:  # ValueError: JSONが壊れているとき
        st.error(f"モデル情報が読み込めません：{e}")
        st.info("`python delay_model.py` を実行してモデルを学習してください。")
        return

    d = m["data"]
    best = m["best_model"]

    # --- 学習データの概要 ---
    st.subheader("学習データ")
    c1, c2, c3 = st.columns([1, 1, 1.4])
    c1.metric("データ件数", f"{d['rows']}件")  # 日数 × 5時間帯
    c2.metric("30分以上の遅延", f"{d['positive']}件（{d['positive_rate']:.0%}）")
    c3.metric("予測に使うモデル", MODEL_LABELS[best])
    st.caption(f"期間：{d['start']} 〜 {d['end']}（{d['days']}日 × 5時間帯）　／　学習日時：{m['trained_at']}")
    if d.get("files"):
        st.caption("学習に使ったファイル：" + "、".join(d["files"]))
    units = {"降水量": "mm", "前日降水量": "mm", "平均風速": "m/s"}
    st.caption("学習データの最大値："
               + "、".join(f"{k} {v:g}{units.get(k, '')}" for k, v in m["train_max"].items())
               + "（これを超える予報は参考値として表示）")
    for w in d.get("warnings", []):
        st.warning(w)
    if m.get("source_programs"):
        st.caption("もとにしたチームの既存プログラム："
                   + "、".join(f"{k}＝{v}" for k, v in m["source_programs"].items()))

    # --- 評価指標 ---
    st.subheader("評価指標")
    st.caption(f"学習に使っていない日で評価しています（{m.get('test_days', 9)}日分を評価用に取り分け、"
               f"残りで学習、を取り分け方を変えて{m.get('cv_repeats', 1)}回）。同じ日の5つの時間帯は"
               "必ず同じ側に入れています。正解率などは、確率"
               f"{m.get('eval_threshold', 0.5):.0%}以上を「遅延あり」の予測とみなして計算しています。")
    ev = m["evaluation"]
    cols = st.columns(len(ev))
    for col, (key, s) in zip(cols, ev.items()):
        with col:
            st.markdown(f"**{MODEL_LABELS[key]}**" + ("　✅ 採用" if key == best else ""))
            a, b = st.columns(2)
            a.metric("ROC-AUC", f"{s['roc_auc']:.3f}")
            b.metric("均衡正解率", f"{s.get('balanced_accuracy', float('nan')):.3f}")

    table = pd.DataFrame(
        {MODEL_LABELS[k]: {label: s[i] for i, label in INDICATOR_LABELS.items() if i in s} for k, s in ev.items()}
    )
    st.dataframe(table.style.format("{:.3f}"), use_container_width=True)
    st.info(
        f"30分以上の遅延は全体の {d['positive_rate']:.0%} しかないため、すべて「遅延なし」と答えても正解率は "
        f"{m['baseline_accuracy']:.1%} になります。そのため正解率ではなく、確率の順位の正しさを表す "
        "**ROC-AUC** と、遅延あり・なしを同じ重さで見る **均衡正解率**（どちらも0.5で当てずっぽう、"
        "1.0で完全）で見ています。"
        "画面には遅延の「確率」を表示するので、予測には確率のずれ（**ブライアスコア**、小さいほど良い）が"
        "小さい方を使っています。"
    )

    with st.expander(f"混同行列（確率{m.get('eval_threshold', 0.5):.0%}以上を「遅延あり」とした場合）"):
        for key, s in ev.items():
            cm = s["confusion_matrix"]
            st.markdown(f"**{MODEL_LABELS[key]}**")
            st.table(pd.DataFrame(cm, index=["実際：遅延なし", "実際：遅延あり"],
                                  columns=["予測：遅延なし", "予測：遅延あり"]))

    # --- 偶然ではないかの確認 ---
    if m.get("feature_group_auc") or m.get("permutation_test"):
        st.subheader("天気などの条件は役に立っているか")
    if m.get("feature_group_auc"):
        st.markdown("**特徴量の組み合わせ別の ROC-AUC（ロジスティック回帰）**")
        g = m["feature_group_auc"]
        gcols = st.columns(len(g))
        for col, (name, auc) in zip(gcols, g.items()):
            col.metric(name, f"{auc:.3f}")
    p = m.get("permutation_test")
    if p:
        st.markdown("**並べ替え検定**（tree_v2.ipynb と同じ方法）")
        st.caption(f"日ごとの答えをほかの日と入れ替えて（{p['n']}回）、その日の条件（天気・平日・前日の遅延）と"
                   "無関係にしても同じくらい当たるかを調べました。時間帯ごとの遅れやすさはそのまま残るので、"
                   "「その日の条件が、時間帯の傾向以上に役立っているか」がわかります。")
        q1, q2, q3 = st.columns(3)
        q1.metric("本物の ROC-AUC", f"{p['observed_auc']:.3f}")
        q2.metric("入れ替えた場合の平均", f"{p['shuffled_mean_auc']:.3f}")
        q3.metric("p値", f"{p['p_value']:.3f}")
        if p["p_value"] >= 0.05:
            st.warning(
                f"p値が {p['p_value']:.2f} で、入れ替えた場合と差があるとは言えません。現在のデータ"
                f"（{d['days']}日分）では、天気・平日・前日の遅延が時間帯の傾向以上に役立っているとは確認できず、"
                "予測は主に「どの時間帯か」で決まっています。tree_v2.ipynb の分析（分析A〜Cとも p=0.50〜0.87）"
                "と同じ結論です。データを増やして再学習すると変わる可能性があります。"
            )
        else:
            st.success(f"p値が {p['p_value']:.3f} で、その日の条件が時間帯の傾向以上に予測に役立っていると言えます。")

    # --- 特徴量の重要度 ---
    st.subheader("どの条件が予測に効いているか")
    tab_rf, tab_lr = st.tabs(["ランダムフォレスト（重要度）", "ロジスティック回帰（係数）"])
    with tab_rf:
        st.altair_chart(_importance_chart(m["feature_importance"]["random_forest"], signed=False),
                        use_container_width=True)
        st.caption("値が大きいほど、予測の判断に多く使われた特徴量です（合計 1.0）。")
    with tab_lr:
        st.altair_chart(_importance_chart(m["feature_importance"]["logistic"], signed=True),
                        use_container_width=True)
        st.caption("赤は値が大きいほど遅延しやすく、青は遅延しにくくなる特徴量です。"
                   "各特徴量を標準化しているので、棒の長さで影響の大きさを比べられます。")

    # --- 決定木のルール ---
    st.subheader("決定木による分岐ルール")
    st.caption("tree_v2.ipynb の分析C と同じ設定（深さ3、葉に8件以上）の決定木で、データをどの条件で分けると"
               "遅延の割合が変わるかを示したものです（説明用で、予測そのものには使っていません）。")
    rules = pd.DataFrame(m["tree_rules"])
    st.dataframe(
        rules,
        use_container_width=True,
        hide_index=True,
        column_config={
            "遅延の割合": st.column_config.ProgressColumn("遅延の割合", min_value=0, max_value=1,
                                                         format="percent"),
        },
    )

    # --- 危険度の基準 ---
    low, high = m["rank_thresholds"]
    st.subheader("危険度の基準")
    st.markdown(
        f"- **低**：遅延確率 {low:.0%} 未満\n"
        f"- **中**：{low:.0%} 以上 {high:.0%} 未満\n"
        f"- **高**：{high:.0%} 以上"
    )
    st.warning(
        f"学習データは {d['days']} 日分と少ないため、予測は目安です。"
        "台風・大雪など過去データにない気象条件では「参考値」と表示されます。最新の運行情報もあわせて確認してください。"
    )


if __name__ == "__main__":
    st.set_page_config(page_title="予測根拠・モデル情報", layout="wide")
    apply_theme()
    show()
