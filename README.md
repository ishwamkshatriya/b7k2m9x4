# Wind Intelligence — January 2026 forecast analysis

A React + FastAPI pilot dashboard for comparing Elexon's national wind-generation forecasts with actual wind outturn around day-ahead purchasing decisions.

> \*\*Data status:\*\* The included `data/snapshot.json` contains the historical Elexon data retrieved for the January 2026 analysis: 20,440 WINDFOR forecast records and 1,488 FUELHH actual WIND records. The forecast dataset provides hourly delivery timestamps, while the actual dataset provides half-hourly observations. The application compares each hourly forecast with the mean of its two corresponding half-hourly actual values, requiring both actual observations. The default 12:00 Europe/London decision cutoff is an illustrative assumption, not a confirmed market deadline. Forecast eligibility and analytical coverage are reported separately in the dashboard.



## What it does

* Retrieves historical WINDFOR forecast versions and FUELHH actual generation records filtered to `fuelType=WIND`.
* Treats January 1–31, 2026 as the **purchasing decision dates** and maps each decision date to the following local calendar day for delivery. The January 31 decision therefore covers February 1 delivery.
* Selects the latest forecast publication with `publishTime <= decision cutoff` for each hourly delivery slot; later versions are never substituted.
* Compares the hourly forecast with the arithmetic mean of the two half-hour actual observations in that hour. Both half-hour actuals are required. The hourly-to-half-hourly mapping is an explicit analytical assumption because WINDFOR observations returned by the feasibility probe are hourly and FUELHH observations are half-hourly.
* Reports MAE, RMSE, signed bias, maximum absolute error, P90/P95 absolute error, data coverage, missing intervals, invalid records, and conflicting winning versions.
* Keeps retrieval availability separate from analytical completeness. Missing values are never converted to zero.
* Provides a detailed interval table, CSV export, API health endpoint, and a forecast-publication diagnostics endpoint.

## Known assumptions and limitations

1. **Decision cutoff:** the UI defaults to `12:00 Europe/London` only as an illustrative demo assumption. The challenge does not specify the utility's exact cutoff. Change it in the UI before examining the headline metrics if the business confirms another time. Do not describe 12:00 as a verified market deadline.
2. **Forecast grid:** the observed WINDFOR data has hourly target timestamps. Actual FUELHH data is half-hourly. This application compares hourly forecasts with the mean of both half-hour actuals in each hour. That mapping must be described in any demo; it is not asserted to be the only possible method.
3. **Actual revisions:** FUELHH versions are selected by the latest available `publishTime` per half-hour start timestamp. The resulting vintage count is retained for diagnostics.
4. **Population:** Elexon describes the wind forecast as covering wind farms visible to NESO with operational metering. Actual fuel-type outturn may cover a somewhat different population, which can affect measured bias.
5. **Generation units:** Elexon's wind-generation page describes the forecast values in MW. The sample API records themselves do not include a separate unit field.
6. **Snapshot vs. live:** the browser reads a local JSON snapshot served by FastAPI. It does not call Elexon from the browser on each page view. This reduces rate-limit exposure and makes the submitted analysis reproducible. Refresh the snapshot deliberately with the script below.

## Technology

* **Frontend:** React 19, Vite, custom SVG charts and responsive CSS.
* **Backend:** Python 3.12, FastAPI, Uvicorn.
* **Data ingestion:** Python standard-library HTTP client (`urllib`) with explicit timeouts and JSON validation.
* **Tests:** pytest and FastAPI TestClient.
* **Packaging:** Docker multi-stage build; the production image serves the compiled React app and FastAPI API from one origin.
* **CI:** GitHub Actions runs the backend tests and frontend production build.

## Repository map

