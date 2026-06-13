# -*- coding: utf-8 -*-
"""
Ядро переноса лайков Yandex Music -> YouTube Music.

Авторизация: OAuth device flow для обоих сервисов (плюс ручной fallback).
  - Яндекс: yandex_music.Client().device_auth(on_code=...) — официальный клиент, регистрация не нужна.
  - YouTube: ytmusicapi OAuthCredentials.get_code()/token_from_code() — нужен свой Google OAuth-клиент.

Прогресс/коды отдаются через потокобезопасные State-объекты, остановка — через threading.Event.
"""

import csv
import json
import os
import re
import time
import difflib
import threading

from yandex_music import Client

STATE_FILE = "state.json"
REPORT_FILE = "report.csv"
MISSES_FILE = "misses.csv"

# файлы авторизации (все в .gitignore)
YANDEX_TOKEN_FILE = "yandex_token.json"   # {access_token, refresh_token, expires_at}
YT_OAUTH_FILE = "oauth.json"              # токен YouTube (ytmusicapi)
YT_CLIENT_FILE = "yt_client.json"         # {client_id, client_secret} Google OAuth-клиента
BROWSER_FILE = "browser.json"             # legacy: авторизация YT по заголовкам


# ============================================================
#  Потокобезопасные состояния
# ============================================================

class _LockedDict:
    def __init__(self, initial):
        self._lock = threading.Lock()
        self.data = dict(initial)

    def update(self, **kw):
        with self._lock:
            self.data.update(kw)

    def snapshot(self):
        with self._lock:
            return dict(self.data)


class AuthState(_LockedDict):
    """Состояние логина одного провайдера для UI."""
    def __init__(self, provider):
        super().__init__({
            "provider": provider,
            "phase": "idle",          # idle|starting|waiting|done|error
            "user_code": "",
            "verification_url": "",
            "error": None,
        })


class Status(_LockedDict):
    """Состояние прогона миграции для UI."""
    def __init__(self):
        super().__init__({
            "phase": "idle",          # idle|connecting|fetching|matching|done|error|stopped
            "running": False,
            "total": 0, "processed": 0, "matched": 0, "missed": 0,
            "current": "", "error": None,
            "playlist_id": None, "playlist_url": None,
            "log": [], "misses": [],
        })

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


# ============================================================
#  Авторизация — Яндекс
# ============================================================

def save_yandex_token(access_token, refresh_token=None, expires_in=None):
    data = {"access_token": access_token}
    if refresh_token:
        data["refresh_token"] = refresh_token
    if expires_in:
        data["expires_at"] = int(time.time()) + int(expires_in)
    with open(YANDEX_TOKEN_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=1)


def load_yandex_token():
    if not os.path.exists(YANDEX_TOKEN_FILE):
        return None
    with open(YANDEX_TOKEN_FILE, "r", encoding="utf-8") as f:
        return json.load(f).get("access_token")


def yandex_logged_in():
    return bool(load_yandex_token())


def run_yandex_device_login(auth: AuthState):
    """Device flow Яндекса. Блокирует до подтверждения — запускать в отдельном потоке."""
    auth.update(phase="starting", error=None, user_code="", verification_url="")
    try:
        def on_code(code):
            # code: объект с verification_url и user_code
            auth.update(
                phase="waiting",
                user_code=getattr(code, "user_code", "") or "",
                verification_url=getattr(code, "verification_url", "") or "",
            )

        client = Client()
        if not hasattr(client, "device_auth"):
            raise RuntimeError(
                "Версия yandex-music без device_auth. "
                "Обнови: pip install -U yandex-music  (или войди вручную токеном)."
            )
        token = client.device_auth(on_code=on_code)
        access = getattr(token, "access_token", None) or (
            token.get("access_token") if isinstance(token, dict) else None)
        if not access:
            raise RuntimeError("Не получили access_token от Яндекса.")
        save_yandex_token(
            access,
            getattr(token, "refresh_token", None),
            getattr(token, "expires_in", None),
        )
        # проверим, что токен живой
        Client(access).init()
        auth.update(phase="done")
    except Exception as e:
        auth.update(phase="error", error=str(e))


