# -*- coding: utf-8 -*-
"""Тесты чистой логики core: нормализация, скоринг, мэтчинг, стейт, отчёты, токен."""
import os
import csv
import json

import pytest

import core


# ---------------- normalize ----------------

def test_normalize_lowercases_and_trims():
    assert core.normalize("  Hello World  ") == "hello world"


def test_normalize_strips_feat():
    assert core.normalize("Song feat. Other Artist") == "song"


def test_normalize_removes_bracket_content():
    assert core.normalize("Song (Remix) [Live]") == "song"


def test_normalize_drops_punctuation():
    assert core.normalize("Rock'n'Roll, Baby!") == "rock n roll baby"


def test_normalize_handles_none():
    assert core.normalize(None) == ""


def test_normalize_keeps_cyrillic():
    assert core.normalize("Кино — Группа крови!") == "кино группа крови"


# ---------------- score_candidate ----------------

def _cand(title, artists, dur=None):
    return {"title": title, "artists": [{"name": a} for a in artists],
            "duration_seconds": dur, "videoId": "v"}


def test_score_perfect_match_high():
    s = core.score_candidate("Kino", "Gruppa krovi", 200,
                             _cand("Gruppa krovi", ["Kino"], 200))
    assert s > 0.95


def test_score_wrong_track_low():
    s = core.score_candidate("Kino", "Gruppa krovi", 200,
                             _cand("Imagine", ["John Lennon"], 180))
    assert s < 0.5


def test_score_duration_penalty():
    close = core.score_candidate("A", "Song", 200, _cand("Song", ["A"], 200))
    far = core.score_candidate("A", "Song", 200, _cand("Song", ["A"], 260))
    assert close > far


def test_score_missing_duration_neutral():
    # нет duration_seconds у кандидата -> не падает, даёт средний вклад
    s = core.score_candidate("A", "Song", 200, _cand("Song", ["A"], None))
    assert 0.0 <= s <= 1.0


# ---------------- best_match ----------------

class FakeYt:
    def __init__(self, results):
        self._results = results
        self.searches = []

    def search(self, query, filter=None, limit=5):
        self.searches.append(query)
        return list(self._results)


class _Status:
    def log(self, *a): pass


def test_best_match_picks_above_threshold():
    yt = FakeYt([_cand("Gruppa krovi", ["Kino"], 200),
                 _cand("Other", ["X"], 100)])
    cand, sc = core.best_match(yt, "Kino", "Gruppa krovi", 200, 0.62, 5, _Status())
    assert cand is not None
    assert cand["title"] == "Gruppa krovi"
    assert sc > 0.62


def test_best_match_returns_none_below_threshold():
    yt = FakeYt([_cand("Totally Different", ["Nobody"], 30)])
    cand, sc = core.best_match(yt, "Kino", "Gruppa krovi", 200, 0.62, 5, _Status())
    assert cand is None
    assert sc < 0.62


def test_best_match_stops_early_on_great_match():
    # отличный матч с первого запроса -> второй запрос (title-only) не делается
    yt = FakeYt([_cand("Gruppa krovi", ["Kino"], 200)])
    core.best_match(yt, "Kino", "Gruppa krovi", 200, 0.62, 5, _Status())
    assert len(yt.searches) == 1


# ---------------- state ----------------

def test_state_roundtrip(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    assert core.load_state() == {"playlist_id": None, "done": {}}
    st = {"playlist_id": "PL", "done": {"1": {"status": "ok"}}}
    core.save_state(st)
    assert core.resume_available() is True
    assert core.load_state() == st


def test_reset_state_removes_file(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    core.save_state({"playlist_id": None, "done": {}})
    core.reset_state()
    assert core.resume_available() is False


# ---------------- reports ----------------

def test_write_reports_cyrillic_and_misses(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    state = {"playlist_id": "PL", "done": {
        "1": {"status": "ok", "ya": "Кино — Группа крови",
              "yt": "Kino — Gruppa krovi", "videoId": "abc", "score": 0.9},
        "2": {"status": "miss", "ya": "Редкий трек", "reason": "низкая оценка 0.40"},
    }}
    core.write_reports(state)

    with open(core.REPORT_FILE, encoding="utf-8-sig", newline="") as f:
        rows = list(csv.reader(f, delimiter=";"))
    assert rows[0] == ["status", "yandex", "youtube", "score", "videoId", "reason"]
    assert any(r[0] == "ok" and "Кино" in r[1] for r in rows[1:])

    with open(core.MISSES_FILE, encoding="utf-8-sig", newline="") as f:
        mrows = list(csv.reader(f, delimiter=";"))
    assert mrows[0] == ["yandex", "reason"]
    assert len(mrows) == 2  # header + 1 miss (ok не попадает)
    assert mrows[1][0] == "Редкий трек"


# ---------------- YT token store (фильтр лишних ключей) ----------------

def test_store_yt_token_filters_extra_keys(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(core, "YT_OAUTH_FILE", "oauth.json")
    token = {"access_token": "A", "refresh_token": "R", "scope": "s",
             "token_type": "Bearer", "expires_in": 3600,
             "refresh_token_expires_in": 99999}  # лишний ключ
    core._store_yt_token(token, cred=None)  # cred=None -> упадёт RefreshingToken, уйдёт в fallback
    data = json.load(open("oauth.json", encoding="utf-8"))
    assert "refresh_token_expires_in" not in data
    assert "expires_at" in data
    assert data["access_token"] == "A"


# ---------------- проверки авторизации по файлам ----------------

def test_youtube_logged_in_requires_browser_file(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(core, "BROWSER_FILE", "browser.json")
    assert core.youtube_logged_in() is False
    with open("browser.json", "w") as f:
        f.write("{}")
    assert core.youtube_logged_in() is True


def test_yandex_logged_in(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(core, "YANDEX_TOKEN_FILE", "yandex_token.json")
    assert core.yandex_logged_in() is False
    core.save_yandex_token("TKN")
    assert core.yandex_logged_in() is True
    assert core.load_yandex_token() == "TKN"


def test_make_yt_client_errors_without_auth(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(core, "BROWSER_FILE", "browser.json")
    with pytest.raises(RuntimeError):
        core._make_yt_client()
