# -*- coding: utf-8 -*-
"""
CLI-вариант переноса (для тех, кому не нужен веб-интерфейс).
Большинству удобнее: python app.py  (браузерный UI).

Запуск:
    python migrate.py
Заполни YA_TOKEN ниже и положи рядом browser.json (ytmusicapi browser).
"""

import os
import threading

import core

# ----- настройки CLI -----
YA_TOKEN = "ВСТАВЬ_ЯНДЕКС_ТОКЕН"
YT_AUTH_FILE = "browser.json"
SETTINGS = {
    "playlist_name": "Yandex Likes",
    "privacy": "PRIVATE",
    "threshold": 0.62,
    "also_like": False,
    "sleep": 0.6,
    "reset": False,
}


def main():
    assert YA_TOKEN and YA_TOKEN != "ВСТАВЬ_ЯНДЕКС_ТОКЕН", "Заполни YA_TOKEN"
    assert os.path.exists(YT_AUTH_FILE), f"Нет {YT_AUTH_FILE}: сделай 'ytmusicapi browser'"

    status = core.Status()
    stop = threading.Event()

    # печать лога в консоль по мере поступления
    seen = 0
    import time
    t = threading.Thread(
        target=core.run_migration,
        args=(YA_TOKEN, YT_AUTH_FILE, SETTINGS, status, stop),
        daemon=True,
    )
    t.start()
    try:
        while t.is_alive():
            snap = status.snapshot()
            for line in snap["log"][seen:]:
                print(line)
            seen = len(snap["log"])
            time.sleep(0.5)
    except KeyboardInterrupt:
        stop.set()
        print("Останавливаю...")
        t.join()
    # финальный хвост лога
    for line in status.snapshot()["log"][seen:]:
        print(line)


if __name__ == "__main__":
    main()