def save_yandex_token_manual(token_str):
    """Ручной fallback: пользователь вставил access_token."""
    token_str = (token_str or "").strip()
    if not token_str:
        raise ValueError("Пустой токен.")
    Client(token_str).init()   # валидация
    save_yandex_token(token_str)


# ============================================================
#  Авторизация — YouTube (Google OAuth device flow)
# ============================================================

def save_yt_client(client_id, client_secret):
    with open(YT_CLIENT_FILE, "w", encoding="utf-8") as f:
        json.dump({"client_id": client_id.strip(),
                   "client_secret": client_secret.strip()}, f, indent=1)


def load_yt_client():
    if not os.path.exists(YT_CLIENT_FILE):
        return None, None
    with open(YT_CLIENT_FILE, "r", encoding="utf-8") as f:
        d = json.load(f)
    return d.get("client_id"), d.get("client_secret")


def youtube_logged_in():
    # Рабочий путь — только заголовки. OAuth ('TV/Limited Input') у ytmusicapi
    # сейчас отдаёт HTTP 400 на все запросы (upstream #676), поэтому не считаем его.
    return os.path.exists(BROWSER_FILE)


def _oauth_credentials(client_id, client_secret):
    from ytmusicapi import OAuthCredentials
    return OAuthCredentials(client_id=client_id, client_secret=client_secret)


def run_youtube_device_login(client_id, client_secret, auth: AuthState):
    """Device flow Google. Блокирует (polling) до подтверждения — запускать в потоке."""
    auth.update(phase="starting", error=None, user_code="", verification_url="")
    try:
        client_id = (client_id or "").strip()
        client_secret = (client_secret or "").strip()
        if not client_id or not client_secret:
            raise ValueError("Нужны client_id и client_secret Google OAuth-клиента.")
        save_yt_client(client_id, client_secret)

        cred = _oauth_credentials(client_id, client_secret)
        code = cred.get_code()   # AuthCodeDict: device_code, user_code, verification_url, interval, expires_in
        auth.update(
            phase="waiting",
            user_code=code.get("user_code", ""),
            verification_url=code.get("verification_url", ""),
        )

        device_code = code["device_code"]
        interval = int(code.get("interval", 5) or 5)
        deadline = time.time() + int(code.get("expires_in", 1800) or 1800)

        token = None
        while time.time() < deadline:
            try:
                t = cred.token_from_code(device_code)
                if t and t.get("access_token"):
                    token = t
                    break
            except Exception:
                pass   # authorization_pending — ждём дальше
            time.sleep(interval)

        if not token:
            raise RuntimeError("Истекло время ожидания подтверждения Google.")

        _store_yt_token(token, cred)
        # проверим, что авторизация рабочая
        _make_yt_client()
        auth.update(phase="done")
    except Exception as e:
        auth.update(phase="error", error=str(e))


# поля, которые принимает RefreshingToken (лишние ключи вроде
# refresh_token_expires_in ломают и конструктор, и последующую загрузку oauth.json)
_YT_TOKEN_KEYS = {"scope", "token_type", "access_token",
                  "refresh_token", "expires_at", "expires_in"}


def _store_yt_token(token, cred):
    """Сохраняем токен YouTube в oauth.json в формате ytmusicapi (только нужные поля)."""
    clean = {k: v for k, v in dict(token).items() if k in _YT_TOKEN_KEYS}
    if "expires_in" in clean and "expires_at" not in clean:
        clean["expires_at"] = int(time.time()) + int(clean["expires_in"])
    try:
        from ytmusicapi.auth.oauth import RefreshingToken
        rt = RefreshingToken(credentials=cred, **clean)
        rt.store_token(YT_OAUTH_FILE)
        return
    except Exception:
        with open(YT_OAUTH_FILE, "w", encoding="utf-8") as f:
            json.dump(clean, f, indent=1)


