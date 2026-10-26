#!/usr/bin/env python3
"""Fetch the January 2026 decision-analysis snapshot from Elexon.

Run this from the project root on a machine that can reach data.elexon.co.uk:
    python scripts/refresh_snapshot.py

The script saves only genuine upstream responses. If retrieval or validation
fails, it will not overwrite the existing data/snapshot.json.
"""
from __future__ import annotations

import argparse
import json
import math
import os
import sys
import tempfile
from datetime import date, datetime, time, timedelta, timezone
from pathlib import Path
from typing import Any
from urllib.parse import urlencode
from urllib.request import Request, urlopen
from urllib.error import HTTPError, URLError
from zoneinfo import ZoneInfo

BASE = "https://data.elexon.co.uk/bmrs/api/v1/datasets"
ROOT = Path(__file__).resolve().parents[1]
OUTPUT = ROOT / "data" / "snapshot.json"
LONDON = ZoneInfo("Europe/London")
UTC = timezone.utc


def request_json(endpoint: str, params: list[tuple[str, str]], timeout: int = 60) -> list[dict[str, Any]]:
    url = f"{BASE}/{endpoint}/stream?{urlencode(params)}"
    req = Request(url, headers={"Accept": "application/json", "User-Agent": "wind-intelligence-challenge/1.0"}, method="GET")
    try:
        with urlopen(req, timeout=timeout) as response:
            status = response.status
            content_type = response.headers.get("Content-Type", "")
            body = response.read()
    except HTTPError as exc:
        details = exc.read(1500).decode("utf-8", errors="replace")
        raise RuntimeError(f"Elexon returned HTTP {exc.code} for {endpoint}: {details}") from exc
    except (URLError, TimeoutError, OSError) as exc:
        raise RuntimeError(f"Could not reach Elexon for {endpoint}: {exc}") from exc
    if status != 200:
        raise RuntimeError(f"Elexon returned unexpected HTTP {status} for {endpoint}")
    try:
        payload = json.loads(body.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise RuntimeError(f"Elexon returned invalid JSON for {endpoint}; content type was {content_type!r}") from exc
    if not isinstance(payload, list) or any(not isinstance(row, dict) for row in payload):
        raise RuntimeError(f"Expected a JSON array of records from {endpoint}; observed {type(payload).__name__}")
    print(f"{endpoint}: HTTP {status}; {len(payload):,} rows; {len(body):,} bytes; {content_type}")
    return payload


def parse_utc(value: Any) -> datetime | None:
    if not isinstance(value, str):
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=UTC)
    return parsed.astimezone(UTC)


def unique_start_times(rows: list[dict[str, Any]]) -> set[str]:
    values = set()
    for row in rows:
        parsed = parse_utc(row.get("startTime"))
        if parsed is not None:
            values.add(parsed.isoformat(timespec="seconds").replace("+00:00", "Z"))
    return values


def expected_starts(start_day: date, end_day: date, minutes: int) -> set[str]:
    result: set[str] = set()
    day = start_day
    while day <= end_day:
        start_local = datetime.combine(day, time.min, tzinfo=LONDON)
        end_local = datetime.combine(day + timedelta(days=1), time.min, tzinfo=LONDON)
        current = start_local.astimezone(UTC)
        end = end_local.astimezone(UTC)
        while current < end:
            result.add(current.isoformat(timespec="seconds").replace("+00:00", "Z"))
            current += timedelta(minutes=minutes)
        day += timedelta(days=1)
    return result


