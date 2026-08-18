"""
Integration tests for Host_Team/auth_api/app.py using FastAPI's TestClient
(no real HTTP server, no real network port) against an isolated per-test
SQLite database (see conftest.py). Covers signup/login/validate-token
happy paths plus the failure paths a client can trigger: duplicate email,
wrong password, malformed payloads, and expired/invalid tokens.
"""

from datetime import datetime, timedelta, timezone

import pytest
from fastapi.testclient import TestClient


@pytest.fixture
def client(auth_app_module):
    with TestClient(auth_app_module.app) as c:
        yield c


class TestHealth:
    def test_health_reports_ok_and_sqlite_backend(self, client):
        resp = client.get("/health")
        assert resp.status_code == 200
        body = resp.json()
        assert body["ok"] is True
        assert body["db"] == "sqlite"


class TestSignup:
    def test_signup_creates_user(self, client):
        resp = client.post("/signup", json={"email": "new@example.com", "password": "password123"})
        assert resp.status_code == 200
        body = resp.json()
        assert body["ok"] is True
        assert body["email"] == "new@example.com"

    def test_signup_lowercases_and_strips_email(self, client):
        resp = client.post("/signup", json={"email": "  New@Example.com  ", "password": "password123"})
        assert resp.json()["email"] == "new@example.com"

    def test_duplicate_signup_returns_409(self, client):
        client.post("/signup", json={"email": "dup@example.com", "password": "password123"})
        resp = client.post("/signup", json={"email": "dup@example.com", "password": "password123"})
        assert resp.status_code == 409

    def test_duplicate_signup_case_insensitive(self, client):
        client.post("/signup", json={"email": "case@example.com", "password": "password123"})
        resp = client.post("/signup", json={"email": "CASE@example.com", "password": "password123"})
        assert resp.status_code == 409

    def test_invalid_email_format_returns_422(self, client):
        resp = client.post("/signup", json={"email": "not-an-email", "password": "password123"})
        assert resp.status_code == 422

    def test_password_too_short_returns_422(self, client):
        resp = client.post("/signup", json={"email": "short@example.com", "password": "abc"})
        assert resp.status_code == 422

    def test_missing_fields_return_422(self, client):
        resp = client.post("/signup", json={"email": "missing@example.com"})
        assert resp.status_code == 422

    def test_password_is_not_stored_in_plaintext(self, client, auth_app_module):
        client.post("/signup", json={"email": "hash@example.com", "password": "password123"})
        db = auth_app_module.SessionLocal()
        try:
            user = db.query(auth_app_module.User).filter_by(email="hash@example.com").first()
            assert user.password_hash != "password123"
        finally:
            db.close()


class TestLogin:
    def _signup(self, client, email="user@example.com", password="password123"):
        client.post("/signup", json={"email": email, "password": password})

    def test_login_with_correct_credentials_returns_token(self, client):
        self._signup(client)
        resp = client.post("/login", json={"email": "user@example.com", "password": "password123"})
        assert resp.status_code == 200
        body = resp.json()
        assert body["ok"] is True
        assert len(body["token"]) > 20
        assert body["user"]["email"] == "user@example.com"

    def test_login_with_wrong_password_returns_401(self, client):
        self._signup(client)
        resp = client.post("/login", json={"email": "user@example.com", "password": "wrongpass"})
        assert resp.status_code == 401

    def test_login_with_unknown_email_returns_401(self, client):
        resp = client.post("/login", json={"email": "ghost@example.com", "password": "password123"})
        assert resp.status_code == 401

    def test_login_error_does_not_leak_whether_user_exists(self, client):
        self._signup(client)
        wrong_pw = client.post("/login", json={"email": "user@example.com", "password": "wrongpass"})
        unknown_user = client.post("/login", json={"email": "ghost@example.com", "password": "password123"})
        assert wrong_pw.json()["detail"] == unknown_user.json()["detail"]

    def test_login_updates_last_login_timestamp(self, client, auth_app_module):
        self._signup(client)
        client.post("/login", json={"email": "user@example.com", "password": "password123"})
        db = auth_app_module.SessionLocal()
        try:
            user = db.query(auth_app_module.User).filter_by(email="user@example.com").first()
            assert user.last_login is not None
        finally:
            db.close()


class TestValidateToken:
    def _login_and_get_token(self, client):
        client.post("/signup", json={"email": "tok@example.com", "password": "password123"})
        resp = client.post("/login", json={"email": "tok@example.com", "password": "password123"})
        return resp.json()["token"]

    def test_valid_token_returns_user(self, client):
        token = self._login_and_get_token(client)
        resp = client.post("/validate-token", json={"token": token})
        assert resp.status_code == 200
        assert resp.json()["user"]["email"] == "tok@example.com"

    def test_unknown_token_returns_401(self, client):
        resp = client.post("/validate-token", json={"token": "x" * 32})
        assert resp.status_code == 401

    def test_token_too_short_returns_422(self, client):
        resp = client.post("/validate-token", json={"token": "short"})
        assert resp.status_code == 422

    def test_expired_token_returns_401(self, client, auth_app_module):
        token = self._login_and_get_token(client)
        db = auth_app_module.SessionLocal()
        try:
            sess = db.query(auth_app_module.SessionToken).filter_by(token=token).first()
            sess.expires_at = datetime.now(timezone.utc) - timedelta(hours=1)
            db.commit()
        finally:
            db.close()

        resp = client.post("/validate-token", json={"token": token})
        assert resp.status_code == 401

    def test_revoked_token_returns_401(self, client, auth_app_module):
        token = self._login_and_get_token(client)
        db = auth_app_module.SessionLocal()
        try:
            sess = db.query(auth_app_module.SessionToken).filter_by(token=token).first()
            sess.is_revoked = True
            db.commit()
        finally:
            db.close()

        resp = client.post("/validate-token", json={"token": token})
        assert resp.status_code == 401

    def test_each_login_issues_a_distinct_token(self, client):
        client.post("/signup", json={"email": "multi@example.com", "password": "password123"})
        r1 = client.post("/login", json={"email": "multi@example.com", "password": "password123"})
        r2 = client.post("/login", json={"email": "multi@example.com", "password": "password123"})
        assert r1.json()["token"] != r2.json()["token"]
        # Both tokens remain valid — login does not revoke prior sessions.
        assert client.post("/validate-token", json={"token": r1.json()["token"]}).status_code == 200
        assert client.post("/validate-token", json={"token": r2.json()["token"]}).status_code == 200
