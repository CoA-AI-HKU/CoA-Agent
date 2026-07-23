# Telegram development client

This optional adapter long-polls Telegram, sends each text message to the CoA REST API, and displays the returned response. It contains no routing, RAG, safety, or account logic.

Set `TELEGRAM_BOT_TOKEN`, the same strong `COA_SERVICE_TOKEN` configured on the backend, and optionally `COA_BACKEND_URL`, then run `python -m clients.telegram.telegram_adapter`.
