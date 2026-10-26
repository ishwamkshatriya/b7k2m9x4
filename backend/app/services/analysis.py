"""Historical forecast selection and accuracy analysis.

WINDFOR observations are hourly while FUELHH observations are half-hourly.
The chosen comparison policy averages both FUELHH observations in each hour.
This is an explicit and visible modelling assumption, not an Elexon guarantee.
"""
from __future__ import annotations

import math
from collections import defaultdict
from datetime import date, datetime, time, timedelta, timezone
from statistics import mean
from typing import Any, Iterable
from zoneinfo import ZoneInfo

LONDON = ZoneInfo("Europe/London")
UTC = timezone.utc


def parse_datetime(value: Any) -> datetime | None:
    if not isinstance(value, str) or not value.strip():
        return None
    try:
        parsed = datetime.fromisoformat(value.strip().replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=UTC)
    return parsed.astimezone(UTC)


def iso_utc(value: datetime | None) -> str | None:
    if value is None:
        return None
    return value.astimezone(UTC).isoformat(timespec="seconds").replace("+00:00", "Z")


def numeric(value: Any) -> float | None:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    result = float(value)
    return result if math.isfinite(result) else None


def _row_key(row: dict[str, Any]) -> tuple[str | None, str | None, float | None]:
    published = parse_datetime(row.get("publishTime"))
    started = parse_datetime(row.get("startTime"))
    return iso_utc(started), iso_utc(published), numeric(row.get("generation"))


def _dedupe_exact(rows: Iterable[dict[str, Any]]) -> tuple[list[dict[str, Any]], int]:
    seen: set[tuple[Any, ...]] = set()
    result: list[dict[str, Any]] = []
    duplicates = 0
    for row in rows:
        if not isinstance(row, dict):
            continue
        key = tuple(sorted((str(k), repr(v)) for k, v in row.items()))
        if key in seen:
            duplicates += 1
            continue
        seen.add(key)
        result.append(row)
    return result, duplicates


def percentile(values: list[float], quantile: float) -> float | None:
    """Linearly interpolated percentile, defined for any non-empty sample."""
    if not values:
        return None
    ordered = sorted(values)
    if len(ordered) == 1:
        return ordered[0]
    position = (len(ordered) - 1) * quantile
    lower = math.floor(position)
    upper = math.ceil(position)
    if lower == upper:
        return ordered[lower]
    weight = position - lower
    return ordered[lower] * (1 - weight) + ordered[upper] * weight


def calculate_metrics(rows: list[dict[str, Any]]) -> dict[str, Any]:
    pairs = [
        row for row in rows
        if row.get("forecastGeneration") is not None and row.get("actualGeneration") is not None
        and row.get("pairStatus") == "paired"
    ]
    errors = [float(row["forecastGeneration"]) - float(row["actualGeneration"]) for row in pairs]
    absolute = [abs(item) for item in errors]
    if not errors:
        return {
            "n": 0, "mae": None, "rmse": None, "bias": None,
            "maxAbsoluteError": None, "p90AbsoluteError": None,
            "p95AbsoluteError": None,
        }
    return {
        "n": len(errors),
        "mae": mean(absolute),
        "rmse": math.sqrt(mean([item * item for item in errors])),
        "bias": mean(errors),
        "maxAbsoluteError": max(absolute),
        "p90AbsoluteError": percentile(absolute, 0.90),
        "p95AbsoluteError": percentile(absolute, 0.95),
    }