def atomic_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary = tempfile.mkstemp(prefix="snapshot-", suffix=".json", dir=str(path.parent))
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            json.dump(payload, handle, indent=2, ensure_ascii=False, allow_nan=False)
            handle.write("\n")
        os.replace(temporary, path)
    except Exception:
        try:
            os.unlink(temporary)
        except OSError:
            pass
        raise


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--decision-start", default="2026-01-01", help="First purchasing decision date (inclusive).")
    parser.add_argument("--decision-end", default="2026-01-31", help="Last purchasing decision date (inclusive).")
    parser.add_argument("--output", default=str(OUTPUT), help="Snapshot JSON output path.")
    parser.add_argument("--timeout", type=int, default=60)
    args = parser.parse_args()
    try:
        decision_start = date.fromisoformat(args.decision_start)
        decision_end = date.fromisoformat(args.decision_end)
    except ValueError as exc:
        print(f"Invalid date: {exc}", file=sys.stderr)
        return 2
    if decision_start > decision_end or decision_start < date(2026, 1, 1) or decision_end > date(2026, 1, 31):
        print("Decision range must be within 2026-01-01 through 2026-01-31.", file=sys.stderr)
        return 2

    delivery_start = decision_start + timedelta(days=1)
    delivery_end = decision_end + timedelta(days=1)
    # The publication window begins before the first decision to retain earlier
    # forecast versions. The selector locally enforces each decision cutoff.
    wind_params = [
        ("publishDateTimeFrom", "2025-12-28T00:00:00Z"),
        ("publishDateTimeTo", "2026-01-31T23:59:59Z"),
    ]
    fuel_params = [
        ("settlementDateFrom", delivery_start.isoformat()),
        ("settlementDateTo", delivery_end.isoformat()),
        ("fuelType", "WIND"),
    ]
    try:
        forecast_records = request_json("WINDFOR", wind_params, args.timeout)
        actual_records = request_json("FUELHH", fuel_params, args.timeout)
    except RuntimeError as exc:
        print(f"SNAPSHOT NOT UPDATED: {exc}", file=sys.stderr)
        return 1

    expected_hourly = expected_starts(delivery_start, delivery_end, 60)
    expected_half_hour = expected_starts(delivery_start, delivery_end, 30)
    forecast_starts = unique_start_times(forecast_records) & expected_hourly
    actual_starts_all = unique_start_times([r for r in actual_records if str(r.get("fuelType", "")).upper() == "WIND"])
    actual_starts = actual_starts_all & expected_half_hour
    missing_actuals = sorted(expected_half_hour - actual_starts)
    missing_forecast_start_times = sorted(expected_hourly - forecast_starts)
    duplicate_forecast_rows = len(forecast_records) - len({json.dumps(r, sort_keys=True, separators=(",", ":")) for r in forecast_records})
    filtered_actuals = [r for r in actual_records if str(r.get("fuelType", "")).upper() == "WIND"]
    duplicate_actual_rows = len(filtered_actuals) - len({json.dumps(r, sort_keys=True, separators=(",", ":")) for r in filtered_actuals})
    invalid_forecast_fields = sum(1 for r in forecast_records if parse_utc(r.get("publishTime")) is None or parse_utc(r.get("startTime")) is None or not isinstance(r.get("generation"), (int, float)) or isinstance(r.get("generation"), bool) or not math.isfinite(float(r.get("generation", 0))))
    invalid_actual_fields = sum(1 for r in filtered_actuals if parse_utc(r.get("publishTime")) is None or parse_utc(r.get("startTime")) is None or not isinstance(r.get("generation"), (int, float)) or isinstance(r.get("generation"), bool) or not math.isfinite(float(r.get("generation", 0))))

    retrieved_at = datetime.now(UTC).isoformat(timespec="seconds").replace("+00:00", "Z")
    data = {
        "schemaVersion": 1,
        "retrievalMode": "elexon_snapshot",
        "complete": True,
        "retrievedAtUtc": retrieved_at,
        "decisionStartDate": decision_start.isoformat(),
        "decisionEndDate": decision_end.isoformat(),
        "deliveryStartDate": delivery_start.isoformat(),
        "deliveryEndDate": delivery_end.isoformat(),
        "unit": "MW",
        "sourceUrls": {
            "WINDFOR": f"{BASE}/WINDFOR/stream",
            "FUELHH": f"{BASE}/FUELHH/stream",
        },
        "queryParameters": {"WINDFOR": dict(wind_params), "FUELHH": dict(fuel_params)},
        "validation": {
            "retrievalCompleted": True,
            "expectedForecastSlots": len(expected_hourly),
            "distinctForecastSlotsReturned": len(forecast_starts),
            "missingForecastSlotsBeforeCutoffSelection": len(missing_forecast_start_times),
            "missingForecastSlotExamples": missing_forecast_start_times[:10],
            "expectedActualHalfHours": len(expected_half_hour),
            "distinctActualHalfHoursReturned": len(actual_starts),
            "missingActualHalfHours": len(missing_actuals),
            "missingActualExamples": missing_actuals[:10],
            "duplicateForecastRows": duplicate_forecast_rows,
            "duplicateActualRows": duplicate_actual_rows,
            "invalidForecastRecords": invalid_forecast_fields,
            "invalidActualRecords": invalid_actual_fields,
            "note": "Retrieval completed successfully. Decision-cutoff eligibility and paired data coverage are calculated by the API and may still be partial.",
        },
        "forecastRecords": forecast_records,
        "actualRecords": filtered_actuals,
    }
    atomic_json(Path(args.output).resolve(), data)
    print(f"Snapshot written to: {Path(args.output).resolve()}")
    print(f"Decision dates: {decision_start} through {decision_end}; delivery dates: {delivery_start} through {delivery_end}")
    print(f"Forecast slots: {len(forecast_starts)}/{len(expected_hourly)} distinct hourly starts in target range")
    print(f"Actual half-hours: {len(actual_starts)}/{len(expected_half_hour)} distinct target starts")
    print(f"Missing actual half-hours: {len(missing_actuals)}")
    print("Note: this reports retrieval coverage only. The business cutoff remains configurable and is applied later.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
