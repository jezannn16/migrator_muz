# -*- coding: utf-8 -*-
"""Тесты полного цикла run_migration на фейковых клиентах (через инъекцию)."""
import json
import threading

import pytest

import core


# ---------------- фейки ----------------

class FakeArtist:
    def __init__(self, name): self.name = name


class FakeTrack:
    def __init__(self, id, title, artist, dur_ms=200000, available=True):
        self.id = id
        self.title = title
        self.artists = [FakeArtist(artist)]
        self.duration_ms = dur_ms
        self.available = available


class FakeShort:
    def __init__(self, track_id, timestamp):
        self.track_id = track_id
        self.timestamp = timestamp


class FakeLikes:
    def __init__(self, shorts): self.tracks = shorts


class FakeYa:
    """shorts: список FakeShort (в произвольном порядке); tracks_by_id: dict id->FakeTrack."""
    def __init__(self, shorts, tracks_by_id):
        self._shorts = shorts
        self._by_id = tracks_by_id

    def init(self): return self

    def users_likes_tracks(self): return FakeLikes(list(self._shorts))

    def tracks(self, ids): return [self._by_id[i] for i in ids]


def _cand(title, artist, dur=200, vid=None):
    return {"title": title, "artists": [{"name": artist}],
            "duration_seconds": dur, "videoId": vid or ("vid_" + title)}


class FakeYt:
    """matches: dict title->cand. search вернёт [cand], если title встречается в запросе."""
    def __init__(self, matches):
        self._matches = matches
        self.created = []
        self.added = []       # порядок добавленных videoId
        self.liked = []

    def create_playlist(self, name, desc, privacy_status="PRIVATE"):
        self.created.append((name, privacy_status))
        return "PLID"

    def search(self, query, filter=None, limit=5):
        q = query.lower()
        for title, cand in self._matches.items():
            if title.lower() in q:
                return [cand]
        return []

    def add_playlist_items(self, pid, vids, duplicates=False):
        self.added.extend(vids)

    def rate_song(self, vid, rating):
        self.liked.append((vid, rating))


def _run(ya, yt, tmp_path, monkeypatch, settings=None, state=None):
    monkeypatch.chdir(tmp_path)
    if state is not None:
        core.save_state(state)
    s = core.Status()
    stop = threading.Event()
    cfg = {"sleep": 0, "threshold": 0.62}
    if settings:
        cfg.update(settings)
    core.run_migration(cfg, s, stop, ya=ya, yt=yt)
    return s


# ---------------- тесты ----------------

def test_migration_preserves_add_order(tmp_path, monkeypatch):
    # лайки приходят в обратном порядке по времени -> должны лечь старые->новые
    tracks = {
        "1": FakeTrack("1", "Alpha", "A"),
        "2": FakeTrack("2", "Beta", "B"),
        "3": FakeTrack("3", "Gamma", "G"),
    }
    shorts = [FakeShort("3", "2020-03"), FakeShort("1", "2020-01"), FakeShort("2", "2020-02")]
    ya = FakeYa(shorts, tracks)
    yt = FakeYt({"Alpha": _cand("Alpha", "A"), "Beta": _cand("Beta", "B"),
                 "Gamma": _cand("Gamma", "G")})

    s = _run(ya, yt, tmp_path, monkeypatch)

    assert yt.added == ["vid_Alpha", "vid_Beta", "vid_Gamma"]
    assert yt.created == [("Yandex Likes", "PRIVATE")]
    assert s.snapshot()["matched"] == 3
    assert s.snapshot()["missed"] == 0


def test_migration_miss_when_no_match(tmp_path, monkeypatch):
    tracks = {"1": FakeTrack("1", "Known", "A"),
              "2": FakeTrack("2", "Unfindable", "B")}
    shorts = [FakeShort("1", "1"), FakeShort("2", "2")]
    ya = FakeYa(shorts, tracks)
    yt = FakeYt({"Known": _cand("Known", "A")})  # Unfindable не в матчах

    s = _run(ya, yt, tmp_path, monkeypatch)

    assert yt.added == ["vid_Known"]
    snap = s.snapshot()
    assert snap["matched"] == 1 and snap["missed"] == 1
    assert any("Unfindable" in m["ya"] for m in snap["misses"])


def test_migration_skips_unavailable(tmp_path, monkeypatch):
    tracks = {"1": FakeTrack("1", "Gone", "A", available=False)}
    ya = FakeYa([FakeShort("1", "1")], tracks)
    yt = FakeYt({"Gone": _cand("Gone", "A")})

    s = _run(ya, yt, tmp_path, monkeypatch)

    assert yt.added == []          # недоступный не добавляется
    assert s.snapshot()["missed"] == 1


def test_migration_resume_skips_done(tmp_path, monkeypatch):
    tracks = {"1": FakeTrack("1", "Alpha", "A"), "2": FakeTrack("2", "Beta", "B")}
    ya = FakeYa([FakeShort("1", "1"), FakeShort("2", "2")], tracks)
    yt = FakeYt({"Alpha": _cand("Alpha", "A"), "Beta": _cand("Beta", "B")})
    # трек "1" уже сделан в прошлом прогоне + плейлист есть
    prior = {"playlist_id": "PLID", "done": {"1": {"status": "ok", "ya": "A — Alpha"}}}

    s = _run(ya, yt, tmp_path, monkeypatch, state=prior)

    assert yt.added == ["vid_Beta"]      # только новый трек
    assert yt.created == []               # плейлист повторно не создаётся


def test_migration_also_like(tmp_path, monkeypatch):
    tracks = {"1": FakeTrack("1", "Alpha", "A")}
    ya = FakeYa([FakeShort("1", "1")], tracks)
    yt = FakeYt({"Alpha": _cand("Alpha", "A")})

    _run(ya, yt, tmp_path, monkeypatch, settings={"also_like": True})

    assert yt.liked == [("vid_Alpha", "LIKE")]


def test_migration_stop_event_halts(tmp_path, monkeypatch):
    tracks = {"1": FakeTrack("1", "Alpha", "A"), "2": FakeTrack("2", "Beta", "B")}
    ya = FakeYa([FakeShort("1", "1"), FakeShort("2", "2")], tracks)
    yt = FakeYt({"Alpha": _cand("Alpha", "A"), "Beta": _cand("Beta", "B")})
    monkeypatch.chdir(tmp_path)
    s = core.Status()
    stop = threading.Event()
    stop.set()   # остановлено до старта цикла
    core.run_migration({"sleep": 0}, s, stop, ya=ya, yt=yt)

    assert yt.added == []
    assert s.snapshot()["phase"] == "stopped"


def test_migration_done_phase_and_reports(tmp_path, monkeypatch):
    tracks = {"1": FakeTrack("1", "Alpha", "A")}
    ya = FakeYa([FakeShort("1", "1")], tracks)
    yt = FakeYt({"Alpha": _cand("Alpha", "A")})

    s = _run(ya, yt, tmp_path, monkeypatch)

    assert s.snapshot()["phase"] == "done"
    assert (tmp_path / core.REPORT_FILE).exists()