def _curl_to_headers(text):
    """Вытаскивает заголовки и cookie из команды 'Copy as cURL' (bash или cmd)."""
    s = text.replace("\\\n", " ").replace("^\n", " ").replace("`\n", " ")
    headers = []
    for m in re.finditer(r"-H\s+'((?:[^']|'\\'')*)'", s):       # -H '...'
        headers.append(m.group(1).replace("'\\''", "'").strip())
    for m in re.finditer(r'-H\s+"((?:[^"\\]|\\.)*)"', s):       # -H "..."
        headers.append(m.group(1).replace('\\"', '"').strip())
    if not any(h.lower().startswith("cookie:") for h in headers):
        cm = (re.search(r"(?:-b|--cookie)\s+'((?:[^']|'\\'')*)'", s)
              or re.search(r'(?:-b|--cookie)\s+"((?:[^"\\]|\\.)*)"', s))
        if cm:
            headers.append("cookie: " + cm.group(1).replace("'\\''", "'").strip())
    return "\n".join(headers)


def _normalize_headers_input(text):
    """Принимает либо сырые Request Headers, либо вывод 'Copy as cURL'."""
    t = (text or "").strip()
    is_curl = bool(re.match(r"\s*curl\b", t)) or "-H '" in t or '-H "' in t
    return _curl_to_headers(t) if is_curl else text


def setup_yt_headers(headers_raw):
    """Авторизация YT по сырым заголовкам или cURL -> browser.json. С проверкой живым запросом."""
    from ytmusicapi import setup as yt_setup, YTMusic
    headers_raw = _normalize_headers_input(headers_raw)
    try:
        yt_setup(filepath=BROWSER_FILE, headers_raw=headers_raw)
    except Exception as e:
        _rm(BROWSER_FILE)
        raise RuntimeError(
            "Не разобрал заголовки. Нужны именно Request Headers (key: value), "
            "скопированные целиком. " + str(e))
    # реальный запрос — убедиться, что cookie/авторизация рабочие
    try:
        yt = YTMusic(BROWSER_FILE)
        yt.search("test", filter="songs", limit=1)
    except Exception as e:
        _rm(BROWSER_FILE)
        raise RuntimeError(
            "Заголовки сохранились, но запрос к YouTube не прошёл — скорее всего "
            "в них нет валидной cookie или они устарели. Скопируй Request Headers "
            "заново из POST-запроса к music.youtube.com. Детали: " + str(e))
    return True


def _rm(path):
    if os.path.exists(path):
        try:
            os.remove(path)
        except OSError:
            pass


def _make_yt_client():
    """Строим YTMusic из браузерной авторизации (browser.json).

    Только заголовки: OAuth-клиент 'TV/Limited Input' у ytmusicapi сейчас отдаёт
    HTTP 400 на все запросы (upstream issue #676), поэтому в рабочем пути не используется.
    """
    from ytmusicapi import YTMusic
    if os.path.exists(BROWSER_FILE):
        return YTMusic(BROWSER_FILE)
    raise RuntimeError(
        "Нет рабочей авторизации YouTube Music. Войди по заголовкам "
        "(OAuth сейчас не работает — баг ytmusicapi).")


# ============================================================
#  Нормализация и скоринг
# ============================================================

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
        a.get("name", "") for a in (cand.get("artists") or []) if a.get("name"))
    t = ratio(normalize(ya_title), normalize(cand_title))
    a = ratio(normalize(ya_artist), normalize(cand_artists))
    cd = cand.get("duration_seconds")
    if cd and ya_dur_s:
        dur = max(0.0, 1.0 - abs(cd - ya_dur_s) / 15.0)
    else:
        dur = 0.5
    return 0.45 * t + 0.35 * a + 0.20 * dur


# ============================================================
#  Состояние прогона
# ============================================================

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


def resume_available():
    return os.path.exists(STATE_FILE)


# ============================================================
#  Яндекс: выгрузка лайков
# ============================================================

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


# ============================================================
#  YouTube: поиск и мэтчинг
# ============================================================

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


# ============================================================
#  Основной прогон
# ============================================================

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