def _latest_actual_by_start(actual_records: list[dict[str, Any]]) -> tuple[dict[datetime, dict[str, Any]], dict[datetime, list[dict[str, Any]]], int]:
    grouped: dict[datetime, list[dict[str, Any]]] = defaultdict(list)
    usable = [r for r in actual_records if isinstance(r, dict) and str(r.get("fuelType", "")).upper() == "WIND"]
    deduped, duplicates = _dedupe_exact(usable)
    for row in deduped:
        start = parse_datetime(row.get("startTime"))
        if start is not None:
            grouped[start].append(row)
    selected: dict[datetime, dict[str, Any]] = {}
    for start, versions in grouped.items():
        published_versions = [(parse_datetime(row.get("publishTime")), row) for row in versions]
        newest_time = max((pub for pub, _ in published_versions if pub is not None), default=None)
        newest = [row for pub, row in published_versions if pub == newest_time]
        if newest_time is None:
            newest = versions
        # Preserve tied rows for conflict detection in downstream logic.
        selected[start] = {
            "_selectedRows": newest,
            "_versionCount": len(versions),
            "_publishTimeValid": newest_time is not None,
        }
    return selected, grouped, duplicates


def analyze_snapshot(
    snapshot: dict[str, Any],
    decision_start: date = date(2026, 1, 1),
    decision_end: date = date(2026, 1, 31),
    cutoff_time: str = "12:00",
) -> dict[str, Any]:
    """Build hourly forecast/actual rows for day-ahead January decisions.

    Decision dates are inclusive. Each decision date maps to the next local
    calendar date for delivery. Forecast values remain on the hourly source
    grid; actuals are the mean of the two half-hour FUELHH observations.
    """
    try:
        hour, minute = (int(part) for part in cutoff_time.split(":"))
        cutoff_clock = time(hour, minute)
    except (ValueError, AttributeError):
        raise ValueError("cutoffTime must use HH:MM format") from None
    if len(cutoff_time.split(":")) != 2 or not (0 <= hour <= 23 and 0 <= minute <= 59):
        raise ValueError("cutoffTime must use a valid 24-hour HH:MM value")
    if decision_start > decision_end:
        raise ValueError("startDecisionDate must be on or before endDecisionDate")
    if decision_start.year != 2026 or decision_start.month != 1 or decision_end.year != 2026 or decision_end.month != 1:
        raise ValueError("Decision dates must be within January 2026 for this challenge")

    forecast_raw = snapshot.get("forecastRecords") or []
    actual_raw = snapshot.get("actualRecords") or []
    forecasts, forecast_dup_count = _dedupe_exact(forecast_raw)
    forecast_by_start: dict[datetime, list[dict[str, Any]]] = defaultdict(list)
    malformed_forecasts = 0
    for row in forecasts:
        start = parse_datetime(row.get("startTime"))
        published = parse_datetime(row.get("publishTime"))
        if start is None or published is None:
            malformed_forecasts += 1
            continue
        forecast_by_start[start].append(row)

    actual_selected, actual_versions_by_start, actual_dup_count = _latest_actual_by_start(actual_raw)
    malformed_actuals = sum(
        1 for r in actual_raw
        if not isinstance(r, dict) or parse_datetime(r.get("startTime")) is None or parse_datetime(r.get("publishTime")) is None
    )

    decision_days: list[date] = []
    cursor_date = decision_start
    while cursor_date <= decision_end:
        decision_days.append(cursor_date)
        cursor_date += timedelta(days=1)

    rows: list[dict[str, Any]] = []
    expected_forecast_slots = 0
    expected_actual_half_hours = 0
    forecast_slots_valid = 0
    actual_hour_slots_valid = 0
    actual_half_hours_valid_set: set[datetime] = set()
    conflict_count = 0

    for decision_day in decision_days:
        delivery_day = decision_day + timedelta(days=1)
        cutoff_local = datetime.combine(decision_day, cutoff_clock, tzinfo=LONDON)
        cutoff_utc = cutoff_local.astimezone(UTC)
        delivery_start_local = datetime.combine(delivery_day, time.min, tzinfo=LONDON)
        delivery_end_local = datetime.combine(delivery_day + timedelta(days=1), time.min, tzinfo=LONDON)
        slot = delivery_start_local.astimezone(UTC)
        delivery_end_utc = delivery_end_local.astimezone(UTC)
        while slot < delivery_end_utc:
            expected_forecast_slots += 1
            expected_actual_half_hours += 2
            candidates = [r for r in forecast_by_start.get(slot, [])
                          if (parse_datetime(r.get("publishTime")) is not None
                              and parse_datetime(r.get("publishTime")) <= cutoff_utc)]
            selected_forecast: dict[str, Any] | None = None
            forecast_value: float | None = None
            forecast_publish: datetime | None = None
            forecast_status = "missing_forecast"
            if candidates:
                max_pub = max(parse_datetime(r.get("publishTime")) for r in candidates if parse_datetime(r.get("publishTime")) is not None)
                winning = [r for r in candidates if parse_datetime(r.get("publishTime")) == max_pub]
                winning_values = [numeric(r.get("generation")) for r in winning]
                if len(set(winning_values)) > 1:
                    forecast_status = "conflict"
                    conflict_count += 1
                    forecast_publish = max_pub
                else:
                    selected_forecast = winning[0]
                    forecast_publish = max_pub
                    candidate_value = numeric(selected_forecast.get("generation"))
                    if candidate_value is None:
                        forecast_status = "invalid_value"
                    else:
                        forecast_status = "ok"
                        forecast_value = candidate_value
                        forecast_slots_valid += 1

            half_starts = (slot, slot + timedelta(minutes=30))
            half_values: list[float] = []
            half_publish_times: list[datetime] = []
            half_vintage_count = 0
            half_statuses: list[str] = []
            for half_start in half_starts:
                selected_actual = actual_selected.get(half_start)
                versions = actual_versions_by_start.get(half_start, [])
                half_vintage_count += len(versions)
                if selected_actual is None:
                    half_statuses.append("missing")
                    continue
                version_rows = selected_actual["_selectedRows"]
                values = [numeric(item.get("generation")) for item in version_rows]
                if len(set(values)) > 1:
                    half_statuses.append("conflict")
                    continue
                if not selected_actual.get("_publishTimeValid", False):
                    half_statuses.append("invalid")
                    continue
                value = values[0] if values else None
                if value is None:
                    half_statuses.append("invalid")
                    continue
                half_values.append(value)
                actual_pub = parse_datetime(version_rows[0].get("publishTime")) if version_rows else None
                if actual_pub is not None:
                    half_publish_times.append(actual_pub)
                actual_half_hours_valid_set.add(half_start)
                half_statuses.append("ok")

            actual_value: float | None = None
            actual_status = "ok"
            if all(item == "ok" for item in half_statuses) and len(half_values) == 2:
                actual_value = mean(half_values)
                actual_hour_slots_valid += 1
            elif "conflict" in half_statuses:
                actual_status = "conflict"
                conflict_count += 1
            elif "invalid" in half_statuses:
                actual_status = "invalid_value"
            else:
                actual_status = "missing_actual"

            if forecast_status == "ok" and actual_status == "ok":
                pair_status = "paired"
            elif forecast_status == "conflict" or actual_status == "conflict":
                pair_status = "conflict"
            elif forecast_status == "invalid_value" or actual_status == "invalid_value":
                pair_status = "invalid_value"
            elif forecast_status != "ok" and actual_status != "ok":
                pair_status = "missing_both"
            elif forecast_status != "ok":
                pair_status = "missing_forecast"
            else:
                pair_status = "missing_actual"

            lead_minutes = None
            if forecast_publish is not None:
                lead_minutes = (slot - forecast_publish).total_seconds() / 60
            error = (forecast_value - actual_value) if pair_status == "paired" else None
            rows.append({
                "decisionDate": decision_day.isoformat(),
                "deliveryDate": delivery_day.isoformat(),
                "deliveryStartUtc": iso_utc(slot),
                "deliveryStartLocal": slot.astimezone(LONDON).isoformat(timespec="minutes"),
                "decisionCutoffUtc": iso_utc(cutoff_utc),
                "forecastPublishTimeUtc": iso_utc(forecast_publish),
                "forecastGeneration": forecast_value,
                "forecastStatus": forecast_status,
                "forecastLeadTimeMinutes": lead_minutes,
                "actualGeneration": actual_value,
                "actualStatus": actual_status,
                "actualPublishTimeUtc": iso_utc(max(half_publish_times)) if half_publish_times else None,
                "actualVintageCount": half_vintage_count,
                "actualHalfHourValues": half_values if len(half_values) == 2 else None,
                "error": error,
                "absoluteError": abs(error) if error is not None else None,
                "pairStatus": pair_status,
            })
            slot += timedelta(hours=1)

    metrics = calculate_metrics(rows)
    expected_comparisons = len(rows)
    paired = metrics["n"]
    forecast_cov = 100.0 * forecast_slots_valid / expected_forecast_slots if expected_forecast_slots else 0.0
    actual_cov = 100.0 * actual_hour_slots_valid / expected_comparisons if expected_comparisons else 0.0
    pair_cov = 100.0 * paired / expected_comparisons if expected_comparisons else 0.0
    raw_actual_cov = 100.0 * len(actual_half_hours_valid_set) / expected_actual_half_hours if expected_actual_half_hours else 0.0

    daily: list[dict[str, Any]] = []
    for day in decision_days:
        day_rows = [row for row in rows if row["decisionDate"] == day.isoformat()]
        day_metrics = calculate_metrics(day_rows)
        day_metrics.update({
            "decisionDate": day.isoformat(),
            "deliveryDate": (day + timedelta(days=1)).isoformat(),
            "expectedComparisons": len(day_rows),
            "forecastValid": sum(row["forecastStatus"] == "ok" for row in day_rows),
            "actualValid": sum(row["actualStatus"] == "ok" for row in day_rows),
            "pairedCoveragePct": 100.0 * day_metrics["n"] / len(day_rows) if day_rows else 0.0,
        })
        daily.append(day_metrics)

    snapshot_validation = snapshot.get("validation") or {}
    snapshot_mode = snapshot.get("retrievalMode", "unknown")
    sample_fixture = snapshot_mode == "sample_fixture"
    retrieval_complete = bool(snapshot.get("complete", False))
    messages: list[str] = []
    if sample_fixture:
        messages.append("This package contains only three sample records per source. Run scripts/refresh_snapshot.py before interpreting the dashboard as a January-wide analysis.")
    elif snapshot_mode in {"missing_snapshot", "snapshot_error"}:
        messages.append(str(snapshot_validation.get("note", "The data snapshot is missing or could not be loaded.")))
    elif not retrieval_complete:
        messages.append("The data snapshot is not marked as a completed retrieval. Refresh it before using the analysis.")
    if pair_cov < 100:
        messages.append("Some hourly comparison periods do not have both an eligible forecast and two valid half-hour actual records.")
    if malformed_forecasts or malformed_actuals:
        messages.append("Some source records had invalid required timestamps and were excluded from matching.")
    if conflict_count:
        messages.append("Conflicting values were found at a winning publication version or latest actual vintage; affected periods are excluded.")
    if forecast_dup_count or actual_dup_count:
        messages.append("Exact duplicate source rows were collapsed; counts are shown in diagnostics.")
    if expected_forecast_slots != 24 * len(decision_days):
        messages.append("The expected hourly interval count differs from 24 hours per decision date. Check timezone boundaries.")

    if sample_fixture or not retrieval_complete or pair_cov < 100 or raw_actual_cov < 100:
        quality_status = "partial"
    else:
        quality_status = "ok"

    return {
        "period": {
            "decisionStartDate": decision_start.isoformat(),
            "decisionEndDate": decision_end.isoformat(),
            "deliveryStartDate": (decision_start + timedelta(days=1)).isoformat(),
            "deliveryEndDate": (decision_end + timedelta(days=1)).isoformat(),
            "decisionTimezone": "Europe/London",
            "cutoffTimeLocal": cutoff_time,
        },
        "methodology": {
            "forecastGridMinutes": 60,
            "actualGridMinutes": 30,
            "comparisonGridMinutes": 60,
            "actualAggregation": "Arithmetic mean of the two half-hour FUELHH observations in each forecast hour; both are required.",
            "forecastSelection": "For each hourly delivery start, select the record with the latest publishTime less than or equal to that decision date's configured cutoff.",
            "errorConvention": "forecast minus actual; positive means overforecast, negative means underforecast.",
            "cutoffIsDefault": cutoff_time == "12:00",
            "cutoffSource": "Illustrative demo assumption; not specified by the challenge or verified as the utility's market deadline.",
            "percentileMethod": "Linear interpolation between ordered absolute errors.",
            "unit": snapshot.get("unit", "MW"),
        },
        "metrics": metrics,
        "coverage": {
            "expectedForecastSlots": expected_forecast_slots,
            "expectedActualHalfHours": expected_actual_half_hours,
            "expectedComparisons": expected_comparisons,
            "eligibleForecastSlots": sum(row["forecastStatus"] == "ok" for row in rows),
            "actualHourlySlotsComplete": actual_hour_slots_valid,
            "actualHalfHoursAvailable": len(actual_half_hours_valid_set),
            "pairedIntervals": paired,
            "forecastCoveragePct": round(forecast_cov, 2),
            "actualCoveragePct": round(actual_cov, 2),
            "actualHalfHourCoveragePct": round(raw_actual_cov, 2),
            "pairedCoveragePct": round(pair_cov, 2),
            "missingForecasts": sum(row["forecastStatus"] == "missing_forecast" for row in rows),
            "invalidForecasts": sum(row["forecastStatus"] == "invalid_value" for row in rows),
            "forecastConflicts": sum(row["forecastStatus"] == "conflict" for row in rows),
            "missingActualHourlySlots": sum(row["actualStatus"] == "missing_actual" for row in rows),
            "invalidActualHourlySlots": sum(row["actualStatus"] == "invalid_value" for row in rows),
            "actualConflicts": sum(row["actualStatus"] == "conflict" for row in rows),
        },
        "daily": daily,
        "records": rows,
        "dataQuality": {
            "status": quality_status,
            "source": snapshot_mode,
            "snapshotComplete": retrieval_complete,
            "snapshotRetrievedAtUtc": snapshot.get("retrievedAtUtc"),
            "rawForecastRecordCount": len(forecast_raw),
            "rawActualRecordCount": len(actual_raw),
            "exactForecastDuplicatesCollapsed": forecast_dup_count,
            "exactActualDuplicatesCollapsed": actual_dup_count,
            "malformedForecastRecords": malformed_forecasts,
            "malformedActualRecords": malformed_actuals,
            "winningVersionConflicts": conflict_count,
            "messages": messages,
            "snapshotValidation": snapshot_validation,
        },
    }


