# -*- coding: utf-8 -*-
"""
Ядро переноса лайков Yandex Music -> YouTube Music.
Используется и веб-интерфейсом (app.py), и CLI (migrate.py).

Прогресс отдаётся через объект Status (потокобезопасный),
остановка — через threading.Event.
"""

import csv
import json
import os
import re
import time
import difflib
import threading

from yandex_music import Client
from ytmusicapi import YTMusic

STATE_FILE = "state.json"
REPORT_FILE = "report.csv"
MISSES_FILE = "misses.csv"


# ---------------- общий объект статуса ----------------

class Status:
    """Потокобезопасный снимок прогресса для UI."""

    def __init__(self):
        self._lock = threading.Lock()
        self.data = {
            "phase": "idle",          # idle|connecting|fetching|matching|done|error|stopped
            "running": False,
            "total": 0,
            "processed": 0,
            "matched": 0,
            "missed": 0,
            "current": "",
            "error": None,
            "playlist_id": None,
            "playlist_url": None,
            "log": [],                # последние строки лога
            "misses": [],             # [{ya, reason}]
        }

    def update(self, **kw):
        with self._lock:
            self.data.update(kw)

    def log(self, line):
        with self._lock:
            self.data["log"].append(line)
            if len(self.data["log"]) > 400:
                self.data["log"] = self.data["log"][-400:]

    def add_miss(self, ya, reason):
        with self._lock:
            self.data["misses"].append({"ya": ya, "reason": reason})

    def snapshot(self):
        with self._lock:
            d = dict(self.data)
            d["log"] = list(self.data["log"][-200:])
            d["misses"] = list(self.data["misses"][-500:])
            return d


# ---------------- нормализация и скоринг ----------------

_FEAT_RE = re.compile(r"\b(feat|ft|featuring)\b\.?.*", re.IGNORECASE)
_BRACKETS_RE = re.compile(r"[\(\[\{].*?[\)\]\}]")
_NONWORD_RE = re.compile(r"[^\w\s]", re.UNICODE)
_SPACES_RE = re.compile(r"\s+")


def normalize(s):
    if not s:
        return ""
    s = s.lower().strip()
    s = _FEAT_RE.sub("", s)
    s = _BRACKETS_RE.sub(" ", s)
    s = _NONWORD_RE.sub(" ", s)
    s = _SPACES_RE.sub(" ", s).strip()
    return s


def ratio(a, b):
    return difflib.SequenceMatcher(None, a, b).ratio()


def score_candidate(ya_artist, ya_title, ya_dur_s, cand):
    cand_title = cand.get("title", "") or ""
    cand_artists = " ".join(
        a.get("name", "") for a in (cand.get("artists") or []) if a.get("name")
    )
    t = ratio(normalize(ya_title), normalize(cand_title))
    a = ratio(normalize(ya_artist), normalize(cand_artists))
    cd = cand.get("duration_seconds")
    if cd and ya_dur_s:
        dur = max(0.0, 1.0 - abs(cd - ya_dur_s) / 15.0)
    else:
        dur = 0.5
    return 0.45 * t + 0.35 * a + 0.20 * dur


# ---------------- состояние ----------------

