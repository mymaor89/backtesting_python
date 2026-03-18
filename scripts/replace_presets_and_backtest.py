"""
Replace all existing presets with the finalized set and run a backtest for each.
Run from project root: python scripts/replace_presets_and_backtest.py
"""

import json
import sys
import requests

API = "http://localhost:8000"

PRESETS = [
    {
        "name": "Market Golden Cross",
        "tag": "Trend",
        "category": "Trend Following",
        "description": "Classic SMA crossover: enter when SMA-50 > SMA-200. Exit when price breaks below SMA-50.",
        "explanation": "אסטרטגיה זו מתאימה למדד החברות הגדולות כיוון שהוא נוטה לייצר מגמות עלייה ארוכות טווח לאורך שנים. היא מאפשרת לתפוס את רוב מהלכי העלייה הממושכים ולצאת באופן אוטומטי במקרים של התרסקות שוק עמוקה.",
        "state": {
            "symbol": "SPY",
            "exchange": "yfinance",
            "freq": "1D",
            "base_balance": 10000,
            "comission": 0.001,
            "start": "2020-01-01",
            "stop": "2026-03-18",
            "datapoints": [
                {"name": "sma_50", "transformer": "sma", "args": [50]},
                {"name": "sma_200", "transformer": "sma", "args": [200]},
            ],
            "enter": [["sma_50", ">", "sma_200"]],
            "exit": [["close", "<", "sma_50"]],
        },
    },
    {
        "name": "Oil Trend Ride",
        "tag": "Trend",
        "category": "Trend Following",
        "description": "Ride crude oil trends using EMA-20 and SMA-200 as filters. Enter when fast crosses slow.",
        "explanation": "נפט מושפע מאוד מאירועי כלכלה עולמית והיצע וביקוש מה שיוצר מגמות חזקות וארוכות שאינן נעצרות מיד. שימוש במדדים עוקבי מגמה מתאים בדיוק לאופי המגמתי של סחורה זו.",
        "state": {
            "symbol": "USO",
            "exchange": "yfinance",
            "freq": "1D",
            "base_balance": 10000,
            "comission": 0.001,
            "start": "2020-01-01",
            "stop": "2026-03-18",
            "datapoints": [
                {"name": "ema_20", "transformer": "ema", "args": [20]},
                {"name": "sma_200", "transformer": "sma", "args": [200]},
            ],
            "enter": [["ema_20", ">", "sma_200"]],
            "exit": [["ema_20", "<", "sma_200"]],
        },
    },
    {
        "name": "Oversold Bounce",
        "tag": "Mean Rev",
        "category": "Mean Reversion",
        "description": "Catch quick bounces: enter when RSI < 30 and price is above long-term SMA-200.",
        "explanation": "גישה קלאסית המתאימה למדדי מניות או נכסים יציבים. ההנחה היא שמגמת העלייה ארוכת הטווח תקפה ולכן כל ירידה חדה מהווה הזדמנות קנייה בהסתברות גבוהה לתיקון כלפי מעלה.",
        "state": {
            "symbol": "SPY",
            "exchange": "yfinance",
            "freq": "1D",
            "base_balance": 10000,
            "comission": 0.001,
            "start": "2020-01-01",
            "stop": "2026-03-18",
            "datapoints": [
                {"name": "rsi_14", "transformer": "rsi", "args": [14]},
                {"name": "sma_200", "transformer": "sma", "args": [200]},
            ],
            "enter": [["rsi_14", "<", 30], ["close", ">", "sma_200"]],
            "exit": [["rsi_14", ">", 70]],
        },
    },
    {
        "name": "Tech Triple Momentum",
        "tag": "Trend",
        "category": "Trend Following",
        "description": "Uses three EMAs (8, 21, 55) for aggressive trend following. Enter when aligned. Exit on fast cross.",
        "explanation": "אסטרטגיה זו מתאימה לנכסים בעלי נטייה למגמות חזקות וברורות. שימוש בשלושה ממוצעים נעים מסייע לסנן רעשי רקע שקריים ומשאיר את עסקת המסחר פתוחה רק כשיש הסכמה מוחלטת על כיוון המגמה.",
        "state": {
            "symbol": "QQQ",
            "exchange": "yfinance",
            "freq": "1D",
            "base_balance": 10000,
            "comission": 0.001,
            "start": "2020-01-01",
            "stop": "2026-03-18",
            "datapoints": [
                {"name": "ema_8", "transformer": "ema", "args": [8]},
                {"name": "ema_21", "transformer": "ema", "args": [21]},
                {"name": "ema_55", "transformer": "ema", "args": [55]},
            ],
            "enter": [["ema_8", ">", "ema_21"], ["ema_21", ">", "ema_55"]],
            "exit": [["ema_8", "<", "ema_21"]],
        },
    },
    {
        "name": "Gold Pullback Hunter",
        "tag": "Mean Rev",
        "category": "Mean Reversion",
        "description": "Buy dips in gold: RSI(4) < 25 AND SMA-100 uptrend. Exit on RSI(4) > 60.",
        "explanation": "זהב פועל לרוב כנכס מקלט ונוטה לכבד רמות תמיכה ומסגרות מחיר. בניגוד לנכסי טכנולוגיה שפורצים באגרסיביות בזהב נכון יותר טקטית לקנות נסיגות לתוך תמיכה במהלך מגמת עלייה.",
        "state": {
            "symbol": "GLD",
            "exchange": "yfinance",
            "freq": "1D",
            "base_balance": 10000,
            "comission": 0.001,
            "start": "2020-01-01",
            "stop": "2026-03-18",
            "datapoints": [
                {"name": "rsi_4", "transformer": "rsi", "args": [4]},
                {"name": "sma_100", "transformer": "sma", "args": [100]},
            ],
            "enter": [["rsi_4", "<", 25], ["close", ">", "sma_100"]],
            "exit": [["rsi_4", ">", 60]],
        },
    },
    {
        "name": "Silver Breakout",
        "tag": "Breakout",
        "category": "Breakout",
        "description": "Enter on 20-period highest high breakouts in silver. Exit on 10-period lowest low.",
        "explanation": "כסף מאופיין בתקופות דשדוש ארוכות שמסתיימות לעיתים קרובות בפריצות אלימות וחזקות. ערוצי המחיר מתוכננים בדיוק כדי להתעלם מהדשדוש ולהכניס אותך לעסקה רק כשהפריצה האמיתית והאגרסיבית מתרחשת.",
        "state": {
            "symbol": "SLV",
            "exchange": "yfinance",
            "freq": "1D",
            "base_balance": 10000,
            "comission": 0.001,
            "start": "2020-01-01",
            "stop": "2026-03-18",
            "datapoints": [
                {"name": "donchian_high_20", "transformer": "rolling_max", "args": [20]},
                {"name": "donchian_low_10", "transformer": "rolling_min", "args": [10]},
            ],
            "enter": [["close", ">", "donchian_high_20"]],
            "exit": [["close", "<", "donchian_low_10"]],
        },
    },
    {
        "name": "Market Hybrid Strategy",
        "tag": "Trend mean-reversion",
        "category": "Custom",
        "description": "Hybrid mean-reversion + trend-following approach for the S&P 500.",
        "explanation": "המדד המרכזי עולה לאורך זמן אך חווה תיקונים חדים. במקום להיות חשופים לנפילות השוק כל הזמן ההון יושב במזומן ומושקע רק בנקודות תורפה קצרות בתוך המגמה החיובית מה שמקטין משמעותית את ההפסד המקסימלי.",
        "state": {
            "symbol": "SPY",
            "exchange": "yfinance",
            "freq": "1D",
            "base_balance": 10000,
            "comission": 0.001,
            "start": "2021-03-16",
            "stop": "2026-03-16",
            "datapoints": [
                {"name": "rsi_2", "transformer": "rsi", "args": [2]},
                {"name": "rsi_7", "transformer": "rsi", "args": [7]},
                {"name": "rsi_14", "transformer": "rsi", "args": [14]},
                {"name": "sma_200", "transformer": "sma", "args": [200]},
                {"name": "ema_8", "transformer": "ema", "args": [8]},
                {"name": "macd_line", "transformer": "macd", "args": [12, 26, 9]},
                {"name": "atr_14", "transformer": "atr", "args": [14]},
            ],
            "enter": [
                ["close", ">", "sma_200"],
                ["rsi_2", "<", 10],
                ["rsi_14", "<", 35],
                ["atr_14", ">", 2],
            ],
            "exit": [
                ["rsi_7", ">", 85],
                ["close", ">", "ema_8"],
                ["macd_line", "<", 0],
            ],
        },
    },
    {
        "name": "Small Cap Oversold",
        "tag": "Mean Rev",
        "category": "Mean Reversion",
        "description": "RSI(2) <10 entry, >50 exit on IWM daily.",
        "explanation": "מניות קטנות נוטות לסבול מחוסר נזילות בזמן ירידות מה שגורם לתגובות פאניקה מוגזמות של מוכרים. אסטרטגיה מהירה זו מנצלת את העיוות הזה בכך שההון נשאר בטוח בחוץ ונכנס רק כשהפאניקה מגיעה לשיאה.",
        "state": {
            "symbol": "IWM",
            "exchange": "yfinance",
            "freq": "1D",
            "base_balance": 10000,
            "comission": 0.001,
            "start": "2024-03-16",
            "stop": "2026-03-16",
            "datapoints": [
                {"name": "rsi_2", "transformer": "rsi", "args": [2]},
            ],
            "enter": [["rsi_2", "<", 10]],
            "exit": [["rsi_2", ">", 50]],
        },
    },
]


