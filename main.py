import datetime
import os

import matplotlib.pyplot as plt
import pandas as pd
import streamlit as st

# 日本語フォントの設定（文字化け対策）
plt.rcParams['font.family'] = 'sans-serif'

# データ保存用CSVファイルの設定
DATA_FILE = "kakeibo.csv"

# CSVファイルの初期化（存在しない場合のみ作成）
# Excel対応のため encoding="utf_8_sig" を指定
if not os.path.exists(DATA_FILE):
    df_init = pd.DataFrame(columns=["日付", "カテゴリ", "金額", "メモ"])
    df_init.to_csv(DATA_FILE, index=False, encoding="utf_8_sig")

st.title("手軽な家計簿アプリ")

# --- 入力フォームエリア ---
st.header("収支の入力")
with st.form(key="kakeibo_form", clear_on_submit=True):
    date = st.date_input("日付", datetime.date.today())
    category = st.selectbox("カテゴリ", ["食費", "日用品", "交際費", "交通費", "住宅・光熱費", "その他"])
    amount = st.number_input("金額（円）", min_value=0, step=100)
    memo = st.text_input("メモ")

    submit_button = st.form_submit_button(label="記録する")

# 登録ボタンが押された時の処理
if submit_button:
    new_data = pd.DataFrame([[str(date), category, amount, memo]], columns=["日付", "カテゴリ", "金額", "メモ"])
    # 既存のデータをBOM付きUTF-8で読み込み
    df = pd.read_csv(DATA_FILE, encoding="utf_8_sig")
    df = pd.concat([df, new_data], ignore_index=True)
    df.to_csv(DATA_FILE, index=False, encoding="utf_8_sig")
    st.success("記録しました！")

# --- データ表示・編集エリア ---
st.header("履歴と分析")
# 読み込み時にも encoding="utf_8_sig" を指定
try:
    df_display = pd.read_csv(DATA_FILE, encoding="utf_8_sig")
except Exception:
    # 過去の文字化けファイルが原因でエラーが出る場合のセーフティ
    df_display = pd.read_csv(DATA_FILE, encoding="utf-8")

if not df_display.empty:
    st.subheader("データの編集・削除")
    st.caption("※表の中をダブルクリックして値を直接変更できます。行の左端にチェックを入れて『選択行を削除』を押すと削除できます。")

    # 編集用データエディタの表示
    edited_df = st.data_editor(
        df_display,
        use_container_width=True,
        num_rows="dynamic",
        key="data_editor"
    )

    # 変更保存ボタン
    if st.button("変更を確定して保存する", type="primary"):
        edited_df.to_csv(DATA_FILE, index=False, encoding="utf_8_sig")
        st.success("データを更新しました！")
        st.rerun()

    # --- 分析エリア ---
    st.subheader("カテゴリ別支出")
    summary = edited_df.groupby("カテゴリ")["金額"].sum()

    # 左右に並べて表示
    col1, col2 = st.columns(2)
    with col1:
        st.dataframe(summary)
    with col2:
        if summary.sum() > 0:
            fig, ax = plt.subplots()
            ax.pie(summary, labels=summary.index, autopct="%1.1f%%", startangle=90)
            ax.axis("equal")
            st.pyplot(fig)
        else:
            st.info("集計可能な金額がありません。")
else:
    st.info("データがまだありません。上のフォームから入力してください。")