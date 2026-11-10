import datetime
import hmac
from pathlib import Path
 
import altair as alt
import pandas as pd
import streamlit as st
import streamlit.components.v1 as components

import json 
 
st.set_page_config(page_title="手軽な家計簿アプリ", page_icon="💰")
 
# ==========================================
# 設定
# ==========================================
# ローカル実行用のCSV（Googleスプレッドシートを設定していない場合だけ使います）
DATA_FILE = Path(__file__).parent / "kakeibo.csv"
MEMBERS_FILE = Path(__file__).parent / "members.csv"
 
# スプレッドシート内のシート名
DATA_SHEET = "家計簿"
MEMBERS_SHEET = "入力者"
 
COLUMNS = ["日付", "カテゴリ", "店名", "金額", "カード利用額", "入力者", "購入場所", "メモ"]
MEMBER_COLUMNS = ["名前"]
NUM_COLS = ["金額", "カード利用額"]
TEXT_COLS = ["カテゴリ", "店名", "入力者", "購入場所", "メモ"]
 
CATEGORIES = [
    "食費", "外食", "ペット", "日用品", "医療費",
    "スマホ代", "ネット・通信", "交通費", "光熱費", "その他",
]
BUDGET_CATEGORIES = ["食費", "外食", "日用品", "ペット", "医療費"]
BUDGET_OPTIONS = [0, 5000, 10000, 20000, 30000, 40000, 50000, 70000, 100000, 150000]
 
 
# ==========================================
# パスワード（任意）
#   Secrets に APP_PASSWORD を設定したときだけ、入力を求めます。
# ==========================================
MAX_FAILS = 10        # この回数を超えて間違えると、しばらく入力できなくなる
WINDOW_SEC = 600      # 上の回数を数える期間（秒）
 
 
@st.cache_resource
def _login_failures():
    return []         # 失敗した時刻のリスト（アプリを開いている全員で共有）
 
 
def check_password():
    try:
        password = st.secrets.get("APP_PASSWORD")
    except Exception:
        password = None
 
    if not password:
        # スプレッドシートにつないでいるのにパスワードが無い＝設定漏れ。表示しない。
        if use_sheets():
            st.error("パスワード（APP_PASSWORD）が設定されていないため、表示できません。Secrets に設定してください。")
            return False
        return True                       # ローカルのCSV実行では、パスワードなしで使える
    if st.session_state.get("authed"):
        return True
 
    now = datetime.datetime.now().timestamp()
    fails = _login_failures()
    fails[:] = [t for t in fails if now - t < WINDOW_SEC]
    if len(fails) >= MAX_FAILS:
        st.error("パスワードの入力失敗が続いたため、しばらく入力できません。10分ほど待ってからお試しください。")
        return False
 
    entered = st.text_input("パスワード", type="password")
    if entered:
        if hmac.compare_digest(entered.encode("utf-8"), str(password).encode("utf-8")):
            st.session_state["authed"] = True
            st.rerun()
        else:
            fails.append(now)
            st.error("パスワードが違います。")
    return False
 
 
# ==========================================
# データの整形（保存先に関係なく共通）
# ==========================================
def normalize(df):
    """列・型をそろえる。旧形式（現金/カード/金券/電子マネー列あり）のCSVも新形式に変換する。"""
    df = df.copy()
    if "カード" in df.columns and "カード利用額" not in df.columns:
        df = df.rename(columns={"カード": "カード利用額"})
    for c in COLUMNS:
        if c not in df.columns:
            df[c] = "" if c in TEXT_COLS else 0
    df = df[COLUMNS].copy()
    df["日付"] = pd.to_datetime(df["日付"], errors="coerce", format="mixed")
    df = df.dropna(subset=["日付"])          # 日付が不正な行は除く
    for c in NUM_COLS:
        df[c] = pd.to_numeric(df[c], errors="coerce").fillna(0).astype(int)
    for c in TEXT_COLS:
        df[c] = df[c].fillna("").astype(str)
    return df.reset_index(drop=True)
 
 
def add_year_month(df):
    df = df.copy()
    df["年月"] = df["日付"].dt.strftime("%Y年%m月")
    return df
 
 
