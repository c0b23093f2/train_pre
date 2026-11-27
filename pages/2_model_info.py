"""予測根拠・モデル情報（担当：太刀岡）

app.py と同じフォルダーに pages/ ごと置くと、Streamlit のサイドバーにページとして表示される。
"""
import streamlit as st

from model_info_page import apply_theme, show

st.set_page_config(page_title="予測根拠・モデル情報", layout="wide")
apply_theme()
# ホーム（app.py）と同じく、Streamlit 標準の左サイドバーは出さない（戻るリンクで移動する）
st.markdown(
    """<style>
    section[data-testid="stSidebar"], [data-testid="stSidebarCollapsedControl"],
    [data-testid="stExpandSidebarButton"] { display: none !important; }
    </style>""",
    unsafe_allow_html=True,
)
try:
    st.page_link("app.py", label="← 遅延リスク予測・遅延実績（ホーム）へ戻る")
except Exception:      # このページだけを単体で起動したときは、戻り先が無いのでリンクを出さない
    pass
show()