def main():
    # 1. Delete all existing presets
    print("Fetching existing presets...")
    resp = requests.get(f"{API}/presets", timeout=10)
    resp.raise_for_status()
    existing = resp.json()
    print(f"  Found {len(existing)} existing presets — deleting...")
    for p in existing:
        r = requests.delete(f"{API}/presets/{p['id']}", timeout=10)
        if r.ok:
            print(f"  Deleted: {p['name']}")
        else:
            print(f"  WARN: Could not delete {p['name']}: {r.text}")

    # 2. Insert new presets
    print(f"\nInserting {len(PRESETS)} new presets...")
    created_ids = {}
    for p in PRESETS:
        payload = {
            "name": p["name"],
            "tag": p["tag"],
            "category": p["category"],
            "description": p["description"],
            "explanation": p["explanation"],
            "state": p["state"],
        }
        r = requests.post(f"{API}/presets", json=payload, timeout=10)
        if r.ok:
            created = r.json()
            created_ids[p["name"]] = created["id"]
            print(f"  Created [{created['id']}]: {p['name']}")
        else:
            print(f"  ERROR creating {p['name']}: {r.status_code} {r.text}")

    # 3. Run backtests
    print(f"\nRunning backtests for {len(PRESETS)} presets...")
    results = []
    for p in PRESETS:
        strategy = dict(p["state"])
        strategy["explanation"] = p["explanation"]
        payload = {"strategy": strategy, "use_cache": False, "username": "admin"}
        print(f"  Backtesting: {p['name']} ({p['state']['symbol']} {p['state']['freq']})...")
        try:
            r = requests.post(f"{API}/backtest", json=payload, timeout=120)
            if r.ok:
                data = r.json()
                s = data.get("summary", {})
                results.append({
                    "name": p["name"],
                    "return": s.get("return_perc", "n/a"),
                    "sharpe": s.get("sharpe_ratio", "n/a"),
                    "drawdown": s.get("max_drawdown") or (s.get("drawdown_metrics") or {}).get("max_drawdown_pct", "n/a"),
                    "trades": s.get("total_trades", "n/a"),
                    "win_rate": s.get("win_rate", "n/a"),
                    "bah": s.get("buy_and_hold_perc", "n/a"),
                    "status": "ok",
                })
            else:
                results.append({"name": p["name"], "status": f"ERROR {r.status_code}: {r.text[:120]}"})
        except Exception as e:
            results.append({"name": p["name"], "status": f"EXCEPTION: {e}"})

    # 4. Print results table
    print("\n" + "=" * 100)
    print(f"{'Strategy':<30} {'Return%':>8} {'Sharpe':>7} {'Drawdown':>9} {'Trades':>7} {'WinRate':>8} {'B&H%':>7} Status")
    print("-" * 100)
    for r in results:
        if r.get("status") == "ok":
            ret = f"{r['return']:.1f}" if isinstance(r['return'], (int, float)) else str(r['return'])
            sh = f"{r['sharpe']:.2f}" if isinstance(r['sharpe'], (int, float)) else str(r['sharpe'])
            dd = f"{r['drawdown']:.1f}" if isinstance(r['drawdown'], (int, float)) else str(r['drawdown'])
            wr = f"{r['win_rate']:.1f}" if isinstance(r['win_rate'], (int, float)) else str(r['win_rate'])
            bah = f"{r['bah']:.1f}" if isinstance(r['bah'], (int, float)) else str(r['bah'])
            print(f"{r['name']:<30} {ret:>8} {sh:>7} {dd:>9} {r['trades']:>7} {wr:>8} {bah:>7}  ok")
        else:
            print(f"{r['name']:<30} {'':>8} {'':>7} {'':>9} {'':>7} {'':>8} {'':>7}  {r['status']}")
    print("=" * 100)


if __name__ == "__main__":
    main()
