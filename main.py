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
if not os.path.exists(DATA_FILE):
    df_init = pd.DataFrame(columns=["日付", "カテゴリ", "金額", "購入場所", "値引き率", "メモ"])
    df_init.to_csv(DATA_FILE, index=False, encoding="utf_8_sig")

st.title("手軽な家計簿アプリ（支出特化・分析強化版）")

# --- 入力フォームエリア ---
st.header("支出の入力")
with st.form(key="kakeibo_form", clear_on_submit=True):
    date = st.date_input("日付", datetime.date.today())
    
    # 充実させたカテゴリリスト
    categories = [
        "食費", "外食", "日用品", "医療費", 
        "スマホ代", "ネット代", "それ以外の通信費", 
        "交通費", "交際費", "趣味・娯楽", "住宅・光熱費", "その他"
    ]
    category = st.selectbox("カテゴリ", categories)
    
    amount = st.number_input("金額（円）", min_value=0, step=100)
    
    # ① ネット販売か実店舗か
    purchase_place = st.radio("購入場所", ["実店舗", "ネット販売"], horizontal=True)
    
    # ② 値引き率（％）
    discount_rate = st.number_input("値引き率（% ※なければ0または空欄）", min_value=0.0, max_value=100.0, step=1.0, value=0.0)
    
    memo = st.text_input("メモ")

    submit_button = st.form_submit_button(label="記録する")

# 登録ボタンが押された時の処理
if submit_button:
    new_data = pd.DataFrame([[
        str(date), category, amount, purchase_place, discount_rate if discount_rate > 0 else "", memo
    ]], columns=["日付", "カテゴリ", "金額", "購入場所", "値引き率", "メモ"])
    
    df = pd.read_csv(DATA_FILE, encoding="utf_8_sig")
    df = pd.concat([df, new_data], ignore_index=True)
    df.to_csv(DATA_FILE, index=False, encoding="utf_8_sig")
    st.success("記録しました！")

# --- データの読み込み ---
try:
    df_all = pd.read_csv(DATA_FILE, encoding="utf_8_sig")
except Exception:
    df_all = pd.read_csv(DATA_FILE, encoding="utf-8")

if not df_all.empty:
    # 日付列を日付型に変換して「年-月」列を作る
    df_all["日付"] = pd.to_datetime(df_all["日付"])
    df_all["年月"] = df_all["日付"].dt.strftime("%Y年%m月")
    
    # --- サイドバー：月次フィルター・予算設定 ---
    st.sidebar.header("⚙️ 設定・絞り込み")
    
    available_months = sorted(df_all["年月"].unique(), reverse=True)
    selected_month = st.sidebar.selectbox("表示する月を選択", available_months)
    
    # 選択した月のデータに絞り込む
    df_month = df_all[df_all["年月"] == selected_month].copy()
    df_month["日付"] = df_month["日付"].dt.strftime("%Y-%m-%d")
    
    st.sidebar.divider()
    
    # 予算設定（主要カテゴリ）
    st.sidebar.subheader("🎯 月別予算の設定")
    budget_options = [0, 5000, 10000, 20000, 30000, 40000, 50000, 70000, 100000, 150000]
    
    budgets = {}
    for cat in ["食費", "外食", "日用品", "医療費", "趣味・娯楽"]:
        default_idx = 3 if cat == "食費" else 0
        budgets[cat] = st.sidebar.selectbox(f"{cat} の予算", budget_options, index=default_idx, key=f"budget_{cat}")

    # --- メインエリア：月次サマリーとアラート ---
    st.header(f"📊 {selected_month} の支出レポート")
    
    total_expense = df_month["金額"].sum()
    st.metric("今月の総支出", f"{total_expense:,} 円")
    
    st.divider()

    # --- 予算超過アラートのチェック ---
    expense_summary = df_month.groupby("カテゴリ")["金額"].sum()
    for cat, budget_val in budgets.items():
        if budget_val > 0:
            spent = expense_summary.get(cat, 0)
            if spent > budget_val:
                st.warning(f"⚠️ **【予算超過アラート】** {cat} の今月の支出（{spent:,}円）が、設定予算（{budget_val:,}円）を超えています！")

    # --- データ編集・削除エリア ---
    st.subheader("📝 履歴の確認・編集")
    st.caption("※表の中をダブルクリックして値を直接変更できます。行の左端にチェックを入れて『選択行を削除』を押すと削除できます。")

    display_cols = ["日付", "カテゴリ", "金額", "購入場所", "値引き率", "メモ"]
    edited_df_month = st.data_editor(
        df_month[display_cols],
        use_container_width=True,
        num_rows="dynamic",
        key=f"data_editor_{selected_month}"
    )

    if st.button("変更を確定して保存する", type="primary"):
        df_all["日付"] = df_all["日付"].astype(str)
        df_other = df_all[df_all["年月"] != selected_month]
        
        edited_df_month["日付"] = pd.to_datetime(edited_df_month["日付"])
        edited_df_month["年月"] = edited_df_month["日付"].dt.strftime("%Y年%m月")
        edited_df_month["日付"] = edited_df_month["日付"].dt.strftime("%Y-%m-%d")
        
        final_df = pd.concat([df_other[display_cols + ["年月"]], edited_df_month], ignore_index=True)
        final_df[display_cols].to_csv(DATA_FILE, index=False, encoding="utf_8_sig")
        st.success("データを更新しました！")
        st.rerun()

    # --- エクスポート & 印刷エリア ---
    st.divider()
    col_dl1, col_dl2 = st.columns(2)
    with col_dl1:
        csv_data = df_month[display_cols].to_csv(index=False, encoding="utf_8_sig")
        st.download_button(
            label=f"📥 {selected_month} のデータをCSVダウンロード",
            data=csv_data,
            file_name=f"kakeibo_{selected_month.replace('年','_').replace('月','')}.csv",
            mime="text/csv"
        )
    with col_dl2:
        if st.button("🖨️ この月のレポートを印刷 / PDF保存"):
            st.markdown(
                """
                <script>
                window.print();
                </script>
                """,
                unsafe_allow_html=True
            )
            st.info("ブラウザの印刷ダイアログが開きます。「PDFに保存」を選択するとPDF化できます。")

    # --- 分析エリア ---
    st.subheader(f"📊 {selected_month} カテゴリ別支出内訳")
    col1, col2 = st.columns(2)
    with col1:
        if not expense_summary.empty and expense_summary.sum() > 0:
            st.dataframe(expense_summary)
        else:
            st.info("今月の支出データはありません。")
    with col2:
        if not expense_summary.empty and expense_summary.sum() > 0:
            fig, ax = plt.subplots()
            ax.pie(expense_summary, labels=expense_summary.index, autopct="%1.1f%%", startangle=90)
            ax.axis("equal")
            st.pyplot(fig)
        else:
            st.info("円グラフを表示するデータがありません。")
else:
    st.info("データがまだありません。上のフォームから入力してください。")