def rows_to_df(values, headers):
    """シートの値（文字列の2次元リスト・1行目は見出し）をDataFrameにする。列数が不ぞろいでも崩れない。"""
    if not values:
        return pd.DataFrame(columns=headers)
    header = [str(h).strip() for h in values[0]]
    body = [(list(r) + [""] * len(header))[: len(header)] for r in values[1:]]
    return pd.DataFrame(body, columns=header)
 
 
def df_to_rows(df, headers):
    """DataFrameを、シートに書き込める2次元リスト（1行目は見出し）にする。"""
    d = df.reindex(columns=headers)
    d = d.astype(object).where(d.notna(), "")
    return [list(headers)] + d.values.tolist()
 
 
def ensure_header(ws, headers):
    """シートの1行目が headers と違えば、列をそろえて書き直す（初回作成や、列を増やしたあとの移行用）。"""
    values = ws.get_all_values()
    if not values:
        ws.update(range_name="A1", values=[list(headers)])
        return
    if [str(h).strip() for h in values[0]] != list(headers):
        df = rows_to_df(values, headers)
        ws.clear()
        ws.update(range_name="A1", values=df_to_rows(df, headers))
 
 
def to_csv_bytes(df):
    """Excelで文字化けしないCSV（BOM付きUTF-8）のバイト列にする。"""
    out = df.copy()
    if "日付" in out.columns and pd.api.types.is_datetime64_any_dtype(out["日付"]):
        out["日付"] = out["日付"].dt.strftime("%Y-%m-%d")
    return ("\ufeff" + out.to_csv(index=False)).encode("utf-8")
 
 
# ==========================================
# 保存先（Googleスプレッドシート / ローカルCSV）
#   Secrets に gcp_service_account と SPREADSHEET_ID があればスプレッドシート、
#   なければローカルCSVを使います。
# ==========================================

def use_sheets():
    try:
        # Secretsの中に "gspread" と "SPREADSHEET_ID" が両方あればスプレッドシートを使用
        return "gspread" in st.secrets and "SPREADSHEET_ID" in st.secrets
    except Exception:
        return False


@st.cache_resource
def get_spreadsheet():
    import gspread

    # 1. 埋め込んだJSON文字列をPythonの辞書型に変換
    secret_credentials = json.loads(st.secrets["gspread"]["json_secrets"])

    # 2. 辞書型データを使って認証
    gc = gspread.service_account_from_dict(secret_credentials)

    # 3. 指定されたIDのスプレッドシートを開く
    return gc.open_by_key(st.secrets["SPREADSHEET_ID"])
 
 
@st.cache_resource
def get_worksheet(name, headers):
    import gspread
 
    sh = get_spreadsheet()
    try:
        ws = sh.worksheet(name)
    except gspread.WorksheetNotFound:
        ws = sh.add_worksheet(title=name, rows=1000, cols=max(10, len(headers)))
    ensure_header(ws, list(headers))
    return ws
 
 
def _read(name, path, headers):
    """保存先から、文字列のDataFrameとして読む"""
    if use_sheets():
        return rows_to_df(get_worksheet(name, tuple(headers)).get_all_values(), headers)
    if not Path(path).exists():
        return pd.DataFrame(columns=headers)
    for enc in ("utf_8_sig", "utf-8"):
        try:
            return pd.read_csv(path, encoding=enc, dtype=str, keep_default_na=False)
        except UnicodeDecodeError:
            continue
        except pd.errors.EmptyDataError:
            break
    return pd.DataFrame(columns=headers)
 
 
def _write(name, path, headers, df):
    """保存先の内容を、dfで全部置き換える"""
    if use_sheets():
        ws = get_worksheet(name, tuple(headers))
        ws.clear()
        ws.update(range_name="A1", values=df_to_rows(df, headers))
    else:
        df.reindex(columns=headers).to_csv(path, index=False, encoding="utf_8_sig")
 
 
@st.cache_data(ttl=20, show_spinner=False)
def load_data():
    return normalize(_read(DATA_SHEET, DATA_FILE, COLUMNS))
 
 
def read_fresh():
    """キャッシュを使わず、保存先から最新を読む（保存の直前に使う）"""
    return normalize(_read(DATA_SHEET, DATA_FILE, COLUMNS))
 
 