```text
.
├── backend/
│   ├── app/
│   │   ├── main.py                 # FastAPI routes, health, API validation, static serving
│   │   └── services/analysis.py     # forecast selection, interval join, metrics, data-quality flags
│   ├── requirements.txt
│   ├── requirements-dev.txt
│   └── tests/                       # metric, cutoff, grain-mapping, and API tests
├── frontend/
│   ├── src/App.jsx                  # dashboard, controls, table and CSV export
│   ├── src/components/              # SVG forecast and daily-error charts
│   ├── src/styles.css               # responsive application styling
│   ├── package.json
│   └── vite.config.js                # local /api proxy
├── data/snapshot.json               # deployable snapshot; starter file is explicitly incomplete
├── docs/data-feasibility.md         # actual API feasibility report from the probe
├── reports/                         # small source samples and probe metadata, not a full dataset
├── scripts/refresh\_snapshot.py      # retrieve and validate the full target dataset
├── scripts/api\_probe.py             # small repeatable API probe used in feasibility work
├── .github/workflows/ci.yml
├── Dockerfile
└── docker-compose.yml
```

## 1\. Refresh and validate the actual data

Use Python 3.12 or a compatible modern Python version. Run from the repository root:

```bash
python scripts/refresh\_snapshot.py
```

The script performs two bounded requests:

* `WINDFOR/stream`, filtered by publication-time range starting `2025-12-28T00:00:00Z` and ending `2026-01-31T23:59:59Z`.
* `FUELHH/stream`, filtered to `fuelType=WIND` and settlement dates from `2026-01-02` through `2026-02-01`.

It writes actual API records to `data/snapshot.json` atomically, retaining the query parameters and validation metadata. If either upstream request fails, the existing snapshot is not overwritten. The console report distinguishes expected hourly forecast slots from half-hour actual slots. A completed retrieval is **not** proof that every decision-time forecast is eligible or that every comparison is paired; the dashboard calculates those separately.

The date range can be inspected explicitly:

```bash
python scripts/refresh\_snapshot.py --decision-start 2026-01-01 --decision-end 2026-01-31
```

Do not commit a snapshot marked as a sample fixture and present it as a complete analysis. After refresh, review the generated validation fields and dashboard coverage before recording the demo.

## 2\. Run locally without Docker

### Backend

```bash
python -m venv .venv
# Windows PowerShell:
.venv\\Scripts\\Activate.ps1
# macOS/Linux:
# source .venv/bin/activate
pip install -r backend/requirements-dev.txt
$env:PYTHONPATH = "backend"  # Windows PowerShell
# macOS/Linux: export PYTHONPATH=backend
uvicorn app.main:app --app-dir backend --reload --port 8000
```

