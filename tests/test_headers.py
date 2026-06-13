# -*- coding: utf-8 -*-
"""Парсер входа: сырые заголовки ИЛИ 'Copy as cURL' -> строка заголовков для ytmusicapi."""
import core

BASH_CURL = r"""curl 'https://music.youtube.com/youtubei/v1/browse?key=AIzaXXX' \
  -H 'accept: */*' \
  -H 'authorization: SAPISIDHASH 1718_abcDEF' \
  -H 'content-type: application/json' \
  -b 'VISITOR_INFO1_LIVE=xyz; SAPISID=secret; __Secure-3PAPISID=secret2' \
  --compressed"""

CMD_CURL = 'curl "https://music.youtube.com/youtubei/v1/browse" ^\n' \
           '  -H "accept: */*" ^\n' \
           '  -H "authorization: SAPISIDHASH cmd_token" ^\n' \
           '  -H "cookie: A=1; SAPISID=secret"'


def test_curl_bash_extracts_headers_and_cookie():
    raw = core._normalize_headers_input(BASH_CURL)
    lines = raw.splitlines()
    assert "accept: */*" in lines
    assert any(l.startswith("authorization: SAPISIDHASH") for l in lines)
    assert any(l.startswith("cookie: ") and "SAPISID=secret" in l for l in lines)


def test_curl_cmd_with_cookie_header():
    raw = core._normalize_headers_input(CMD_CURL)
    lines = raw.splitlines()
    assert any(l.startswith("authorization: SAPISIDHASH cmd_token") for l in lines)
    assert any(l.startswith("cookie: ") and "SAPISID=secret" in l for l in lines)


def test_curl_does_not_duplicate_cookie():
    # cookie задан и через -H, и через -b -> в итоге одна cookie-строка
    c = ("curl 'u' -H 'cookie: a=b; c=d' -H 'authorization: Z' "
         "-b 'a=b; c=d'")
    raw = core._normalize_headers_input(c)
    cookies = [l for l in raw.splitlines() if l.lower().startswith("cookie:")]
    assert len(cookies) == 1


def test_raw_headers_passthrough_unchanged():
    raw_in = "accept: */*\nauthorization: X\ncookie: a=b"
    assert core._normalize_headers_input(raw_in) == raw_in
