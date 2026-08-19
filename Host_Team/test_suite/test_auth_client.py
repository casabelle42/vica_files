"""
Unit tests for Host_Team/Host/gui/auth_client.py — the HTTP client the GUI
uses to talk to the Auth API. requests.request is monkeypatched so these
tests never make a real HTTP call (no auth server needs to be running).
"""

import json

import pytest
import requests

import auth_client


class FakeResponse:
    def __init__(self, status_code=200, json_data=None, text=""):
        self.status_code = status_code
        self.ok = 200 <= status_code < 300
        self._json_data = json_data
        self.text = text

    def json(self):
        if self._json_data is None:
            raise ValueError("no json body")
        return self._json_data


class TestRequestHelper:
    def test_successful_request_returns_parsed_json(self, monkeypatch):
        monkeypatch.setattr(
            requests, "request", lambda **kw: FakeResponse(200, {"ok": True, "user_id": 1})
        )
        result = auth_client.signup("a@example.com", "password123")
        assert result == {"ok": True, "user_id": 1}

    def test_network_failure_raises_auth_client_error(self, monkeypatch):
        def raise_conn_error(**kw):
            raise requests.ConnectionError("refused")

        monkeypatch.setattr(requests, "request", raise_conn_error)
        with pytest.raises(auth_client.AuthClientError, match="Could not reach Auth API"):
            auth_client.login("a@example.com", "password123")

    def test_error_status_raises_with_detail_from_json(self, monkeypatch):
        monkeypatch.setattr(
            requests, "request", lambda **kw: FakeResponse(409, {"detail": "User already exists"})
        )
        with pytest.raises(auth_client.AuthClientError, match="User already exists"):
            auth_client.signup("dup@example.com", "password123")

    def test_error_status_with_non_json_body_uses_raw_text(self, monkeypatch):
        monkeypatch.setattr(
            requests,
            "request",
            lambda **kw: FakeResponse(500, json_data=None, text="internal error"),
        )
        with pytest.raises(auth_client.AuthClientError, match="internal error"):
            auth_client.login("a@example.com", "bad")

    def test_success_with_non_dict_json_returns_empty_dict(self, monkeypatch):
        monkeypatch.setattr(requests, "request", lambda **kw: FakeResponse(200, json_data=[1, 2]))
        assert auth_client.validate_token("sometoken12345678901234") == {}

    def test_request_sends_expected_method_and_url(self, monkeypatch):
        captured = {}

        def fake_request(**kw):
            captured.update(kw)
            return FakeResponse(200, {"ok": True})

        monkeypatch.setattr(requests, "request", fake_request)
        auth_client.login("a@example.com", "pw")

        assert captured["method"] == "POST"
        assert captured["url"] == f"{auth_client.AUTH_API_BASE_URL}/login"
        assert captured["json"] == {"email": "a@example.com", "password": "pw"}


class TestSessionPersistence:
    def test_save_and_load_round_trip(self, tmp_path, monkeypatch):
        session_file = tmp_path / ".session.json"
        monkeypatch.setattr(auth_client, "SESSION_FILE", session_file)

        auth_client.save_session("tok123", {"id": 1, "email": "a@example.com"})
        loaded = auth_client.load_session()

        assert loaded == {"token": "tok123", "user": {"id": 1, "email": "a@example.com"}}

    def test_load_session_missing_file_returns_empty_dict(self, tmp_path, monkeypatch):
        monkeypatch.setattr(auth_client, "SESSION_FILE", tmp_path / "nope.json")
        assert auth_client.load_session() == {}

    def test_load_session_corrupt_file_returns_empty_dict(self, tmp_path, monkeypatch):
        session_file = tmp_path / ".session.json"
        session_file.write_text("{not valid json", encoding="utf-8")
        monkeypatch.setattr(auth_client, "SESSION_FILE", session_file)
        assert auth_client.load_session() == {}

    def test_clear_session_removes_file(self, tmp_path, monkeypatch):
        session_file = tmp_path / ".session.json"
        session_file.write_text("{}", encoding="utf-8")
        monkeypatch.setattr(auth_client, "SESSION_FILE", session_file)

        auth_client.clear_session()

        assert not session_file.exists()

    def test_clear_session_missing_file_does_not_raise(self, tmp_path, monkeypatch):
        monkeypatch.setattr(auth_client, "SESSION_FILE", tmp_path / "nope.json")
        auth_client.clear_session()  # must not raise
