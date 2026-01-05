import json
import time
import asyncio

# файл, куда пишем сигнал
SIGNAL_FILE = "signal.json"

# очередь сигналов (из main.py мы будем просто кидать сюда данные)
signal_queue = asyncio.Queue()


async def write_signal_loop():
    """
    Фоновая задача: пишет последний сигнал в файл
    """
    while True:
        signal = await signal_queue.get()

        payload = {
            "pair": signal["pair"],
            "signal": signal["signal"],  # LONG / SHORT
            "tf": signal["tf"],
            "ts": int(time.time())
        }

        try:
            with open(SIGNAL_FILE, "w", encoding="utf-8") as f:
                json.dump(payload, f, indent=2, ensure_ascii=False)
        except Exception as e:
            print("Signal write error:", e)


def push_signal(pair, signal, tf):
    """
    Вызывается из сигнального бота
    """
    signal_queue.put_nowait({
        "pair": pair,
        "signal": signal,
        "tf": tf
    })
