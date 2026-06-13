# -*- coding: utf-8 -*-
"""Тесты веб-слоя: пароль-гейт и гарды /api/start."""
import base64

import pytest

import app as appmod
import core


@pytest.fixture
def client():
    return appmod.app.test_client()


def _basic(pw):
    return {"Authorization": "Basic " + base64.b64encode(("x:" + pw).encode()).decode()}


# ---------------- пароль-гейт ----------------

def test_gate_off_when_no_password(client, monkeypatch):
    monkeypatch.setattr(appmod, "APP_PASSWORD", "")
    assert client.get("/api/state").status_code == 200


def test_gate_blocks_without_auth(client, monkeypatch):
    monkeypatch.setattr(appmod, "APP_PASSWORD", "secret")
    assert client.get("/api/state").status_code == 401


def test_gate_allows_correct_password(client, monkeypatch):
    monkeypatch.setattr(appmod, "APP_PASSWORD", "secret")
    assert client.get("/api/state", headers=_basic("secret")).status_code == 200


def test_gate_rejects_wrong_password(client, monkeypatch):
    monkeypatch.setattr(appmod, "APP_PASSWORD", "secret")
    assert client.get("/api/state", headers=_basic("nope")).status_code == 401


# ---------------- /api/start гарды ----------------

def test_start_requires_yandex(client, tmp_path, monkeypatch):
    monkeypatch.setattr(appmod, "APP_PASSWORD", "")
    monkeypatch.chdir(tmp_path)   # нет файлов авторизации
    r = client.post("/api/start", json={})
    assert r.status_code == 400
    assert "Яндекс" in r.get_json()["error"]


def test_start_requires_youtube(client, tmp_path, monkeypatch):
    monkeypatch.setattr(appmod, "APP_PASSWORD", "")
    monkeypatch.chdir(tmp_path)
    core.save_yandex_token("TKN")      # Яндекс есть, YouTube нет
    r = client.post("/api/start", json={})
    assert r.status_code == 400
    assert "YouTube" in r.get_json()["error"]


# ---------------- /api/state форма ----------------

def test_state_shape(client, monkeypatch, tmp_path):
    monkeypatch.setattr(appmod, "APP_PASSWORD", "")
    monkeypatch.chdir(tmp_path)
    j = client.get("/api/state").get_json()
    for key in ("yandex_logged_in", "youtube_logged_in", "resume_available", "job"):
        assert key in j


def test_index_renders(client, monkeypatch):
    monkeypatch.setattr(appmod, "APP_PASSWORD", "")
    r = client.get("/")
    assert r.status_code == 200
    assert b"YouTube" in r.data
