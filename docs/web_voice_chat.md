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

The supported setup uses Nginx so the frontend always requests relative URLs.
Nginx proxies `/api/chat`, `/health`, and the reminder/auth/patient/emergency
paths (`/api/reminders`, `/api/auth`, `/api/patients`, `/api/patient`,
`/api/emergency`) all to the same port-8081 backend — there is only one
Uvicorn process to run.

The committed frontend uses relative URLs and contains no host-specific IP address.

An SSH tunnel can expose the loopback test port locally:

```bash
ssh -L 8080:127.0.0.1:8080 root@DROPLET_IP
```

## Production deployment

Use HTTPS and keep the Uvicorn process bound to `127.0.0.1`. Nginx should
serve the static page and proxy `/api/chat`, `/health`, `/api/reminders`,
`/api/auth`, `/api/patients`, `/api/patient`, and `/api/emergency` to that
one backend. Do not publicly expose the Uvicorn process.

If the frontend is hosted separately, the API needs exact-origin CORS and HTTPS.
Do not use wildcard CORS or call an HTTP API from an HTTPS page.
