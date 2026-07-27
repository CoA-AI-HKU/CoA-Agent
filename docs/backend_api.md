# CoA backend API

The CoA-Agent web API is a single FastAPI app (`backend.main:app`). It wraps
the existing shared conversation processor used by Nanobot, and also mounts
the reminder/auth/patient/emergency routes from `src.reminders.app` — there
is only one backend process, not a separate reminder service. Start it on
loopback with:

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

The reminder, account, patient, and emergency routes the webpage uses are
served from the same process (port 8081) — no second port to run. Nginx is
the single browser-facing origin and proxies everything to that one backend.
See `deploy/nginx/coa-agent.conf`.