def save_data(df):
    out = df[COLUMNS].copy()
    out["日付"] = pd.to_datetime(out["日付"]).dt.strftime("%Y-%m-%d")
    _write(DATA_SHEET, DATA_FILE, COLUMNS, out)
    st.cache_data.clear()
 
 
def append_record(record):
    """1件だけ追加する（ほかの人が同時に入力しても、上書きで消えにくい）"""
    if use_sheets():
        ws = get_worksheet(DATA_SHEET, tuple(COLUMNS))
        ws.append_row([record[c] for c in COLUMNS], value_input_option="RAW")
    else:
        df = read_fresh()
        df["日付"] = df["日付"].dt.strftime("%Y-%m-%d")
        df = pd.concat([df, pd.DataFrame([record])], ignore_index=True)
        _write(DATA_SHEET, DATA_FILE, COLUMNS, df)
    st.cache_data.clear()
 
 
@st.cache_data(ttl=20, show_spinner=False)
def load_members():
    df = _read(MEMBERS_SHEET, MEMBERS_FILE, MEMBER_COLUMNS)
    names = [str(n).strip() for n in df["名前"] if str(n).strip()]
    return list(dict.fromkeys(names))          # 重複を除き、順番は保つ
 
 
def save_members(names):
    _write(MEMBERS_SHEET, MEMBERS_FILE, MEMBER_COLUMNS, pd.DataFrame({"名前": names}))
    st.cache_data.clear()
 
 
# ==========================================
# 補助関数
# ==========================================
def pie_chart(series, label):
    data = series[series > 0].reset_index()
    data.columns = [label, "金額"]
    return alt.Chart(data).mark_arc().encode(
        theta=alt.Theta("金額:Q"),
        color=alt.Color(f"{label}:N"),
        tooltip=[label, "金額"],
    )
 
 
def bar_chart(series, label):
    data = series.reset_index()
    data.columns = [label, "金額"]
    return alt.Chart(data).mark_bar().encode(
        x=alt.X(f"{label}:N", sort="-y"),
        y=alt.Y("金額:Q"),
        tooltip=[label, "金額"],
    )
 
 
def build_summary(month, dfm):
    """LINEなどに送る、月のまとめ文章を作る"""
    total = int(dfm["金額"].sum())
    card = int(dfm["カード利用額"].sum())
    lines = [
        f"【{month} 家計簿まとめ】",
        f"総支出: {total:,}円",
        f"うちカード利用額: {card:,}円（翌月引き落としの目安）",
    ]
 
    def top(col, n=5):
        return dfm[dfm[col] != ""].groupby(col)["金額"].sum().sort_values(ascending=False).head(n)
 
    cat = dfm.groupby("カテゴリ")["金額"].sum().sort_values(ascending=False).head(5)
    for title, s in (("カテゴリ別（上位5）", cat), ("お店別（上位5）", top("店名")), ("支払い区分別", top("入力者", 10))):
        if not s.empty:
            lines.append("")
            lines.append(f"■{title}")
            lines += [f"・{k}: {int(v):,}円" for k, v in s.items()]
    return "\n".join(lines)
 
 
def send_line(text):
    """LINE送信（別プログラムで作成予定）。ここに送信処理をつなぎます。
 
    例：MakeのWebhookにPOSTする場合（URLはGitHubに書かず、Secretsに置いてください）
        import requests
        url = st.secrets["MAKE_WEBHOOK_URL"]
        r = requests.post(url, json={"to": "group", "text": text}, timeout=10)
        return r.ok, f"ステータスコード: {r.status_code}"
    """
    return False, "LINE送信はまだ接続されていません（send_line 関数に送信処理を追加してください）。"
 
 
# ==========================================
# 画面
# ==========================================
st.title("手軽な家計簿アプリ")
 
if not check_password():
    st.stop()
 
if use_sheets():
    st.caption("💾 保存先：Googleスプレッドシート")
else:
    st.caption("💾 保存先：このアプリ内のCSV（公開環境では再起動で消えます。スプレッドシートの設定をしてください）")
 
tab1, tab2, tab3 = st.tabs(["📝 支出の入力", "📊 レポート・履歴・印刷", "🔍 分析"])
 
