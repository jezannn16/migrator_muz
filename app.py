# -*- coding: utf-8 -*-
"""
Веб-интерфейс переноса лайков Yandex Music -> YouTube Music.
Вход через OAuth device flow (Яндекс + Google) с ручным fallback.

Запуск:  python app.py   ->   http://127.0.0.1:5000  (только локально)
"""

import os
import threading
import webbrowser

from flask import Flask, request, jsonify, render_template, send_file, abort

import core

app = Flask(__name__)

# фоновые состояния (один процесс — один пользователь)
STATUS = core.Status()
STOP_EVENT = threading.Event()
WORKER = None

YA_AUTH = core.AuthState("yandex")
YT_AUTH = core.AuthState("youtube")
YA_THREAD = None
YT_THREAD = None


@app.route("/")
def index():
    resp = app.make_response(render_template("index.html"))
    resp.headers["Cache-Control"] = "no-store, no-cache, must-revalidate, max-age=0"
    return resp


# ---------------- общее состояние ----------------

@app.route("/api/state")
def api_state():
    return jsonify({
        "yandex_logged_in": core.yandex_logged_in(),
        "youtube_logged_in": core.youtube_logged_in(),
        "resume_available": core.resume_available(),
        "job": STATUS.snapshot(),
        "yandex_auth": YA_AUTH.snapshot(),
        "youtube_auth": YT_AUTH.snapshot(),
    })


# ---------------- логин Яндекс ----------------

@app.route("/api/yandex/login", methods=["POST"])
def api_yandex_login():
    global YA_THREAD, YA_AUTH
    if YA_THREAD and YA_THREAD.is_alive():
        return jsonify({"ok": True})   # уже идёт
    YA_AUTH = core.AuthState("yandex")
    YA_THREAD = threading.Thread(target=core.run_yandex_device_login,
                                 args=(YA_AUTH,), daemon=True)
    YA_THREAD.start()
    return jsonify({"ok": True})


@app.route("/api/yandex/status")
def api_yandex_status():
    return jsonify(YA_AUTH.snapshot())


@app.route("/api/yandex/manual", methods=["POST"])
def api_yandex_manual():
    token = (request.get_json(force=True).get("token") or "").strip()
    try:
        core.save_yandex_token_manual(token)
        return jsonify({"ok": True})
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)}), 400


# ---------------- логин YouTube ----------------

@app.route("/api/youtube/login", methods=["POST"])
def api_youtube_login():
    global YT_THREAD, YT_AUTH
    data = request.get_json(force=True)
    cid = (data.get("client_id") or "").strip()
    csec = (data.get("client_secret") or "").strip()
    if not cid or not csec:
        return jsonify({"ok": False, "error": "Нужны client_id и client_secret."}), 400
    if YT_THREAD and YT_THREAD.is_alive():
        return jsonify({"ok": True})
    YT_AUTH = core.AuthState("youtube")
    YT_THREAD = threading.Thread(target=core.run_youtube_device_login,
                                 args=(cid, csec, YT_AUTH), daemon=True)
    YT_THREAD.start()
    return jsonify({"ok": True})


@app.route("/api/youtube/status")
def api_youtube_status():
    return jsonify(YT_AUTH.snapshot())


@app.route("/api/youtube/manual", methods=["POST"])
def api_youtube_manual():
    headers = (request.get_json(force=True).get("headers") or "").strip()
    if not headers:
        return jsonify({"ok": False, "error": "Пустые заголовки."}), 400
    try:
        core.setup_yt_headers(headers)
        return jsonify({"ok": True})
    except Exception as e:
        if os.path.exists(core.BROWSER_FILE):
            try:
                os.remove(core.BROWSER_FILE)
            except OSError:
                pass
        return jsonify({"ok": False, "error": str(e)}), 400


# ---------------- миграция ----------------

@app.route("/api/start", methods=["POST"])
def api_start():
    global WORKER, STATUS, STOP_EVENT
    if WORKER and WORKER.is_alive():
        return jsonify({"ok": False, "error": "Перенос уже идёт."}), 409
    if not core.yandex_logged_in():
        return jsonify({"ok": False, "error": "Нет входа в Яндекс."}), 400
    if not core.youtube_logged_in():
        return jsonify({"ok": False, "error": "Нет входа в YouTube Music."}), 400

    data = request.get_json(force=True)
    settings = {
        "playlist_name": (data.get("playlist_name") or core.DEFAULTS["playlist_name"]).strip(),
        "privacy": data.get("privacy") or core.DEFAULTS["privacy"],
        "threshold": float(data.get("threshold", core.DEFAULTS["threshold"])),
        "also_like": bool(data.get("also_like", False)),
        "reset": bool(data.get("reset", False)),
    }
    STATUS = core.Status()
    STOP_EVENT = threading.Event()
    WORKER = threading.Thread(target=core.run_migration,
                              args=(settings, STATUS, STOP_EVENT), daemon=True)
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
    app.run(host="127.0.0.1", port=5000, debug=False)


if __name__ == "__main__":
    main()
