import json
import os
from datetime import date, datetime
from zoneinfo import ZoneInfo

import gspread
import pandas as pd
import requests

WITH_DETAIL = False  # True にすると、明細（日付・店名・金額）も付ける


def shift_month(y, m, delta):
    idx = y * 12 + (m - 1) + delta
    return idx // 12, idx % 12 + 1


today = datetime.now(ZoneInfo("Asia/Tokyo")).date()
sy, sm = shift_month(today.year, today.month, -2)
ey, em = shift_month(today.year, today.month, -1)
start = date(sy, sm, 16)   # 先々月16日
end = date(ey, em, 15)     # 前月15日

creds = json.loads(os.environ["GSPREAD_JSON"])
gc = gspread.service_account_from_dict(creds)
ws = gc.open_by_key(os.environ["SPREADSHEET_ID"]).worksheet("家計簿")
values = ws.get_all_values()

header = [h.strip() for h in values[0]]
df = pd.DataFrame([(r + [""] * len(header))[: len(header)] for r in values[1:]], columns=header)
df["日付"] = pd.to_datetime(df["日付"], errors="coerce", format="mixed")
df["カード利用額"] = pd.to_numeric(df["カード利用額"], errors="coerce").fillna(0).astype(int)
df = df.dropna(subset=["日付"])

d = df["日付"].dt.date
target = df[(d >= start) & (d <= end) & (df["カード利用額"] > 0)].sort_values("日付")

total = int(target["カード利用額"].sum())
period = f"{start.month}/{start.day}〜{end.month}/{end.day}"
lines = [
    "【クレジットカード利用額】",
    f"対象期間: {period}",
    f"合計: {total:,}円（{len(target)}件）",
]
if WITH_DETAIL and len(target) > 0:
    lines += ["", "■明細"]
    for _, r in target.iterrows():
        store = r["店名"] or "（店名なし）"
        lines.append(f"・{r['日付'].strftime('%m/%d')} {store} {int(r['カード利用額']):,}円")

r = requests.post(os.environ["MAKE_WEBHOOK_URL"], json={"text": "\n".join(lines)}, timeout=30)
r.raise_for_status()
print("送信しました:", period, total)