def run_migration(settings, status, stop_event, ya=None, yt=None):
    """Главный прогон. Авторизация берётся из сохранённых файлов.

    ya/yt можно передать напрямую (инъекция для тестов); иначе строятся из
    сохранённой авторизации.
    """
    cfg = dict(DEFAULTS)
    cfg.update(settings or {})
    try:
        status.update(phase="connecting", running=True, error=None)

        if ya is None:
            ya_token = load_yandex_token()
            if not ya_token:
                raise RuntimeError("Нет авторизации Яндекса (войди на шаге 1).")
            status.log("Подключение к Яндексу...")
            ya = Client(ya_token).init()

        if yt is None:
            status.log("Подключение к YT Music...")
            yt = _make_yt_client()

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

        if not state["playlist_id"]:
            pid = _retry(
                lambda: yt.create_playlist(cfg["playlist_name"], cfg["playlist_desc"],
                                           privacy_status=cfg["privacy"]),
                status=status, label="create_playlist")
            state["playlist_id"] = pid
            save_state(state)
            status.log(f"Создан плейлист: {cfg['playlist_name']}")
        playlist_id = state["playlist_id"]
        status.update(playlist_id=playlist_id,
                      playlist_url=f"https://music.youtube.com/playlist?list={playlist_id}")

        matched = sum(1 for v in state["done"].values() if v.get("status") == "ok")
        missed = sum(1 for v in state["done"].values() if v.get("status") == "miss")
        status.update(matched=matched, missed=missed,
                      processed=len(state["done"]), phase="matching")

        for t in tracks:
            if stop_event.is_set():
                status.update(phase="stopped", running=False)
                status.log("Остановлено пользователем.")
                write_reports(state)
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
                _mark_miss(state, status, yid, label, "недоступен в Яндексе")
                missed += 1
                _bump(status, state, matched, missed)
                save_state(state)
                continue

            try:
                cand, sc = best_match(yt, artist, title, dur_s,
                                      cfg["threshold"], cfg["search_limit"], status)
            except Exception as e:
                _mark_miss(state, status, yid, label, f"ошибка поиска: {e}")
                missed += 1
                status.log(f"ERR: {label} ({e})")
                _bump(status, state, matched, missed)
                save_state(state)
                continue

            if cand:
                vid = cand["videoId"]
                cand_artists = ", ".join(a.get("name", "") for a in (cand.get("artists") or []))
                try:
                    _retry(lambda: yt.add_playlist_items(playlist_id, [vid], duplicates=False),
                           status=status, label="add")
                    if cfg["also_like"]:
                        yt.rate_song(vid, "LIKE")
                except Exception as e:
                    _mark_miss(state, status, yid, label, f"ошибка добавления: {e}")
                    missed += 1
                    status.log(f"ADD-ERR: {label} ({e})")
                    _bump(status, state, matched, missed)
                    save_state(state)
                    time.sleep(cfg["sleep"])
                    continue
                state["done"][yid] = {
                    "status": "ok", "ya": label,
                    "yt": f"{cand_artists} — {cand.get('title', '')}",
                    "videoId": vid, "score": round(sc, 3)}
                matched += 1
                status.log(f"OK {sc:.2f}  {label}")
            else:
                _mark_miss(state, status, yid, label, f"низкая оценка {sc:.2f}")
                missed += 1
                status.log(f"MISS {sc:.2f}  {label}")

            _bump(status, state, matched, missed)
            save_state(state)
            time.sleep(cfg["sleep"])

        write_reports(state)
        status.update(phase="done", running=False, current="")
        status.log(f"Готово. Найдено: {matched}, не найдено: {missed}, всего: {total}")
    except Exception as e:
        status.update(phase="error", running=False, error=str(e))
        status.log(f"ОШИБКА: {e}")


def _retry(fn, status=None, label="", tries=3, base=1.0):
    """Повторяет fn при ошибке (транзиентные 400/сеть). Возвращает результат или кидает последнюю ошибку."""
    last = None
    for i in range(tries):
        try:
            return fn()
        except Exception as e:
            last = e
            if status and i < tries - 1:
                status.log(f"  {label}: ошибка ({e}); ретрай {i + 1}/{tries - 1}")
                time.sleep(base * (i + 1))
    raise last


def _mark_miss(state, status, yid, label, reason):
    state["done"][yid] = {"status": "miss", "ya": label, "reason": reason}
    status.add_miss(label, reason)


def _bump(status, state, matched, missed):
    status.update(processed=len(state["done"]), matched=matched, missed=missed)


def write_reports(state):
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
