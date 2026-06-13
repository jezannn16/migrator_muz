# -*- coding: utf-8 -*-
"""
CLI-вариант прогона (без UI). Авторизуйся сперва через веб (python app.py),
файлы yandex_token.json / oauth.json / yt_client.json подхватятся автоматически.

Запуск:  python migrate.py
"""

import threading
import time

import core

SETTINGS = {
    "playlist_name": "Yandex Likes",
    "privacy": "PRIVATE",
    "threshold": 0.62,
    "also_like": False,
    "reset": False,
}


def main():
    if not core.yandex_logged_in():
        raise SystemExit("Нет входа в Яндекс. Сначала: python app.py (вход в браузере).")
    if not core.youtube_logged_in():
        raise SystemExit("Нет входа в YouTube. Сначала: python app.py (вход в браузере).")

    status = core.Status()
    stop = threading.Event()
    t = threading.Thread(target=core.run_migration, args=(SETTINGS, status, stop), daemon=True)
    t.start()

    seen = 0
    try:
        while t.is_alive():
            log = status.snapshot()["log"]
            for line in log[seen:]:
                print(line)
            seen = len(log)
            time.sleep(0.5)
    except KeyboardInterrupt:
        stop.set(); print("Останавливаю..."); t.join()
    for line in status.snapshot()["log"][seen:]:
        print(line)


if __name__ == "__main__":
    main()
