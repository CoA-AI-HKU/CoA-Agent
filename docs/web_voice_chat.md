# Web voice chat

The homepage keeps the conversation text-based. Browser speech recognition converts microphone input to an editable transcript. Only the confirmed transcript is sent as JSON to `POST /api/chat`; microphone audio is never submitted or stored by CoA-Agent.

`/api/chat` calls `backend.services.conversation.process_user_message`, which delegates to the existing `ConversationService` and `handle_incoming_message` pipeline. This preserves the established server-side identity lookup, safety routing, intent routing, RAG/agent execution, response formatting, and structured event logging. Browser fields cannot grant a caregiver or administrator role.

The API returns only `reply`, `language`, and `session_id`. The browser displays `reply` first, then derives optional audio from that exact text with `speechSynthesis`. Audio is neither generated nor stored on the server. Browser speech recognition and synthesis availability and processing behavior depend on the browser and device.

The current `web-demo-user` identity and random in-memory browser session ID are prototypes. Replace them with authenticated server sessions before production use. Neither the automatic-playback preference nor conversation data is written to browser storage.

## Local testing

Install the existing project requirements, then start the API on loopback only:

```bash
python3 -m pip install -r requirements.txt
uvicorn backend.main:app --host 127.0.0.1 --port 8081
```

The supported setup uses Nginx so the frontend always requests the relative URL
`/api/chat`. Nginx proxies that one endpoint to port 8081 and sends reminder,
authentication, patient, and emergency paths to the separate reminder service
on port 8001.

```bash
uvicorn backend.main:app --host 127.0.0.1 --port 8081
cd reminder_backend && ../.venv/bin/uvicorn app:app --host 127.0.0.1 --port 8001
```

The committed frontend uses relative URLs and contains no host-specific IP address.

An SSH tunnel can expose both loopback test ports locally:

```bash
ssh -L 8080:127.0.0.1:8080 root@DROPLET_IP
```

## Production deployment

Use HTTPS and keep both Uvicorn processes bound to `127.0.0.1`. Nginx should
serve the static page, proxy only `/api/chat` to the CoA-Agent API, and proxy
`/api/reminders`, `/api/auth`, `/api/patients`, `/api/patient`, and
`/api/emergency` to the reminder backend. Do not publicly expose either Uvicorn
process.

If the frontend is hosted separately, both APIs need exact-origin CORS and HTTPS.
Do not use wildcard CORS or call an HTTP API from an HTTPS page.