API docs: [http://localhost:8000/docs](http://localhost:8000/docs)  
Health: [http://localhost:8000/api/v1/health](http://localhost:8000/api/v1/health)

### Frontend

In another terminal:

```bash
cd frontend
npm install
npm run dev
```

Open [http://localhost:5173](http://localhost:5173). Vite proxies `/api` requests to FastAPI at `http://localhost:8000`. If your backend uses another port, set `VITE\_DEV\_API\_TARGET` before starting Vite.

### Tests

From the repository root with the virtual environment active:

```bash
# Windows PowerShell
$env:PYTHONPATH = "backend"
pytest -q backend/tests

# macOS/Linux
# PYTHONPATH=backend pytest -q backend/tests
```

The tests use deterministic fixtures and do not require live API access. They cover cutoff selection, future-version exclusion, missing/invalid values, conflict handling, hourly actual aggregation, the January 31 → February 1 delivery boundary, metric math, and API errors.

## 3\. Docker

Refresh `data/snapshot.json` first if you need real dashboard results, then run:

```bash
docker compose up --build
```

Open [http://localhost:8000](http://localhost:8000). Docker builds the React app and copies the compiled assets into the FastAPI image; the API and SPA are served from one origin. Stop with `Ctrl+C` or `docker compose down`.

## API contract

* `GET /api/v1/health` — process and snapshot state.
* `GET /api/v1/config` — configured range, timezone, step sizes, and cutoff assumption.
* `GET /api/v1/analysis?startDecisionDate=2026-01-01\&endDecisionDate=2026-01-31\&cutoffTime=12:00` — interval rows, metrics, daily metrics, coverage, and data-quality diagnostics.
* `GET /api/v1/diagnostics/forecast-versions?deliveryStartUtc=2026-01-02T00:00:00Z\&cutoffUtc=2026-01-01T12:00:00Z` — all loaded forecast versions for an hourly slot with eligibility flags.

All API timestamps are normalized to UTC for comparison. The decision cutoff is created in `Europe/London`. Dates outside January 2026 are rejected because this is a challenge-scoped pilot.

## Metrics

For valid paired hourly observations, `error = forecast − actual`.

* **MAE:** average absolute error.
* **RMSE:** square root of mean squared error.
* **Bias:** average signed error; positive means overforecast, negative means underforecast.
* **Maximum absolute error:** largest individual miss.
* **P90/P95 absolute error:** linearly interpolated percentiles of absolute error.
* **Coverage:** separately reports eligible forecasts, complete hourly actuals, paired hourly comparisons, and raw half-hour actual coverage.

Only valid paired observations contribute to error metrics. Numeric zero and negative source values are not automatically rejected; missing and invalid observations remain distinct.

## Deployment

A public deployment has **not** been created by this package. After refreshing and committing the snapshot, one deployment path that satisfies the challenge's hosting options is a Docker-container deployment to Heroku. Build and release using the Heroku CLI:

```bash
heroku login
heroku create --stack container <anonymous-app-name>
heroku container:push web --app <anonymous-app-name>
heroku container:release web --app <anonymous-app-name>
heroku open --app <anonymous-app-name>
```

The Docker image binds to Heroku's supplied `$PORT`. Verify the live URL, `/api/v1/health`, chart coverage, and CSV export. Replace the deployment URL below with the real public URL after deployment.

**Deployment URL:** Pending deployment — replace before submission.

Before submission, open the deployed app and every URL included in the submission form in an incognito/private browser session, as required by the challenge. Do not submit while the deployment URL is still pending.

## GitHub submission checklist

Use a neutral, anonymous repository name (for example a short random string), as required by the challenge. Do not falsify commit authorship; simply check that the repository name and visible project metadata follow the anonymity requirement.

```bash
git init
git add .
git commit -m "Build wind forecast analysis pilot"
git branch -M main
git remote add origin https://github.com/<account>/<anonymous-repo-name>.git
git push -u origin main
```

Keep `data/snapshot.json` in the repository after refreshing it, so the deployed analysis uses the same repeatable data version as the submitted code. Review the file size and contents before committing.

## Demo video plan (maximum 10 minutes)

1. **Customer walkthrough (\~4:30):** business problem, chosen illustrative cutoff, forecast-vs-actual chart, MAE/RMSE/bias, coverage and one large miss. Do not describe the assumed cutoff as an official market deadline.
2. **Technical walkthrough (\~4:30):** React/FastAPI/Docker architecture, the two sources, vintage selection, hourly/half-hourly aggregation assumption, missing-data handling, tests, GitHub Actions, and deployment.

Show actual computed values only after the full snapshot has been refreshed. Use the coverage panel to qualify the conclusions.

## AI-tool disclosure

AI tools were used during development and must be disclosed in the submission:

* **ChatGPT (OpenAI):** architecture and requirements analysis, implementation planning, code drafting, and debugging assistance.
* **Codex (OpenAI):** API feasibility probe work and coding-agent assistance.
* **Claude (Anthropic):** independent review of the architecture and data-grain assumptions.

All API observations must be traceable to the included feasibility report and snapshot metadata. AI-generated code and interpretations were checked with automated tests and source-data validation; the business cutoff and hourly-to-half-hourly comparison rule remain explicit assumptions.

## Sources

* [Elexon Insights — Wind generation](https://bmrs.elexon.co.uk/wind-generation): hourly forecast description, forecast update schedule, and MW values.
* [WINDFOR stream API documentation](https://bmrs.elexon.co.uk/api-documentation/endpoint/datasets/WINDFOR/stream).
* [FUELHH stream API documentation](https://bmrs.elexon.co.uk/api-documentation/endpoint/datasets/FUELHH/stream).
* [Elexon Insights developer portal](https://developer.data.elexon.co.uk/).
* See [`docs/data-feasibility.md`](docs/data-feasibility.md) for the recorded request results and remaining limitations.

