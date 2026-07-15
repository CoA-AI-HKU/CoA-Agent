# CoA Care Web

The caregiver dashboard is served by the project's lightweight Python server. Its API uses the same `MetricsCollector`, `InsightGenerator`, registered accounts, and privacy-filtered event log as the Streamlit dashboard and Telegram/WhatsApp message router.

The caregiver dashboard and potential-patient screening experience are deliberately separate. Neither page links to or passes identity into the other.

Pages:

- `dashboard.html` — live caregiver dashboard
- `screening.html` — instructed five-step exercise with an interactive 10:50 clock task
- `check.html` — compatibility redirect to the screening exercise

Start the integrated server from the project root:

```powershell
python -m src.web_server
```

The screening page can be opened at `http://localhost:8080/screening.html`. The caregiver dashboard requires the short-lived private link issued through the paired caregiver's Telegram/WhatsApp conversation; opening `dashboard.html` without a valid link does not expose patient accounts.

The standalone screening exercise keeps answers in page memory only and clears them when the page is closed or refreshed. It does not expose the caregiver dashboard, store typed answers, or identify the participant. The exercise is not a diagnosis.

Account registration, caregiver pairing, chat-history controls, and screening invitations are handled privately inside the Telegram/WhatsApp RAG conversation. They are deliberately not part of the website or caregiver dashboard. See the project-level `README.md` for those features.
