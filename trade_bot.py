import json
import time
import math
import ccxt

# ================= CONFIG =================

SIGNAL_FILE = "signal.json"

API_KEY = "PASTE_API_KEY_HERE"
API_SECRET = "PASTE_API_SECRET_HERE"

SYMBOL_DEFAULT = "HUSDT"

# 🔒 РЕЖИМ ТЕСТА (True = БЕЗ ТОРГОВЛИ)
DRY_RUN = True

LEVERAGE = 5
MAX_USED_USD = 50          # максимум денег в сетке
GRID_LEVELS = 7            # количество уровней
ATR_PERIOD = 14
ATR_MULT = 0.8             # влияет на шаг сетки
MAX_DD_PCT = 0.30          # 30% просадка → авария
PAUSE_AFTER_EXIT = 60 * 30 # 30 минут

CHECK_INTERVAL = 5         # секунд

# ================= BINANCE =================

exchange = ccxt.binance({
    "apiKey": API_KEY,
    "secret": API_SECRET,
    "enableRateLimit": True,
    "options": {
        "defaultType": "future"
    }
})

# ================= STATE =================

current_signal = None
grid_active = False
last_exit_ts = 0

# ================= UTILS =================

def log(msg):
    print(f"[{time.strftime('%H:%M:%S')}] {msg}")

def now():
    return int(time.time())

def load_signal():
    try:
        with open(SIGNAL_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except:
        return None

def fetch_price(symbol):
    return exchange.fetch_ticker(symbol)["last"]

def cancel_all(symbol):
    if DRY_RUN:
        log(f"[DRY] cancel all orders {symbol}")
        return
    try:
        exchange.cancelAllOrders(symbol)
    except:
        pass

# ================= ATR =================

def fetch_atr(symbol, timeframe="5m", period=14):
    ohlc = exchange.fetch_ohlcv(symbol, timeframe, limit=period + 1)
    trs = []

    for i in range(1, len(ohlc)):
        high = ohlc[i][2]
        low = ohlc[i][3]
        prev_close = ohlc[i-1][4]

        tr = max(
            high - low,
            abs(high - prev_close),
            abs(low - prev_close)
        )
        trs.append(tr)

    return sum(trs) / len(trs)

# ================= GRID =================

def build_grid(symbol, direction, price):
    atr = fetch_atr(symbol)
    step = (atr / price) * ATR_MULT

    usd_per_level = MAX_USED_USD / GRID_LEVELS

    log(f"📐 ATR: {atr:.6f} | шаг сетки: {step*100:.2f}%")

    cancel_all(symbol)

    for i in range(1, GRID_LEVELS + 1):
        if direction == "LONG":
            level_price = price * (1 - step * i)
            side = "buy"
        else:
            level_price = price * (1 + step * i)
            side = "sell"

        qty = round((usd_per_level * LEVERAGE) / level_price, 3)

        if DRY_RUN:
            log(f"[DRY] {side.upper()} {qty} @ {level_price:.5f}")
            continue

        try:
            exchange.create_order(
                symbol=symbol,
                type="limit",
                side=side,
                price=round(level_price, 5),
                amount=qty
            )
        except Exception as e:
            log(f"Ошибка ордера: {e}")

    log(f"🕸 Сетка построена: {direction}")

# ================= RISK =================

def emergency_check(symbol):
    if DRY_RUN:
        return False

    pos = exchange.fetch_positions([symbol])
    for p in pos:
        used = abs(float(p["initialMargin"]))
        pnl = float(p["unrealizedPnl"])

        if used > 0 and pnl < -used * MAX_DD_PCT:
            log("🚨 EMERGENCY EXIT")
            exchange.close_position(symbol)
            cancel_all(symbol)
            return True

    return False

# ================= MAIN LOOP =================

def main():
    global current_signal, grid_active, last_exit_ts

    log("🚀 trade_bot запущен")
    log(f"🧪 DRY_RUN = {DRY_RUN}")

    while True:
        sig = load_signal()

        if now() - last_exit_ts < PAUSE_AFTER_EXIT:
            time.sleep(CHECK_INTERVAL)
            continue

        if sig:
            symbol = sig.get("pair", SYMBOL_DEFAULT)
            signal = sig.get("signal")

            if signal != current_signal:
                log(f"📡 Новый сигнал: {symbol} {signal}")
                price = fetch_price(symbol)
                build_grid(symbol, signal, price)

                current_signal = signal
                grid_active = True

        if grid_active:
            if emergency_check(symbol):
                grid_active = False
                current_signal = None
                last_exit_ts = now()

        time.sleep(CHECK_INTERVAL)

if __name__ == "__main__":
    main()
