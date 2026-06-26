# VICA Auth API (Local First)

This service handles sign-up, login, and session token validation.

It runs independently from MQTT and `Network/server.py`.

## 1) Install

From `Host_Team/auth_api`:

```powershell
python -m pip install -r requirements.txt
```

## 2) Run (SQLite local)

No environment variable needed.

```powershell
python -m uvicorn app:app --host 0.0.0.0 --port 8001 --reload
```

It will create `auth_local.db` in this folder.

## 3) Test quickly

Health:

```powershell
curl http://127.0.0.1:8001/health
```

Signup:

```powershell
curl -X POST http://127.0.0.1:8001/signup ^
  -H "Content-Type: application/json" ^
  -d "{\"email\":\"test@example.com\",\"password\":\"Password123!\"}"
```

Login:

```powershell
curl -X POST http://127.0.0.1:8001/login ^
  -H "Content-Type: application/json" ^
  -d "{\"email\":\"test@example.com\",\"password\":\"Password123!\"}"
```

Validate token:

```powershell
curl -X POST http://127.0.0.1:8001/validate-token ^
  -H "Content-Type: application/json" ^
  -d "{\"token\":\"PASTE_TOKEN_HERE\"}"
```

## 4) Switch to PostgreSQL later

Set:

```powershell
$env:DATABASE_URL="postgresql://username:password@localhost:5432/vica_auth"
```

Then run Uvicorn again. Tables auto-create on startup.

## Notes

- You can run this on the same machine as host GUI and `Network/server.py`.
- Keep ports distinct (`8001` for auth API, `1883` for MQTT broker).
