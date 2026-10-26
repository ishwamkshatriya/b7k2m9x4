# Technical architecture

```text
                  ┌──────────────────────────────┐
                  │ React + Vite dashboard       │
                  │ filters · charts · CSV       │
                  └──────────────┬───────────────┘
                                 │ same-origin /api/v1/*
                  ┌──────────────▼───────────────┐
                  │ FastAPI                      │
                  │ typed response schemas       │
                  └──────────────┬───────────────┘
                                 │
                  ┌──────────────▼───────────────┐
                  │ Analysis service             │
                  │ cutoff selector · join       │
                  │ hourly actual aggregation    │
                  │ metrics · coverage           │
                  └──────────────┬───────────────┘
                                 │
                  ┌──────────────▼───────────────┐
                  │ versioned data/snapshot.json │
                  │ forecast + actual raw rows   │
                  └──────────────▲───────────────┘
                                 │ one-off ingestion
                  ┌──────────────┴───────────────┐
                  │ scripts/refresh_snapshot.py  │
                  └───────────┬──────────┬───────┘
                              │          │
                       WINDFOR stream  FUELHH stream
                       publication     settlement dates,
                       time window     fuelType=WIND
```

## Key boundaries

- `scripts/refresh_snapshot.py` performs upstream HTTP requests, validates the response shape, records query parameters and retrieval time, and uses an atomic write to avoid replacing a good snapshot with a failed fetch.
- `analysis.py` contains pure functions for timestamp parsing, cutoff selection, hourly actual aggregation, error metrics, daily metrics and coverage. It does not perform network I/O.
- `main.py` exposes the API routes and maps invalid inputs into a consistent JSON 400 error.
- `schemas.py` defines the public response contract and drives the generated OpenAPI schema.
- The frontend is intentionally API-driven. It does not reproduce the forecast selection or metric formulas in JavaScript.

## Analytical sequence

1. Create every hourly delivery start for each decision date's next local calendar day.
2. Convert the configured `HH:MM` decision cutoff in `Europe/London` into UTC.
3. Filter WINDFOR versions to `publishTime <= cutoff` before selecting the maximum publication time.
4. Resolve conflicting values only at that winning publication timestamp. If the latest eligible value is invalid, do not fall back to an older version.
5. For each hour, select the latest FUELHH vintage for both `startTime = hour` and `startTime = hour + 30 minutes`.
6. Require both actual values and average them to form the hourly actual. If either half-hour is unavailable or conflicting, the hourly actual is not considered valid.
7. Calculate metrics only across valid pairs; keep all expected slots in the response so missing data stays visible.

## Deployable form

The multi-stage Dockerfile builds the Vite SPA and copies its output into FastAPI's static directory. The production app therefore serves the UI and JSON API from one origin and does not require production CORS. In development, Vite proxies API calls to `localhost:8000`.
