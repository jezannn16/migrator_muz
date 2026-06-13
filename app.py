# -*- coding: utf-8 -*-
"""
Веб-интерфейс переноса лайков Yandex Music -> YouTube Music.

Запуск:
    python app.py
Откроется http://127.0.0.1:5000 (сервер слушает только локально).
"""

import os
import threading
import webbrowser

from flask import Flask, request, jsonify, render_template, send_file, abort

import core

app = Flask(__name__)

YT_AUTH_FILE = "browser.json"

# единственная фоновая задача на процесс
STATUS = core.Status()
STOP_EVENT = threading.Event()
WORKER = None


# ----------------- страницы -----------------

@app.route("/")
def index():
    return render_template("index.html")


# ----------------- API -----------------

@app.route("/api/state")
def api_state():
    """Состояние окружения: есть ли авторизация YT, есть ли стейт для возобновления."""
    snap = STATUS.snapshot()
    return jsonify({
        "yt_auth_ready": os.path.exists(YT_AUTH_FILE),
        "resume_available": os.path.exists(core.STATE_FILE),
        "job": snap,
        "yandex_oauth_url":
            "https://oauth.yandex.ru/authorize?response_type=token"
            "&client_id=23cabbbdc6cd418abb4b39c32c41195d",
    })


@app.route("/api/yt-auth", methods=["POST"])
def api_yt_auth():
    """Сохранить авторизацию YT Music из вставленных заголовков."""
    data = request.get_json(force=True)
    headers_raw = (data.get("headers") or "").strip()
    if not headers_raw:
        return jsonify({"ok": False, "error": "Пустые заголовки."}), 400
    try:
        core.setup_yt_auth(headers_raw, YT_AUTH_FILE)
        return jsonify({"ok": True})
    except Exception as e:
        # подчистим возможный битый файл
        if os.path.exists(YT_AUTH_FILE):
            try:
                os.remove(YT_AUTH_FILE)
            except OSError:
                pass
        return jsonify({"ok": False, "error": str(e)}), 400


@app.route("/api/start", methods=["POST"])
def api_start():
    global WORKER
    if WORKER and WORKER.is_alive():
        return jsonify({"ok": False, "error": "Перенос уже идёт."}), 409

    data = request.get_json(force=True)
    ya_token = (data.get("ya_token") or "").strip()
    if not ya_token:
        return jsonify({"ok": False, "error": "Не указан токен Яндекса."}), 400
    if not os.path.exists(YT_AUTH_FILE):
        return jsonify({"ok": False, "error": "Нет авторизации YT Music (шаг 1)."}), 400

    settings = {
        "playlist_name": (data.get("playlist_name") or core.DEFAULTS["playlist_name"]).strip(),
        "privacy": data.get("privacy") or core.DEFAULTS["privacy"],
        "threshold": float(data.get("threshold", core.DEFAULTS["threshold"])),
        "also_like": bool(data.get("also_like", False)),
        "sleep": float(data.get("sleep", core.DEFAULTS["sleep"])),
        "reset": bool(data.get("reset", False)),
    }

    # свежий статус
    global STATUS, STOP_EVENT
    STATUS = core.Status()
    STOP_EVENT = threading.Event()

    WORKER = threading.Thread(
        target=core.run_migration,
        args=(ya_token, YT_AUTH_FILE, settings, STATUS, STOP_EVENT),
        daemon=True,
    )
    WORKER.start()
    return jsonify({"ok": True})


@app.route("/api/stop", methods=["POST"])
def api_stop():
    STOP_EVENT.set()
    return jsonify({"ok": True})


@app.route("/api/status")
def api_status():
    return jsonify(STATUS.snapshot())


@app.route("/api/download/<which>")
def api_download(which):
    fname = {"report": core.REPORT_FILE, "misses": core.MISSES_FILE}.get(which)
    if not fname or not os.path.exists(fname):
        abort(404)
    return send_file(os.path.abspath(fname), as_attachment=True)


def main():
    url = "http://127.0.0.1:5000"
    threading.Timer(1.0, lambda: webbrowser.open(url)).start()
    print(f"UI: {url}  (Ctrl+C — выход)")
    # только локально, без публичного доступа
    app.run(host="127.0.0.1", port=5000, debug=False)


if __name__ == "__main__":
    main()
