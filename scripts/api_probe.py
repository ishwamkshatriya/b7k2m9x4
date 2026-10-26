#!/usr/bin/env python3
"""Small, repeatable Elexon WINDFOR/FUELHH feasibility probe.

Defaults reproduce the narrow January 2026 requests used in this investigation.
The script uses only Python's standard library and never sends credentials.
"""

from __future__ import annotations

import argparse
import json
import sys
import urllib.error
import urllib.parse
import urllib.request
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

BASE = "https://data.elexon.co.uk/bmrs/api/v1/datasets"
TIMEOUT_SECONDS = 25


def request_json(endpoint: str, params: list[tuple[str, str]]) -> dict[str, Any]:
    query = urllib.parse.urlencode(params)
    url = f"{BASE}/{endpoint}/stream?{query}"
    req = urllib.request.Request(url, headers={"Accept": "application/json"}, method="GET")
    try:
        with urllib.request.urlopen(req, timeout=TIMEOUT_SECONDS) as response:
            raw = response.read()
            status = response.status
            content_type = response.headers.get("Content-Type")
            headers = dict(response.headers.items())
    except urllib.error.HTTPError as exc:
        raw = exc.read()
        status = exc.code
        content_type = exc.headers.get("Content-Type")
        headers = dict(exc.headers.items())
    except (urllib.error.URLError, TimeoutError, OSError) as exc:
        return {"url": url, "status": None, "content_type": None, "size_bytes": None,
                "transport_error": str(exc), "error_details": None, "records": None}

    text = raw.decode("utf-8", errors="replace")
    try:
        parsed = json.loads(text)
        parse_error = None
    except json.JSONDecodeError as exc:
        parsed = None
        parse_error = str(exc)
    records = parsed if isinstance(parsed, list) else None
    error_details = None
    if status >= 400 or records is None:
        error_details = parsed if parsed is not None else text[:2000]
    return {"url": url, "status": status, "content_type": content_type,
            "size_bytes": len(raw), "headers": headers, "records": records,
            "parsed_json": parsed, "parse_error": parse_error,
            "error_details": error_details}


def iso_values(records: list[dict[str, Any]], field: str) -> list[str]:
    return [str(row[field]) for row in records if row.get(field) is not None]


