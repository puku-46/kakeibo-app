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
    df_init = pd.DataFrame(columns=[
        "日付", "カテゴリ", "金額", "購入場所", 
        "現金", "カード", "金券", "電子マネー", "メモ"
    ])
    df_init.to_csv(DATA_FILE, index=False, encoding="utf_8_sig")

st.title("手軽な家計簿アプリ")

# --- データの読み込み ---
try:
    df_all = pd.read_csv(DATA_FILE, encoding="utf_8_sig")
except Exception:
    df_all = pd.read_csv(DATA_FILE, encoding="utf-8")

if not df_all.empty:
    df_all["日付"] = pd.to_datetime(df_all["日付"])
    df_all["年月"] = df_all["日付"].dt.strftime("%Y年%m月")

# --- タブによる画面の切り替え（画面変遷） ---
tab1, tab2 = st.tabs(["📝 支出の入力", "📊 レポート・履歴・印刷"])

# ==========================================
# タブ1：支出の入力画面
# ==========================================
with tab1:
    st.header("支出の入力")

    date = st.date_input("日付", datetime.date.today(), key="input_date")

    categories = [
        "食費", "外食", "ペット", "日用品", "医療費", 
        "スマホ代", "ネット・通信", "交通費", "光熱費", "その他"
    ]
    category = st.selectbox("カテゴリ", categories, key="input_category")

    with st.form(key="kakeibo_form", clear_on_submit=True):
        purchase_place = st.radio("購入場所", ["実店舗", "ネット販売"], horizontal=True)
        
        discount_memo = ""
        if category == "外食":
            st.markdown("---")
            st.markdown("🍽️ **【株主優待の利用】**")
            total_price = st.number_input("支払総額（メニューの合計金額・定価）", min_value=0, step=100, value=0)
            actual_price = st.number_input("実際に支払った額（自己負担額）", min_value=0, step=100, value=0)
            benefit = total_price - actual_price
            if benefit > 0:
                discount_memo = f"【総額:{total_price:,}円 / 優待利用:{benefit:,}円】"
        else:
            discount_rate = st.number_input("値引き率（% ※なければ0）", min_value=0.0, max_value=100.0, step=1.0, value=0.0)
            if discount_rate > 0:
                discount_memo = f"【値引き率:{int(discount_rate)}%】"

        st.markdown("---")
        st.markdown("💳 **【支払方法の内訳】それぞれの金額を入力してください**")
        
        col_p1, col_p2 = st.columns(2)
        with col_p1:
            pay_cash = st.number_input("現金（円）", min_value=0, step=100, value=0, key="p_cash")
            pay_ticket = st.number_input("金券・優待券（円）", min_value=0, step=100, value=0, key="p_ticket")
        with col_p2:
            pay_card = st.number_input("クレジットカード（円）", min_value=0, step=100, value=0, key="p_card")
            pay_qr = st.number_input("電子マネー / QR決済（円）", min_value=0, step=100, value=0, key="p_qr")
        
        amount = pay_cash + pay_card + pay_ticket + pay_qr
        st.info(f"💡 支払合計金額: **{amount:,} 円**")
        st.markdown("---")
        
        user_memo = st.text_input("メモ（自由記入）", key="input_memo")
        submit_button = st.form_submit_button(label="記録する")

    if submit_button:
        if amount == 0:
            st.warning("金額が0円です。支払内訳のいずれかに金額を入力してください。")
        else:
            final_memo = f"{discount_memo} {user_memo}".strip()
            new_data = pd.DataFrame([[
                str(date), category, amount, purchase_place, 
                pay_cash, pay_card, pay_ticket, pay_qr, final_memo
            ]], columns=[
                "日付", "カテゴリ", "金額", "購入場所", 
                "現金", "カード", "金券", "電子マネー", "メモ"
            ])
            
            df = pd.read_csv(DATA_FILE, encoding="utf_8_sig")
            df = pd.concat([df, new_data], ignore_index=True)
            df.to_csv(DATA_FILE, index=False, encoding="utf_8_sig")
            st.success("記録しました！「📊 レポート・履歴・印刷」タブから内容を確認できます。")

# ==========================================
# タブ2：レポート・履歴・印刷画面
# ==========================================
with tab2:
    if not df_all.empty:
        # 設定エリア（表示月・予算）
        st.subheader("⚙️ 表示月・予算の設定")
        col_s1, col_s2 = st.columns([1, 2])
        with col_s1:
            available_months = sorted(df_all["年月"].unique(), reverse=True)
            selected_month = st.selectbox("表示する月を選択", available_months, key="select_month_tab2")
        with col_s2:
            st.write("🎯 **月別予算の設定**")
            
        budget_options = [0, 5000, 10000, 20000, 30000, 40000, 50000, 70000, 100000, 150000]
        budgets = {}
        b_cols = st.columns(5)
        cat_list = ["食費", "外食", "日用品", "ペット", "医療費"]
        for i, cat in enumerate(cat_list):
            with b_cols[i]:
                default_idx = 3 if cat == "食費" else 0
                budgets[cat] = st.selectbox(f"{cat}", budget_options, index=default_idx, key=f"budget_tab2_{cat}")
        
        df_month = df_all[df_all["年月"] == selected_month].copy()
        df_month["日付"] = df_month["日付"].dt.strftime("%Y-%m-%d")

        st.divider()

        # レポートサマリー
        st.header(f"📊 {selected_month} の支出レポート")
        total_expense = df_month["金額"].sum()
        st.metric("今月の総支出", f"{total_expense:,} 円")
        
        # 予算超過アラートのチェック
        expense_summary = df_month.groupby("カテゴリ")["金額"].sum()
        for cat, budget_val in budgets.items():
            if budget_val > 0:
                spent = expense_summary.get(cat, 0)
                if spent > budget_val:
                    st.warning(f"⚠️ **【予算超過アラート】** {cat} の今月の支出（{spent:,}円）が、設定予算（{budget_val:,}円）を超えています！")

        # --- データ編集・削除エリア ---
        st.subheader("📝 履歴の確認・編集")
        st.caption("※表の中をダブルクリックして値を直接変更できます。行の左端にチェックを入れて『選択行を削除』を押すと削除できます。")

        display_cols = ["日付", "カテゴリ", "金額", "購入場所", "現金", "カード", "金券", "電子マネー", "メモ"]
        edited_df_month = st.data_editor(
            df_month[display_cols],
            use_container_width=True,
            num_rows="dynamic",
            key=f"data_editor_{selected_month}"
        )

        if st.button("変更を確定して保存する", type="primary", key="save_btn"):
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
                mime="text/csv",
                key="csv_dl_btn"
            )
        with col_dl2:
            if st.button("🖨️ この月のレポートを印刷 / PDF保存", key="print_btn"):
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
        st.info("データがまだありません。「📝 支出の入力」タブから入力してください。")