def load_state():
    if os.path.exists(STATE_FILE):
        with open(STATE_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    return {"playlist_id": None, "done": {}}


def save_state(state):
    tmp = STATE_FILE + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(state, f, ensure_ascii=False, indent=1)
    os.replace(tmp, STATE_FILE)


def reset_state():
    for f in (STATE_FILE, STATE_FILE + ".tmp"):
        if os.path.exists(f):
            os.remove(f)


# ---------------- Яндекс ----------------

def fetch_yandex_likes(ya, status):
    likes = ya.users_likes_tracks()
    shorts = list(likes.tracks)
    shorts.sort(key=lambda s: s.timestamp or "")   # старые -> новые = порядок добавления
    ids = [s.track_id for s in shorts]

    tracks = []
    CH = 50
    for i in range(0, len(ids), CH):
        tracks.extend(ya.tracks(ids[i:i + CH]))
        status.log(f"Выгружено {min(i + CH, len(ids))}/{len(ids)}")
    return tracks


# ---------------- YT Music ----------------

def yt_search_songs(yt, query, limit, status):
    for attempt in range(3):
        try:
            return yt.search(query, filter="songs", limit=limit)
        except Exception as e:
            wait = 2 * (attempt + 1)
            status.log(f"  поиск упал ({e}); ретрай через {wait}с")
            time.sleep(wait)
    return []


def best_match(yt, ya_artist, ya_title, ya_dur_s, threshold, limit, status):
    queries = [f"{ya_artist} {ya_title}", ya_title]
    best, best_s = None, 0.0
    for q in queries:
        for cand in yt_search_songs(yt, q, limit, status):
            if not cand.get("videoId"):
                continue
            s = score_candidate(ya_artist, ya_title, ya_dur_s, cand)
            if s > best_s:
                best, best_s = cand, s
        if best_s >= 0.85:
            break
    if best and best_s >= threshold:
        return best, best_s
    return None, best_s


# ---------------- авторизация YT из вставленных заголовков ----------------

def setup_yt_auth(headers_raw, yt_auth_file):
    """Создаёт browser.json из сырых заголовков, скопированных из music.youtube.com."""
    from ytmusicapi import setup as yt_setup
    yt_setup(filepath=yt_auth_file, headers_raw=headers_raw)
    # проверим, что авторизация валидна
    YTMusic(yt_auth_file)
    return True


# ---------------- основной прогон ----------------

DEFAULTS = {
    "playlist_name": "Yandex Likes",
    "playlist_desc": "Импорт лайков из Яндекс.Музыки",
    "privacy": "PRIVATE",
    "threshold": 0.62,
    "also_like": False,
    "sleep": 0.6,
    "search_limit": 5,
    "reset": False,
}


def run_migration(ya_token, yt_auth_file, settings, status, stop_event):
    """Главный прогон. Обновляет status, уважает stop_event."""
    cfg = dict(DEFAULTS)
    cfg.update(settings or {})

    try:
        status.update(phase="connecting", running=True, error=None)
        status.log("Подключение к Яндексу...")
        ya = Client(ya_token).init()

        status.log("Подключение к YT Music...")
        yt = YTMusic(yt_auth_file)

        if cfg["reset"]:
            reset_state()
            status.log("Стейт сброшен — перенос с нуля.")

        state = load_state()

        status.update(phase="fetching")
        status.log("Выгрузка лайков из Яндекса...")
        tracks = fetch_yandex_likes(ya, status)
        total = len(tracks)
        status.update(total=total)
        status.log(f"Всего лайков: {total}")

        # плейлист
        if not state["playlist_id"]:
            pid = yt.create_playlist(cfg["playlist_name"], cfg["playlist_desc"],
                                     privacy_status=cfg["privacy"])
            state["playlist_id"] = pid
            save_state(state)
            status.log(f"Создан плейлист: {cfg['playlist_name']}")
        playlist_id = state["playlist_id"]
        status.update(
            playlist_id=playlist_id,
            playlist_url=f"https://music.youtube.com/playlist?list={playlist_id}",
        )

        matched = sum(1 for v in state["done"].values() if v.get("status") == "ok")
        missed = sum(1 for v in state["done"].values() if v.get("status") == "miss")
        processed = len(state["done"])
        status.update(matched=matched, missed=missed, processed=processed,
                      phase="matching")

        for t in tracks:
            if stop_event.is_set():
                status.update(phase="stopped", running=False)
                status.log("Остановлено пользователем.")
                write_reports(state, status)
                return

            yid = str(t.id)
            if yid in state["done"]:
                continue

            artist = ", ".join(a.name for a in t.artists) if t.artists else ""
            title = t.title or ""
            dur_s = int(t.duration_ms / 1000) if t.duration_ms else None
            label = f"{artist} — {title}"
            status.update(current=label)

            if not (t.available is None or t.available):
                state["done"][yid] = {"status": "miss", "ya": label, "reason": "недоступен в Яндексе"}
                missed += 1
                status.add_miss(label, "недоступен в Яндексе")
                _bump(status, state, matched, missed)
                save_state(state)
                continue

            try:
                cand, sc = best_match(yt, artist, title, dur_s,
                                      cfg["threshold"], cfg["search_limit"], status)
            except Exception as e:
                state["done"][yid] = {"status": "miss", "ya": label, "reason": f"ошибка поиска: {e}"}
                missed += 1
                status.add_miss(label, f"ошибка поиска: {e}")
                status.log(f"ERR: {label} ({e})")
                _bump(status, state, matched, missed)
                save_state(state)
                continue

            if cand:
                vid = cand["videoId"]
                cand_artists = ", ".join(a.get("name", "") for a in (cand.get("artists") or []))
                try:
                    yt.add_playlist_items(playlist_id, [vid], duplicates=False)
                    if cfg["also_like"]:
                        yt.rate_song(vid, "LIKE")
                except Exception as e:
                    state["done"][yid] = {"status": "miss", "ya": label, "reason": f"ошибка добавления: {e}"}
                    missed += 1
                    status.add_miss(label, f"ошибка добавления: {e}")
                    status.log(f"ADD-ERR: {label} ({e})")
                    _bump(status, state, matched, missed)
                    save_state(state)
                    time.sleep(cfg["sleep"])
                    continue

                state["done"][yid] = {
                    "status": "ok", "ya": label,
                    "yt": f"{cand_artists} — {cand.get('title', '')}",
                    "videoId": vid, "score": round(sc, 3),
                }
                matched += 1
                status.log(f"OK {sc:.2f}  {label}")
            else:
                state["done"][yid] = {"status": "miss", "ya": label, "reason": f"низкая оценка {sc:.2f}"}
                missed += 1
                status.add_miss(label, f"низкая оценка {sc:.2f}")
                status.log(f"MISS {sc:.2f}  {label}")

            _bump(status, state, matched, missed)
            save_state(state)
            time.sleep(cfg["sleep"])

        write_reports(state, status)
        status.update(phase="done", running=False, current="")
        status.log(f"Готово. Найдено: {matched}, не найдено: {missed}, всего: {total}")

    except Exception as e:
        status.update(phase="error", running=False, error=str(e))
        status.log(f"ОШИБКА: {e}")


def _bump(status, state, matched, missed):
    status.update(processed=len(state["done"]), matched=matched, missed=missed)


def write_reports(state, status=None):
    rows = list(state["done"].values())
    with open(REPORT_FILE, "w", encoding="utf-8-sig", newline="") as f:
        w = csv.writer(f, delimiter=";")
        w.writerow(["status", "yandex", "youtube", "score", "videoId", "reason"])
        for r in rows:
            w.writerow([r.get("status"), r.get("ya", ""), r.get("yt", ""),
                        r.get("score", ""), r.get("videoId", ""), r.get("reason", "")])
    with open(MISSES_FILE, "w", encoding="utf-8-sig", newline="") as f:
        w = csv.writer(f, delimiter=";")
        w.writerow(["yandex", "reason"])
        for r in rows:
            if r.get("status") == "miss":
                w.writerow([r.get("ya", ""), r.get("reason", "")])
