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

Then open `http://localhost:8080/dashboard.html` or `http://localhost:8080/screening.html`.

The standalone screening exercise keeps answers in page memory only and clears them when the page is closed or refreshed. It does not expose the caregiver dashboard, store typed answers, or identify the participant. The exercise is not a diagnosis.
