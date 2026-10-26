from __future__ import annotations

import json
import os
from datetime import date
from pathlib import Path
from typing import Any

from fastapi import FastAPI, Query
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from app.services.analysis import analyze_snapshot, forecast_versions
from app.schemas import AnalysisResponse, ForecastVersionsResponse

PROJECT_ROOT = Path(__file__).resolve().parents[2]
SNAPSHOT_PATH = Path(os.getenv("SNAPSHOT_PATH", str(PROJECT_ROOT / "data" / "snapshot.json")))
STATIC_DIR = Path(__file__).resolve().parent / "static"

app = FastAPI(
    title="Wind Intelligence API",
    version="1.0.0",
    description=(
        "Historical day-ahead wind forecast analysis for January 2026. "
        "The application explicitly discloses its illustrative cutoff and hourly-to-half-hourly mapping."
    ),
)

origins = [item.strip() for item in os.getenv("CORS_ORIGINS", "http://localhost:5173").split(",") if item.strip()]
if origins:
    app.add_middleware(
        CORSMiddleware,
        allow_origins=origins,
        allow_credentials=False,
        allow_methods=["GET", "OPTIONS"],
        allow_headers=["Accept", "Content-Type"],
    )


@app.exception_handler(RequestValidationError)
async def request_validation_handler(_request, exc: RequestValidationError):
    return JSONResponse(
        status_code=400,
        content={
            "error": "INVALID_REQUEST",
            "message": "One or more query parameters are invalid.",
            "details": exc.errors(),
        },
    )


def _load_snapshot() -> dict[str, Any]:
    if not SNAPSHOT_PATH.exists():
        return {
            "schemaVersion": 1,
            "retrievalMode": "missing_snapshot",
            "complete": False,
            "retrievedAtUtc": None,
            "forecastRecords": [],
            "actualRecords": [],
            "validation": {"note": f"Snapshot file not found at {SNAPSHOT_PATH}"},
        }
    try:
        with SNAPSHOT_PATH.open("r", encoding="utf-8") as handle:
            content = json.load(handle)
    except (OSError, json.JSONDecodeError) as exc:
        return {
            "schemaVersion": 1,
            "retrievalMode": "snapshot_error",
            "complete": False,
            "retrievedAtUtc": None,
            "forecastRecords": [],
            "actualRecords": [],
            "validation": {"note": f"Could not load snapshot: {exc}"},
        }
    if not isinstance(content, dict):
        return {
            "schemaVersion": 1,
            "retrievalMode": "snapshot_error",
            "complete": False,
            "retrievedAtUtc": None,
            "forecastRecords": [],
            "actualRecords": [],
            "validation": {"note": "Snapshot root must be a JSON object."},
        }
    return content


@app.get("/api/v1/health", tags=["System"])
def health() -> dict[str, Any]:
    snapshot = _load_snapshot()
    return {
        "status": "ok",
        "service": "wind-intelligence-api",
        "snapshotLoaded": SNAPSHOT_PATH.exists(),
        "snapshotComplete": bool(snapshot.get("complete", False)),
        "snapshotMode": snapshot.get("retrievalMode", "unknown"),
        "forecastRecords": len(snapshot.get("forecastRecords") or []),
        "actualRecords": len(snapshot.get("actualRecords") or []),
    }


@app.get("/api/v1/config", tags=["System"])
def config() -> dict[str, Any]:
    snapshot = _load_snapshot()
    return {
        "decisionStartDate": "2026-01-01",
        "decisionEndDate": "2026-01-31",
        "defaultCutoffTime": "12:00",
        "decisionTimezone": "Europe/London",
        "cutoffIsDefault": True,
        "cutoffSource": "Illustrative demo assumption; not specified by the challenge.",
        "forecastStepMinutes": 60,
        "actualStepMinutes": 30,
        "comparisonStepMinutes": 60,
        "unit": snapshot.get("unit", "MW"),
        "snapshotMode": snapshot.get("retrievalMode", "unknown"),
        "snapshotComplete": bool(snapshot.get("complete", False)),
    }


@app.get("/api/v1/analysis", tags=["Analysis"], response_model=AnalysisResponse)
def analysis(
    startDecisionDate: date = Query(default=date(2026, 1, 1), description="Inclusive purchasing decision date, January 2026."),
    endDecisionDate: date = Query(default=date(2026, 1, 31), description="Inclusive purchasing decision date, January 2026."),
    cutoffTime: str = Query(default="12:00", pattern=r"^([01]\d|2[0-3]):[0-5]\d$", description="Illustrative local decision cutoff (Europe/London), HH:MM."),
) -> dict[str, Any]:
    snapshot = _load_snapshot()
    try:
        return analyze_snapshot(snapshot, startDecisionDate, endDecisionDate, cutoffTime)
    except ValueError as exc:
        return JSONResponse(status_code=400, content={"error": "INVALID_ANALYSIS_REQUEST", "message": str(exc)})


@app.get("/api/v1/diagnostics/forecast-versions", tags=["Diagnostics"], response_model=ForecastVersionsResponse)
def diagnostics_forecast_versions(
    deliveryStartUtc: str = Query(..., description="Hourly delivery start in UTC, ISO-8601."),
    cutoffUtc: str = Query(..., description="Decision cutoff in UTC, ISO-8601."),
) -> dict[str, Any] | JSONResponse:
    try:
        return forecast_versions(_load_snapshot(), deliveryStartUtc, cutoffUtc)
    except ValueError as exc:
        return JSONResponse(status_code=400, content={"error": "INVALID_DIAGNOSTIC_REQUEST", "message": str(exc)})


# Production Docker images copy Vite's built output here. In local development,
# Vite runs separately and proxies /api to FastAPI.
if STATIC_DIR.exists() and (STATIC_DIR / "index.html").exists():
    app.mount("/", StaticFiles(directory=STATIC_DIR, html=True), name="frontend")
else:
    @app.get("/", include_in_schema=False)
    def root() -> dict[str, str]:
        return {"service": "Wind Intelligence API", "docs": "/docs", "health": "/api/v1/health"}