# ==========================================
# タブ1：支出の入力
# ==========================================
with tab1:
    st.header("支出の入力")
 
    existing = load_data()
    members = load_members()
    past_stores = sorted({s for s in existing["店名"] if s})
 
    date = st.date_input("日付", datetime.date.today(), key="input_date")
    category = st.selectbox("カテゴリ", CATEGORIES, key="input_category")
 
    with st.form(key="kakeibo_form", clear_on_submit=True):
        person = None
        if members:
            last = st.session_state.get("last_person")
            idx = members.index(last) if last in members else None
            person = st.selectbox("支払い区分", members, index=idx, placeholder="選んでください")
        else:
            st.info("支払い区分が未登録です。「🔍 分析」タブの「支払い区分の登録」から登録できます。")
 
        purchase_place = st.radio("購入場所", ["実店舗", "ネット販売"], horizontal=True)
 
        picked_store = st.selectbox("お店の名前（過去に使ったお店から選ぶ・任意）", [""] + past_stores)
        new_store = st.text_input("お店の名前（新しいお店や、選ばない場合はこちらに入力）")
 
        total_price = 0
        if category == "外食":
            st.markdown("---")
            st.markdown("🍽️ **【株主優待の利用】**")
            total_price = st.number_input(
                "支払総額（メニューの合計金額・定価。優待を使わない場合は0）",
                min_value=0, step=100, value=0,
            )
 
        st.markdown("---")
        amount = st.number_input("金額（円）※実際に支払った額", min_value=0, step=100, value=0)
        card_amount = st.number_input(
            "うちクレジットカード利用額（円）※カード払いがなければ0",
            min_value=0, step=100, value=0,
        )
        user_memo = st.text_input("メモ（自由記入）")
        submit_button = st.form_submit_button(label="記録する")
 
    if submit_button:
        store = new_store.strip() or picked_store
        if members and not person:
            st.warning("支払い区分を選んでください。")
        elif amount == 0:
            st.warning("金額が0円です。金額を入力してください。")
        elif card_amount > amount:
            st.error("カード利用額が金額を超えています。入力を確認してください。")
        else:
            memo_parts = []
            if category == "外食" and total_price > amount:
                memo_parts.append(f"【総額:{total_price:,}円 / 優待利用:{total_price - amount:,}円】")
            if user_memo.strip():
                memo_parts.append(user_memo.strip())
 
            # 同じ内容の記録がすでにあれば、あとで知らせる（重複入力の防止）
            is_dup = bool(
                (
                    (existing["日付"] == pd.Timestamp(date))
                    & (existing["カテゴリ"] == category)
                    & (existing["店名"] == store)
                    & (existing["金額"] == amount)
                ).any()
            )
 
            append_record({
                "日付": date.strftime("%Y-%m-%d"),
                "カテゴリ": category,
                "店名": store,
                "金額": int(amount),
                "カード利用額": int(card_amount),
                "入力者": person or "",
                "購入場所": purchase_place,
                "メモ": " ".join(memo_parts),
            })
            if person:
                st.session_state["last_person"] = person
            st.success("記録しました！「📊 レポート・履歴・印刷」タブから内容を確認できます。")
            if is_dup:
                st.warning(
                    "⚠️ 同じ日付・カテゴリ・店名・金額の記録が、すでにあります。"
                    "重複でないか確認してください（レポートタブで削除できます）。"
                )
 
