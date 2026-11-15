"""
Список акций NASDAQ для вкладки «Акции» сайта 17R Screener (14.11.2026, фильтры владельца).

Отбор: только обычные акции компаний (тип CS — без ETF, фондов, ETN, варрантов), биржа NASDAQ,
средний объём за 20 дней ≥ 300 000 акций, цена закрытия $5–200, ATR(14) ≥ $0.50.
Данные: Polygon (Massive) — справочник тикеров и дневные свечи всего рынка (grouped daily), бесплатный тариф
(5 запросов в минуту, данные конца дня). Ключ — переменная окружения POLYGON_KEY (секрет GitHub), в код не пишется.
Результат: stocks.json рядом со страницей — сайт читает его сам.

Запуск: POLYGON_KEY=... python stocks_list.py [путь/stocks.json]
"""
import datetime as dt
import json
import os
import sys
import time
import urllib.parse
import urllib.request

BASE = os.environ.get("POLYGON_BASE", "https://api.polygon.io")
KEY = os.environ.get("POLYGON_KEY", "")
PAUSE = float(os.environ.get("POLYGON_PAUSE", "12.5"))      # бесплатный тариф: 5 запросов в минуту
MIN_VOL, MIN_PRICE, MAX_PRICE, MIN_ATR = 300_000, 5.0, 200.0, 0.5
DAYS_VOL, DAYS_ATR = 20, 14


def get(url):
    """GET с ключом; при 429 (лимит) — подождать и повторить."""
    sep = "&" if "?" in url else "?"
    full = url + sep + "apiKey=" + urllib.parse.quote(KEY)
    for attempt in range(5):
        try:
            with urllib.request.urlopen(urllib.request.Request(full, headers={"User-Agent": "17r-screener"}), timeout=60) as r:
                data = json.load(r)
            time.sleep(PAUSE)
            return data
        except urllib.error.HTTPError as e:
            if e.code == 429:
                time.sleep(60)
                continue
            raise
    raise RuntimeError("лимит запросов не отпускает")


def nasdaq_common():
    """{тикер: название} — активные обычные акции NASDAQ."""
    out, url = {}, f"{BASE}/v3/reference/tickers?market=stocks&exchange=XNAS&type=CS&active=true&limit=1000"
    while url:
        d = get(url)
        for t in d.get("results", []):
            out[t["ticker"]] = t.get("name", "")
        url = d.get("next_url")
    return out


def daily_bars(need):
    """{дата: {тикер: (o, h, l, c, v)}} за последние need торговых дней (выходные и праздники пропускаются)."""
    days, day = {}, dt.date.today()
    for _ in range(need * 2 + 10):
        day -= dt.timedelta(days=1)
        if day.weekday() >= 5:
            continue
        d = get(f"{BASE}/v2/aggs/grouped/locale/us/market/stocks/{day.isoformat()}?adjusted=true")
        res = d.get("results") or []
        if res:
            days[day.isoformat()] = {r["T"]: (r["o"], r["h"], r["l"], r["c"], r["v"]) for r in res}
        if len(days) >= need:
            break
    return days


def pick(names, days):
    dates = sorted(days)
    rows = []
    for t, name in names.items():
        bars = [days[d][t] for d in dates if t in days[d]]
        if len(bars) < DAYS_ATR + 1:
            continue
        c = bars[-1][3]
        vol = sum(b[4] for b in bars[-DAYS_VOL:]) / len(bars[-DAYS_VOL:])
        trs = [max(b[1] - b[2], abs(b[1] - p[3]), abs(b[2] - p[3])) for p, b in zip(bars[:-1], bars[1:])][-DAYS_ATR:]
        atr = sum(trs) / len(trs)
        if vol < MIN_VOL or not (MIN_PRICE <= c <= MAX_PRICE) or atr < MIN_ATR:
            continue
        ch = (c / bars[-2][3] - 1) * 100 if bars[-2][3] else 0.0
        rows.append({"t": t, "n": name, "p": round(c, 4), "ch": round(ch, 2), "v": round(vol),
                     "atr": round(atr, 3), "atrp": round(atr / c * 100, 2)})
    rows.sort(key=lambda r: -r["v"])
    return rows, dates[-1] if dates else None


def main():
    if not KEY:
        sys.exit("нет ключа POLYGON_KEY")
    out = sys.argv[1] if len(sys.argv) > 1 else "stocks.json"
    names = nasdaq_common()
    days = daily_bars(DAYS_VOL + 1)
    rows, last = pick(names, days)
    data = {"updated": dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"), "date": last,
            "filter": {"exchange": "NASDAQ", "min_vol": MIN_VOL, "price": [MIN_PRICE, MAX_PRICE], "min_atr": MIN_ATR},
            "n": len(rows), "rows": rows}
    with open(out, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, separators=(",", ":"))
    print(f"акций NASDAQ всего {len(names)}, прошли фильтр {len(rows)}, данные за {last}")


if __name__ == "__main__":
    main()