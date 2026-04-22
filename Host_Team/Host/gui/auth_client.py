from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any, Dict

import requests


AUTH_API_BASE_URL = os.getenv("VICA_AUTH_API_URL", "http://127.0.0.1:8001").rstrip("/")
SESSION_FILE = Path(__file__).resolve().parent / ".session.json"


class AuthClientError(Exception):
    pass


def _request(method: str, path: str, payload: Dict[str, Any]) -> Dict[str, Any]:
    url = f"{AUTH_API_BASE_URL}{path}"
    try:
        resp = requests.request(method=method, url=url, json=payload, timeout=10)
    except requests.RequestException as exc:
        raise AuthClientError(f"Could not reach Auth API at {AUTH_API_BASE_URL}: {exc}") from exc

    try:
        data = resp.json()
    except ValueError:
        data = {"detail": resp.text}

    if not resp.ok:
        detail = data.get("detail") if isinstance(data, dict) else str(data)
        raise AuthClientError(f"{resp.status_code} {detail}")
    return data if isinstance(data, dict) else {}


def signup(email: str, password: str) -> Dict[str, Any]:
    return _request("POST", "/signup", {"email": email, "password": password})


def login(email: str, password: str) -> Dict[str, Any]:
    return _request("POST", "/login", {"email": email, "password": password})


def validate_token(token: str) -> Dict[str, Any]:
    return _request("POST", "/validate-token", {"token": token})


def save_session(token: str, user: Dict[str, Any]) -> None:
    payload = {"token": token, "user": user}
    SESSION_FILE.write_text(json.dumps(payload, indent=2), encoding="utf-8")


def load_session() -> Dict[str, Any]:
    if not SESSION_FILE.exists():
        return {}
    try:
        return json.loads(SESSION_FILE.read_text(encoding="utf-8"))
    except Exception:
        return {}


def clear_session() -> None:
    if SESSION_FILE.exists():
        SESSION_FILE.unlink()

