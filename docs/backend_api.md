# CoA backend API

The CoA-Agent web API is a single FastAPI app (`backend.main:app`). It wraps
the existing shared conversation processor used by Nanobot. Reminders are
set by talking to the bot (see `src.reminders.chat_reminders`) and delivered
by `src.reminders.scheduler` — there is no reminder REST API or
caregiver-dashboard login. Start the backend on loopback with:

```bash
uvicorn backend.main:app --host 127.0.0.1 --port 8081
```

## Authentication and chat contract

Browser requests use `POST /api/chat` with a verified Firebase ID token in the `Authorization: Bearer ...` header. The server derives the user ID from that verified token; clients cannot supply another user ID.

```json
{
  "message": "Hello",
  "session_id": "browser-session",
  "input_mode": "text"
}
```

The response contains only `reply`, `language`, and `session_id`. `GET /health` reports API availability. The former `/v1/auth`, `/v1/chat`, and `/v1/caregiver` routes have been retired; trusted channel adapters call the shared conversation service internally.

## Blood-pressure records

When a patient sends a reading such as `我今日血壓130 80`, the shared conversation pipeline validates and stores the structured systolic and diastolic values under that patient's canonical user ID. It does not interpret the reading or provide a diagnosis.

An authenticated caregiver can read up to 90 recent records for a linked patient with:

```text
GET /api/me/linked-patients/{patient_user_id}/blood-pressure?limit=30
```

The existing caregiver permission and patient-link checks apply. Unlinked patient IDs are not readable.

Nginx is the single browser-facing origin and proxies `/api/chat` and
`/health` to that one backend. See `deploy/nginx/coa-agent.conf`.
