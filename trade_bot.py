import json
import time
import math
import ccxt

# ================== CONFIG ==================

SIGNAL_FILE = "signal.json"

API_KEY = "PASTE_API_KEY_HERE"
API_SECRET = "PASTE_API_SECRET_HERE"

SYMBOL_DEFAULT = "HUSDT"

LEVERAGE = 5
MAX_USED_USD = 50          # сколько денег максимум задействует сетка
GRID_LEVELS = 7            # количество уровней сетки
GRID_STEP_PCT = 0.003      # 0.3% шаг сетки
MAX_DD_PCT = 0.30          # 30% просадка → авария
PAUSE_AFTER_EXIT = 60 * 30 # 30 минут пауза

CHECK_INTERVAL = 5         # секунд

# ================== BINANCE ==================

exchange = ccxt.binance({
    "apiKey": API_KEY,
    "secret": API_SECRET,
    "enableRateLimit": True,
    "options": {
        "defaultType": "future"
    }
})

# ================== STATE ==================

current_signal = None
grid_active = False
last_exit_ts = 0

# ================== HELPERS ==================

def load_signal():
    try:
        with open(SIGNAL_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except:
        return None

def log(msg):
    print(f"[{time.strftime('%H:%M:%S')}] {msg}")

def now():
    return int(time.time())

def fetch_price(symbol):
    return exchange.fetch_ticker(symbol)["last"]

def cancel_all(symbol):
    try:
        exchange.cancelAllOrders(symbol)
    except:
        pass

def position_info(symbol):
    positions = exchange.fetch_positions([symbol])
    for p in positions:
        if abs(float(p["contracts"])) > 0:
            return p
    return None

# ================== GRID ==================

def build_grid(symbol, direction, price):
    cancel_all(symbol)

    usd_per_level = MAX_USED_USD / GRID_LEVELS
    orders = []

    for i in range(1, GRID_LEVELS + 1):
        if direction == "LONG":
            level_price = price * (1 - GRID_STEP_PCT * i)
            side = "buy"
        else:
            level_price = price * (1 + GRID_STEP_PCT * i)
            side = "sell"

        qty = round((usd_per_level * LEVERAGE) / level_price, 3)

        try:
            exchange.create_order(
                symbol=symbol,
                type="limit",
                side=side,
                price=round(level_price, 5),
                amount=qty
            )
            orders.append((side, qty, level_price))
        except Exception as e:
            log(f"Ошибка ордера: {e}")

    log(f"Сетка построена: {direction}, уровней: {len(orders)}")

# ================== RISK ==================

def emergency_check(symbol):
    pos = position_info(symbol)
    if not pos:
        return False

    used = abs(float(pos["initialMargin"]))
    pnl = float(pos["unrealizedPnl"])

    if used > 0 and pnl < -used * MAX_DD_PCT:
        log("🚨 EMERGENCY: превышена просадка")
        exchange.close_position(symbol)
        cancel_all(symbol)
        return True

    return False

# ================== MAIN LOOP ==================

def main():
    global current_signal, grid_active, last_exit_ts

    log("🚀 trade_bot запущен")

    while True:
        sig = load_signal()

        # пауза после аварии
        if now() - last_exit_ts < PAUSE_AFTER_EXIT:
            time.sleep(CHECK_INTERVAL)
            continue

        if sig:
            symbol = sig.get("pair", SYMBOL_DEFAULT)
            signal = sig.get("signal")

            if signal != current_signal:
                log(f"Новый сигнал: {symbol} {signal}")

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
