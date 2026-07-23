# Web voice chat

The homepage keeps the conversation text-based. Browser speech recognition converts microphone input to an editable transcript. Only the confirmed transcript is sent as JSON to `POST /api/chat`; microphone audio is never submitted or stored by CoA-Agent.

`/api/chat` calls `backend.services.conversation.process_user_message`, which delegates to the existing `ConversationService` and `handle_incoming_message` pipeline. This preserves the established server-side identity lookup, safety routing, intent routing, RAG/agent execution, response formatting, and structured event logging. Browser fields cannot grant a caregiver or administrator role.

The API returns only `reply`, `language`, and `session_id`. The browser displays `reply` first, then derives optional audio from that exact text with `speechSynthesis`. Audio is neither generated nor stored on the server. Browser speech recognition and synthesis availability and processing behavior depend on the browser and device.

The current `web-demo-user` identity and random in-memory browser session ID are prototypes. Replace them with authenticated server sessions before production use. Neither the automatic-playback preference nor conversation data is written to browser storage.

## Local testing

Install the existing project requirements, then start the API on loopback only:

```bash
python3 -m pip install -r requirements.txt
uvicorn src.web_api:app --host 127.0.0.1 --port 8081
```

For a same-origin local test, proxy `/api/` to port 8081. To test separate local origins, temporarily set `API_BASE_URL` in `index.html` to `http://localhost:8081`, set an exact allowed origin, and serve the static files:

```bash
COA_WEB_ALLOWED_ORIGINS=http://localhost:8080 \
  uvicorn src.web_api:app --host 127.0.0.1 --port 8081
python3 -m http.server 8080 --bind 127.0.0.1
```

The committed `API_BASE_URL` is empty for same-origin deployment. Do not commit a host-specific IP address.

An SSH tunnel can expose both loopback test ports locally:

```bash
ssh -L 8080:127.0.0.1:8080 -L 8081:127.0.0.1:8081 root@DROPLET_IP
```

## Production deployment

Use HTTPS and keep Uvicorn bound to `127.0.0.1`. Nginx should serve `index.html` and proxy `/api/*` to the loopback API. Do not expose the development server directly to the internet.

If the frontend is hosted separately, such as on GitHub Pages, set `API_BASE_URL` to the API's HTTPS origin and set `COA_WEB_ALLOWED_ORIGINS` to the exact deployed frontend origin (for example, `https://ako-saka.github.io`). Multiple exact origins may be comma-separated. Wildcard CORS is deliberately ignored; never use `Access-Control-Allow-Origin: *` in production. An HTTPS page must not call an HTTP API.
