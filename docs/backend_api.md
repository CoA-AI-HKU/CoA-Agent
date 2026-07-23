# CoA backend API

The REST service is the transport-neutral boundary around the existing CoA orchestrator. Start it with:

```bash
uvicorn backend.main:app --host 127.0.0.1 --port 8000
```

## Authentication

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

The API also provides `GET /health` and caregiver pairing routes under `/v1/caregiver`. Interactive API documentation is available at `/docs`.
