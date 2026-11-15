"""
Живые цены акций для вкладки «Акции» (15.11.2026): раз в 15 минут во время торгов берёт у Alpaca снимки
(snapshots, бесплатный поток IEX) по акциям из stocks.json и пишет stocks_live.json:
цена сейчас, открытие дня, «пройдено ATR» от открытия (книжный ATR из stocks.json — как у крипты).
IEX — одна биржа: цены близки к общим, объём занижен, поэтому объём сегодня не показываем.
Ключи — переменные окружения ALPACA_KEY_ID и ALPACA_SECRET (секреты GitHub), в код не пишутся.

Запуск: ALPACA_KEY_ID=... ALPACA_SECRET=... python stocks_live.py [stocks.json] [stocks_live.json]
"""
import datetime as dt
import json
import os
import sys
import time
import urllib.parse
import urllib.request
from zoneinfo import ZoneInfo

BASE = os.environ.get("ALPACA_BASE", "https://data.alpaca.markets")
KID, SEC = os.environ.get("ALPACA_KEY_ID", ""), os.environ.get("ALPACA_SECRET", "")
BATCH = 100


NY = ZoneInfo("America/New_York")


def get(url):
    req = urllib.request.Request(url, headers={"APCA-API-KEY-ID": KID, "APCA-API-SECRET-KEY": SEC,
                                               "User-Agent": "17r-screener"})
    for attempt in range(4):
        try:
            with urllib.request.urlopen(req, timeout=60) as r:
                return json.load(r)
        except urllib.error.HTTPError as e:
            if e.code == 429:
                time.sleep(30)
                continue
            raise
    raise RuntimeError("лимит запросов Alpaca")


def snapshots(symbols):
    return get(f"{BASE}/v2/stocks/snapshots?feed=iex&symbols=" + urllib.parse.quote(",".join(symbols)))


def session_open(symbols, start):
    """{тикер: открытие основной сессии} — open первой 30м свечи с 9:30 по Нью-Йорку (без пре-маркета)."""
    out, token = {}, ""
    while True:
        url = (f"{BASE}/v2/stocks/bars?feed=iex&timeframe=30Min&limit=10000&start={urllib.parse.quote(start)}"
               f"&symbols=" + urllib.parse.quote(",".join(symbols)) + (f"&page_token={token}" if token else ""))
        d = get(url)
        for t, bars in (d.get("bars") or {}).items():
            if bars and t not in out:
                out[t] = bars[0]["o"]
        token = d.get("next_page_token")
        if not token:
            return out


def main():
    if not KID or not SEC:
        sys.exit("нет ключей ALPACA_KEY_ID / ALPACA_SECRET")
    src = sys.argv[1] if len(sys.argv) > 1 else "stocks.json"
    out = sys.argv[2] if len(sys.argv) > 2 else "stocks_live.json"
    with open(src, encoding="utf-8") as f:
        rows = json.load(f)["rows"]
    batr = {r["t"]: r.get("batr") or r["atr"] for r in rows}
    now = dt.datetime.now(NY)
    today, opened = now.date(), now.replace(hour=9, minute=30, second=0, microsecond=0)
    q, tickers = {}, [r["t"] for r in rows]
    if now >= opened and now.weekday() < 5:                       # до 9:30 по Нью-Йорку — сессии ещё нет
        start = opened.astimezone(dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
        for i in range(0, len(tickers), BATCH):
            part = tickers[i:i + BATCH]
            opens, snap = session_open(part, start), snapshots(part)
            for t, s in (snap or {}).items():
                o = opens.get(t)
                px = ((s or {}).get("latestTrade") or {}).get("p")
                if not o or not px:
                    continue
                a = batr.get(t)
                q[t] = [round(px, 4), round(o, 4), round((px - o) / a * 100, 1) if a else None]
    data = {"updated": dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"), "day": today.isoformat(),
            "session": "open" if q else "closed", "feed": "iex", "n": len(q), "q": q}
    with open(out, "w", encoding="utf-8") as f:
        json.dump(data, f, separators=(",", ":"))
    print(f"акций в списке {len(tickers)}, с ценой сегодня {len(q)}")


if __name__ == "__main__":
    main()