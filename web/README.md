# CoA Care Web

This folder is a standalone static website. It does not use Astro, Python, Streamlit, a package manager, or a build step.

Pages:

- `dashboard.html` — caregiver dashboard
- `check.html` — five-step non-diagnostic cognitive concern check-in
- `screening.html` — five-step screening exercise with an interactive clock on question 1

There is intentionally no home page and no link between the two pages.

You can double-click either HTML file to open it directly. To load edited values from `dashboard-data.json`, serve the folder with any basic static server:

```powershell
cd web
python -m http.server 8080
```

Then open `http://localhost:8080/dashboard.html` or `http://localhost:8080/check.html`.

The questionnaire stores answers only in page memory and clears them when the page is closed or refreshed. It is not a diagnosis and does not produce a medical score.
