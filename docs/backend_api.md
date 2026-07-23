# CoA backend API

The dedicated CoA-Agent web API contains only health and browser chat. It wraps
the existing shared conversation processor used by Nanobot and does not contain
reminder, authentication, or emergency routes. Start it on loopback with:

```bash
uvicorn backend.main:app --host 127.0.0.1 --port 8081
```

## Channel authentication API

Register an account with `POST /v1/auth/register`, or create a session for an existing account with `POST /v1/auth/login`. Both return a 24-hour bearer token. Account tokens can send chat messages only for their own `sender_id`.

Trusted transport adapters such as Telegram use a strong secret supplied as `COA_SERVICE_TOKEN` to the backend and adapter. A service token may relay messages for multiple platform user IDs; it must never be embedded in a browser or mobile app.

## Chat contract

`POST /v1/chat`:

```json
{
  "user_id": "platform-user-id",
  "message": "Hello",
  "platform": "web",
  "metadata": {}
}
```

Response:

```json
{
  "response": "...",
  "tts": "...",
  "events": [],
  "metadata": {"role": "user", "route": "..."}
}
```

The modules under `/v1` remain available for trusted channel integrations but
are not included in the dedicated browser app. The browser-safe `POST /api/chat`
returns only `reply`, `language`, and `session_id`; `GET /health` reports API
availability.

The reminder service remains separate because the current webpage uses its
account, patient, reminder, and emergency features. Start it on another loopback
port:

```bash
cd reminder_backend
../.venv/bin/uvicorn app:app --host 127.0.0.1 --port 8001
```

Nginx is the single browser-facing origin and routes each path to the owning
service. See `deploy/nginx/coa-agent.conf`.
