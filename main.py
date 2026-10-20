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
    df_init = pd.DataFrame(columns=["日付", "区分", "カテゴリ", "金額", "メモ"])
    df_init.to_csv(DATA_FILE, index=False, encoding="utf_8_sig")

st.title("手軽な家計簿アプリ（発展版）")

# --- 入力フォームエリア ---
st.header("収支の入力")
with st.form(key="kakeibo_form", clear_on_submit=True):
    date = st.date_input("日付", datetime.date.today())
    # 収入・支出の区分を追加
    income_expense = st.radio("区分", ["支出", "収入"], horizontal=True)
    
    # 区分に応じたカテゴリの切り替え
    if income_expense == "支出":
        category = st.selectbox("カテゴリ", ["食費", "日用品", "交際費", "交通費", "住宅・光熱費", "その他"])
    else:
        category = st.selectbox("カテゴリ", ["給与", "賞与", "副業", "一時収入", "その他"])
        
    amount = st.number_input("金額（円）", min_value=0, step=100)
    memo = st.text_input("メモ")

    submit_button = st.form_submit_button(label="記録する")

# 登録ボタンが押された時の処理
if submit_button:
    new_data = pd.DataFrame([[str(date), income_expense, category, amount, memo]], 
                            columns=["日付", "区分", "カテゴリ", "金額", "メモ"])
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
    
    # 1. 月の選択
    available_months = sorted(df_all["年月"].unique(), reverse=True)
    selected_month = st.sidebar.selectbox("表示する月を選択", available_months)
    
    # 選択した月のデータに絞り込む
    df_month = df_all[df_all["年月"] == selected_month].copy()
    # 表示用に日付を文字列に戻す
    df_month["日付"] = df_month["日付"].dt.strftime("%Y-%m-%d")
    
    st.sidebar.divider()
    
    # 3. カテゴリ別予算の設定（プルダウンで金額を選択）
    st.sidebar.subheader("🎯 月別予算の設定")
    budget_options = [0, 5000, 10000, 20000, 30000, 40000, 50000, 70000, 100000, 150000]
    expense_categories = ["食費", "日用品", "交際費", "交通費", "住宅・光熱費", "その他"]
    
    budgets = {}
    for cat in expense_categories:
        # デフォルト値の位置（例：食費は30000円など適当なインデックスを指定可能）
        default_idx = 3 if cat == "食費" else (2 if cat == "住宅・光熱費" else 0)
        budgets[cat] = st.sidebar.selectbox(f"{cat} の予算", budget_options, index=default_idx, key=f"budget_{cat}")

    # --- メインエリア：月次サマリーとアラート ---
    st.header(f"📊 {selected_month} の収支レポート")
    
    # 収入と支出の集計
    df_expense_month = df_month[df_month["区分"] == "支出"]
    df_income_month = df_month[df_month["区分"] == "収入"]
    
    total_expense = df_expense_month["金額"].sum()
    total_income = df_income_month["金額"].sum()
    balance = total_income - total_expense
    
    # サマリーメトリクス表示
    m1, m2, m3 = st.columns(3)
    m1.metric("総収入", f"{total_income:,} 円")
    m2.metric("総支出", f"{total_expense:,} 円")
    m3.metric("収支差額", f"{balance:,} 円", delta=f"{balance:,} 円")
    
    st.divider()

    # --- 予算超過アラートのチェック ---
    expense_summary = df_expense_month.groupby("カテゴリ")["金額"].sum()
    for cat, budget_val in budgets.items():
        if budget_val > 0:
            spent = expense_summary.get(cat, 0)
            if spent > budget_val:
                st.warning(f"⚠️ **【予算超過アラート】** {cat} の今月の支出（{spent:,}円）が、設定予算（{budget_val:,}円）を超えています！")

    # --- データ編集・削除エリア ---
    st.subheader("📝 履歴の確認・編集")
    st.caption("※表の中をダブルクリックして値を直接変更できます。行の左端にチェックを入れて『選択行を削除』を押すと削除できます。")

    # 編集用データエディタ（不要な「年月」列を除外して表示）
    display_cols = ["日付", "区分", "カテゴリ", "金額", "メモ"]
    edited_df_month = st.data_editor(
        df_month[display_cols],
        use_container_width=True,
        num_rows="dynamic",
        key=f"data_editor_{selected_month}"
    )

    if st.button("変更を確定して保存する", type="primary"):
        # 変更された月データを元の全データに反映させる
        df_all["日付"] = df_all["日付"].astype(str)
        df_other = df_all[df_all["年月"] != selected_month]
        
        # 画面で編集されたデータに「年月」を再付与
        edited_df_month["日付"] = pd.to_datetime(edited_df_month["日付"])
        edited_df_month["年月"] = edited_df_month["日付"].dt.strftime("%Y年%m月")
        edited_df_month["日付"] = edited_df_month["日付"].dt.strftime("%Y-%m-%d")
        
        # 結合して保存
        final_df = pd.concat([df_other[display_cols + ["年月"]], edited_df_month], ignore_index=True)
        final_df[display_cols].to_csv(DATA_FILE, index=False, encoding="utf_8_sig")
        st.success("データを更新しました！")
        st.rerun()

    # --- エクスポート & 印刷エリア ---
    st.divider()
    col_dl1, col_dl2 = st.columns(2)
    with col_dl1:
        # CSVダウンロード
        csv_data = df_month[display_cols].to_csv(index=False, encoding="utf_8_sig")
        st.download_button(
            label=f"📥 {selected_month} のデータをCSVダウンロード",
            data=csv_data,
            file_name=f"kakeibo_{selected_month.replace('年','_').replace('月','')}.csv",
            mime="text/csv"
        )
    with col_dl2:
        # 印刷・PDF保存用ボタン（ブラウザの印刷機能を呼び出し）
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