# ==========================================
# タブ2：レポート・履歴・印刷
# ==========================================
with tab2:
    df_all = load_data()
    if df_all.empty:
        st.info("データがまだありません。「📝 支出の入力」タブから入力してください。")
    else:
        df_all = add_year_month(df_all)
 
        st.subheader("⚙️ 表示月・予算の設定")
        available_months = sorted(df_all["年月"].unique(), reverse=True)
        selected_month = st.selectbox("表示する月を選択", available_months, key="select_month_tab2")
 
        st.write("🎯 **月別予算の設定**")
        budgets = {}
        b_cols = st.columns(5)
        for i, cat in enumerate(BUDGET_CATEGORIES):
            with b_cols[i]:
                default_idx = 3 if cat == "食費" else 0
                budgets[cat] = st.selectbox(cat, BUDGET_OPTIONS, index=default_idx, key=f"budget_tab2_{cat}")
 
        df_month = df_all[df_all["年月"] == selected_month].copy()
 
        st.divider()
 
        # --- レポートサマリー ---
        st.header(f"📊 {selected_month} の支出レポート")
        m1, m2 = st.columns(2)
        m1.metric("今月の総支出", f"{int(df_month['金額'].sum()):,} 円")
        m2.metric("うちカード利用額", f"{int(df_month['カード利用額'].sum()):,} 円")
 
        expense_summary = df_month.groupby("カテゴリ")["金額"].sum()
        for cat, budget_val in budgets.items():
            if budget_val > 0:
                spent = int(expense_summary.get(cat, 0))
                if spent > budget_val:
                    st.warning(
                        f"⚠️ **【予算超過アラート】** {cat} の今月の支出（{spent:,}円）が、"
                        f"設定予算（{budget_val:,}円）を超えています！"
                    )
 
        # --- 履歴の確認・編集・削除 ---
        st.subheader("📝 履歴の確認・編集")
        st.caption(
            "※値はダブルクリックで直接変更できます。削除は「削除」列にチェックを入れて、"
            "「変更を確定して保存する」を押してください。"
        )
 
        view = df_month[COLUMNS].copy()
        view["日付"] = view["日付"].dt.strftime("%Y-%m-%d")
        view.insert(0, "削除", False)
 
        editor_ver = st.session_state.get("editor_ver", 0)
        edited = st.data_editor(
    view,
    num_rows="fixed",          # 行の追加は「支出の入力」タブで行います
    column_config={"入力者": st.column_config.TextColumn(label="支払い区分")},
    key=f"data_editor_{selected_month}_{editor_ver}",
)
 
        if st.button("変更を確定して保存する", type="primary", key="save_btn"):
            keep = edited[~edited["削除"].fillna(False).astype(bool)].drop(columns="削除")
            keep = normalize(keep)                                  # 型をそろえる
            fresh = add_year_month(read_fresh())                    # 保存の直前に最新を読む
            other = fresh[fresh["年月"] != selected_month][COLUMNS]  # 他の月はそのまま
            save_data(pd.concat([other, keep], ignore_index=True))
            st.session_state["editor_ver"] = editor_ver + 1         # 編集状態をリセット
            st.success("データを更新しました！")
            st.rerun()
 
        # --- エクスポート & 印刷 ---
        st.divider()
        col_dl1, col_dl2 = st.columns(2)
        with col_dl1:
            st.download_button(
                label=f"📥 {selected_month} のデータをCSVダウンロード",
                data=to_csv_bytes(df_month[COLUMNS]),
                file_name=f"kakeibo_{selected_month.replace('年', '_').replace('月', '')}.csv",
                mime="text/csv",
                key="csv_dl_btn",
            )
        with col_dl2:
            if st.button("🖨️ この月のレポートを印刷 / PDF保存", key="print_btn"):
                components.html("<script>window.parent.print();</script>", height=0)
                st.info("ブラウザの印刷ダイアログが開きます。「PDFに保存」を選択するとPDF化できます。")
 
        # --- カテゴリ別内訳 ---
        st.subheader(f"📊 {selected_month} カテゴリ別支出内訳")
        col1, col2 = st.columns(2)
        with col1:
            if expense_summary.sum() > 0:
                st.dataframe(expense_summary)
            else:
                st.info("今月の支出データはありません。")
        with col2:
            if expense_summary.sum() > 0:
                st.altair_chart(pie_chart(expense_summary, "カテゴリ"))
            else:
                st.info("円グラフを表示するデータがありません。")
 