def summarize(result: dict[str, Any], dataset: str) -> dict[str, Any]:
    records = result.get("records")
    summary: dict[str, Any] = {k: result.get(k) for k in
        ("url", "status", "content_type", "size_bytes", "transport_error", "parse_error", "error_details")}
    if records is None:
        summary.update(record_count=None, fields=[], representative_records=[])
        return summary
    keys = sorted({key for row in records if isinstance(row, dict) for key in row})
    missing = {key: sum(not isinstance(row, dict) or key not in row for row in records) for key in keys}
    nulls = {key: sum(isinstance(row, dict) and key in row and row[key] is None for row in records) for key in keys}
    duplicates = Counter(json.dumps(row, sort_keys=True, separators=(",", ":"), default=str) for row in records)
    duplicate_rows = sum(n - 1 for n in duplicates.values() if n > 1)
    starts = iso_values(records, "startTime")
    publishes = iso_values(records, "publishTime")
    versions: dict[str, set[str]] = defaultdict(set)
    for row in records:
        if isinstance(row, dict) and row.get("startTime") is not None and row.get("publishTime") is not None:
            versions[str(row["startTime"])].add(str(row["publishTime"]))
    summary.update({
        "record_count": len(records), "fields": keys, "missing_field_counts": missing,
        "null_value_counts": nulls, "duplicate_record_count": duplicate_rows,
        "min_publishTime": min(publishes) if publishes else None,
        "max_publishTime": max(publishes) if publishes else None,
        "min_startTime": min(starts) if starts else None,
        "max_startTime": max(starts) if starts else None,
        "start_times_with_multiple_publications_count": sum(len(times) > 1 for times in versions.values()),
        "multiple_publication_examples": [
            {"startTime": start, "publishTimes": sorted(times)}
            for start, times in versions.items() if len(times) > 1
        ][:5],
        "representative_records": records[:3],
    })
    return summary


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--wind-publish-from", default="2026-01-01T00:00:00Z")
    parser.add_argument("--wind-publish-to", default="2026-01-02T00:00:00Z")
    parser.add_argument("--fuel-settlement-from", default="2026-01-01")
    parser.add_argument("--fuel-settlement-to", default="2026-01-02")
    parser.add_argument("--reports-dir", default="reports")
    args = parser.parse_args()

    # Parameters are selected from the official endpoint docs. FUELHH request
    # intentionally has settlement filters and fuelType only; no publish filters.
    wind = request_json("WINDFOR", [
        ("publishDateTimeFrom", args.wind_publish_from),
        ("publishDateTimeTo", args.wind_publish_to),
    ])
    fuel = request_json("FUELHH", [
        ("settlementDateFrom", args.fuel_settlement_from),
        ("settlementDateTo", args.fuel_settlement_to),
        ("fuelType", "WIND"),
    ])
    summaries = {"WINDFOR": summarize(wind, "WINDFOR"), "FUELHH": summarize(fuel, "FUELHH")}
    # Illustrative decision cutoff; change it to the business's agreed cutoff.
    cutoff = "2026-01-01T12:00:00Z"
    wind_rows, fuel_rows = wind.get("records"), fuel.get("records")
    if isinstance(wind_rows, list) and isinstance(fuel_rows, list):
        actual_by_start = {str(r.get("startTime")): r for r in fuel_rows
                           if isinstance(r, dict) and r.get("fuelType") == "WIND"}
        # Day-ahead illustration: delivery must begin on a later UTC date than
        # the cutoff date; a same-day timestamp would be an intraday comparison.
        common = sorted(set(actual_by_start) & {
            str(r.get("startTime")) for r in wind_rows if isinstance(r, dict)
            if str(r.get("startTime", ""))[:10] > cutoff[:10]
        })
        matches = []
        for start in common:
            eligible = [r for r in wind_rows if isinstance(r, dict)
                        and str(r.get("startTime")) == start
                        and r.get("publishTime") is not None
                        and str(r["publishTime"]) < cutoff]
            if eligible:
                forecast = max(eligible, key=lambda r: str(r["publishTime"]))
                actual = actual_by_start[start]
                if isinstance(forecast.get("generation"), (int, float)) and isinstance(actual.get("generation"), (int, float)):
                    matches.append({"startTime": start, "cutoffExclusive": cutoff,
                                    "forecast": forecast, "actual": actual,
                                    "error_forecast_minus_actual": forecast["generation"] - actual["generation"],
                                    "absolute_error": abs(forecast["generation"] - actual["generation"])})
        summaries["sample_match"] = {"cutoff_exclusive": cutoff,
                                     "shared_startTime_count": len(common),
                                     "eligible_numeric_matches": len(matches),
                                     "first_match": matches[0] if matches else None}
        jan_forecast_starts = {str(r.get("startTime")) for r in wind_rows
                               if isinstance(r, dict) and str(r.get("startTime", ""))[:7] == "2026-01"}
        jan_actual_starts = {str(r.get("startTime")) for r in fuel_rows
                             if isinstance(r, dict) and str(r.get("startTime", ""))[:7] == "2026-01"}
        summaries["january_delivery_coverage"] = {
            "forecast_unique_startTime_in_january": len(jan_forecast_starts),
            "actual_unique_startTime_in_january": len(jan_actual_starts),
            "exact_timestamp_overlap_in_january": len(jan_forecast_starts & jan_actual_starts),
            "actual_periods_without_exact_forecast_startTime": len(jan_actual_starts - jan_forecast_starts),
        }

    out = Path(args.reports_dir)
    out.mkdir(parents=True, exist_ok=True)
    for name, result in (("windfor", wind), ("fuelhh", fuel)):
        if isinstance(result.get("records"), list):
            (out / f"{name}_sample.json").write_text(
                json.dumps(result["records"][:3], indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    (out / "api_probe_results.json").write_text(
        json.dumps(summaries, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print("Elexon API probe summary")
    for name in ("WINDFOR", "FUELHH"):
        item = summaries[name]
        print(f"{name}: HTTP {item.get('status')}; {item.get('record_count')} records; "
              f"{item.get('content_type')}; {item.get('size_bytes')} bytes")
    if "january_delivery_coverage" in summaries:
        cov = summaries["january_delivery_coverage"]
        print(f"January delivery: {cov['forecast_unique_startTime_in_january']} unique forecast timestamps; "
              f"{cov['actual_unique_startTime_in_january']} actual timestamps; "
              f"{cov['exact_timestamp_overlap_in_january']} exact matches; "
              f"{cov['actual_periods_without_exact_forecast_startTime']} actuals without an exact forecast timestamp")
    match = summaries.get("sample_match", {}).get("first_match")
    if match:
        print(f"Illustrative cutoff match: {match['startTime']}; "
              f"forecast={match['forecast']['generation']}; actual={match['actual']['generation']}; "
              f"error={match['error_forecast_minus_actual']}")
    else:
        print("Illustrative cutoff match: none")
    print("Files created: reports/windfor_sample.json, reports/fuelhh_sample.json, "
          "reports/api_probe_results.json")
    return 0 if all(x.get("status") is not None for x in summaries.values()) else 2


if __name__ == "__main__":
    sys.exit(main())