def forecast_versions(snapshot: dict[str, Any], delivery_start_utc: str, cutoff_utc: str) -> dict[str, Any]:
    delivery_start = parse_datetime(delivery_start_utc)
    cutoff = parse_datetime(cutoff_utc)
    if delivery_start is None or cutoff is None:
        raise ValueError("deliveryStartUtc and cutoffUtc must be valid ISO-8601 timestamps")
    if delivery_start.minute != 0 or delivery_start.second != 0:
        raise ValueError("deliveryStartUtc must be an hourly delivery start")
    versions = []
    for row in snapshot.get("forecastRecords") or []:
        start = parse_datetime(row.get("startTime")) if isinstance(row, dict) else None
        published = parse_datetime(row.get("publishTime")) if isinstance(row, dict) else None
        if start == delivery_start and published is not None:
            versions.append({
                "publishTimeUtc": iso_utc(published),
                "startTimeUtc": iso_utc(start),
                "generation": numeric(row.get("generation")),
                "eligible": published <= cutoff,
            })
    versions.sort(key=lambda item: item["publishTimeUtc"] or "")
    return {
        "deliveryStartUtc": iso_utc(delivery_start),
        "cutoffUtc": iso_utc(cutoff),
        "versionsFound": len(versions),
        "eligibleVersions": sum(item["eligible"] for item in versions),
        "versions": versions,
        "source": snapshot.get("retrievalMode", "snapshot"),
    }