# ==========================================
# タブ3：分析
# ==========================================
with tab3:
    # --- 入力者の登録（データが空でも使えるよう、一番上に置く）---
    with st.expander("👥 支払い区分の登録・管理"):
        st.caption("入力画面で選べる名前を登録します。1行に1つずつ入力してください。")
        members_now = load_members()
        names_text = st.text_area("支払い区分", "\n".join(members_now), height=120)
        if st.button("支払い区分を保存", key="save_members"):
            names = list(dict.fromkeys(n.strip() for n in names_text.splitlines() if n.strip()))
            save_members(names)
            st.success(f"{len(names)}件を登録しました。")
            st.rerun()
 
    df_all = load_data()
    if df_all.empty:
        st.info("データがまだありません。「📝 支出の入力」タブから入力してください。")
    else:
        df_all = add_year_month(df_all)
        months = sorted(df_all["年月"].unique(), reverse=True)
        sel = st.selectbox("分析する月", months, key="analysis_month")
        dfm = df_all[df_all["年月"] == sel]
 
        # --- クレジットカード ---
        st.subheader("💳 クレジットカード利用額")
        card_total = int(dfm["カード利用額"].sum())
        st.metric(f"{sel} のカード利用額（翌月引き落としの目安）", f"{card_total:,} 円")
        st.caption("※実際の引き落とし月は、カードの締め日・支払日によって変わります。")
        card_df = dfm[dfm["カード利用額"] > 0][["日付", "店名", "入力者", "カテゴリ", "カード利用額"]].sort_values("日付")
        with st.expander(f"カード払いの明細（{len(card_df)}件）"):
            card_view = card_df.copy()
            card_view["日付"] = card_view["日付"].dt.strftime("%Y-%m-%d")
            st.dataframe(card_view.rename(columns={"入力者": "支払い区分"}), hide_index=True)
 
        # --- 入力者別 ---
        # --- 支払い区分別 ---
        st.subheader("👤 支払い区分別の支出")
        person_sum = dfm[dfm["入力者"] != ""].groupby("入力者")["金額"].sum().sort_values(ascending=False)
        if person_sum.empty:
            st.info("支払い区分が入力された記録が、この月にはまだありません。")
        else:
            st.dataframe(person_sum.rename_axis("支払い区分"))
        
 
        # --- お店別 ---
        st.subheader("🏪 お店別の支出")
        scope = st.radio("集計期間", ["選択した月", "全期間"], horizontal=True, key="store_scope")
        target = dfm if scope == "選択した月" else df_all
        with_store = target[target["店名"] != ""]
        missing = len(target) - len(with_store)
        if missing:
            st.caption(f"※お店の名前が未入力の記録が {missing} 件あります（集計には含まれません）。")
 
        store_sum = None
        if with_store.empty:
            st.info("お店の名前が入力された記録がまだありません。")
        else:
            store_sum = (
                with_store.groupby("店名")
                .agg(合計金額=("金額", "sum"), 回数=("金額", "size"))
                .sort_values("合計金額", ascending=False)
            )
            st.dataframe(store_sum)
            st.altair_chart(bar_chart(store_sum["合計金額"].head(10), "店名"))
 
            pick = st.selectbox("お店を選んで明細を見る", list(store_sum.index), key="store_pick")
            detail = (
                with_store[with_store["店名"] == pick][["日付", "カテゴリ", "金額", "カード利用額", "入力者", "メモ"]]
                .sort_values("日付", ascending=False)
            )
            detail["日付"] = detail["日付"].dt.strftime("%Y-%m-%d")
            st.dataframe(detail.rename(columns={"入力者": "支払い区分"}), hide_index=True)
 
        # --- CSVエクスポート ---
        st.subheader("📥 CSVエクスポート")
        ym_key = sel.replace("年", "_").replace("月", "")
        e1, e2, e3 = st.columns(3)
        with e1:
            st.download_button(
                f"{sel} の明細",
                data=to_csv_bytes(dfm[COLUMNS]),
                file_name=f"kakeibo_{ym_key}.csv",
                mime="text/csv",
                key="export_month",
            )
        with e2:
            st.download_button(
                "全期間の明細",
                data=to_csv_bytes(df_all[COLUMNS]),
                file_name="kakeibo_all.csv",
                mime="text/csv",
                key="export_all",
            )
        with e3:
            if store_sum is not None:
                label = "お店別の集計（選択した月）" if scope == "選択した月" else "お店別の集計（全期間）"
                st.download_button(
                    label,
                    data=to_csv_bytes(store_sum.reset_index()),
                    file_name="kakeibo_store_summary.csv",
                    mime="text/csv",
                    key="export_store",
                )
 
        # --- LINE送信 ---
        st.subheader("📨 LINEで送る")
        text = st.text_area("送信する内容（編集できます）", build_summary(sel, dfm), height=260)
        if st.button("LINEに送信", key="line_send"):
            ok, info = send_line(text)
            if ok:
                st.success(info)
            else:
                st.warning(info)
