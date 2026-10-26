from datetime import date

from app.services.analysis import analyze_snapshot, calculate_metrics


def base_snapshot(forecasts, actuals, complete=True):
    return {
        "schemaVersion": 1,
        "retrievalMode": "elexon_snapshot" if complete else "sample_fixture",
        "complete": complete,
        "retrievedAtUtc": "2026-10-25T00:00:00Z" if complete else None,
        "unit": "MW",
        "forecastRecords": forecasts,
        "actualRecords": actuals,
        "validation": {},
    }


def forecast(publish, start, generation):
    return {"dataset": "WINDFOR", "publishTime": publish, "startTime": start, "generation": generation}


def actual(publish, start, generation):
    return {"dataset": "FUELHH", "publishTime": publish, "startTime": start, "fuelType": "WIND", "generation": generation}


def test_latest_forecast_before_cutoff_is_selected_and_actuals_are_aggregated():
    snapshot = base_snapshot(
        forecasts=[
            forecast("2026-01-01T08:00:00Z", "2026-01-02T00:00:00Z", 95),
            forecast("2026-01-01T11:30:00Z", "2026-01-02T00:00:00Z", 100),
            forecast("2026-01-01T12:30:00Z", "2026-01-02T00:00:00Z", 999),
        ],
        actuals=[
            actual("2026-01-02T00:30:00Z", "2026-01-02T00:00:00Z", 80),
            actual("2026-01-02T01:00:00Z", "2026-01-02T00:30:00Z", 100),
        ],
    )
    result = analyze_snapshot(snapshot, date(2026, 1, 1), date(2026, 1, 1), "12:00")
    first = result["records"][0]
    assert first["forecastGeneration"] == 100
    assert first["forecastPublishTimeUtc"] == "2026-01-01T11:30:00Z"
    assert first["actualGeneration"] == 90
    assert first["error"] == 10
    assert first["pairStatus"] == "paired"
    assert first["actualHalfHourValues"] == [80.0, 100.0]
    assert first["forecastPublishTimeUtc"] <= first["decisionCutoffUtc"]


def test_invalid_latest_eligible_forecast_does_not_fall_back_to_older_version():
    snapshot = base_snapshot(
        forecasts=[
            forecast("2026-01-01T09:00:00Z", "2026-01-02T00:00:00Z", 100),
            forecast("2026-01-01T11:30:00Z", "2026-01-02T00:00:00Z", None),
        ],
        actuals=[
            actual("2026-01-02T00:30:00Z", "2026-01-02T00:00:00Z", 80),
            actual("2026-01-02T01:00:00Z", "2026-01-02T00:30:00Z", 100),
        ],
    )
    row = analyze_snapshot(snapshot, date(2026, 1, 1), date(2026, 1, 1), "12:00")["records"][0]
    assert row["forecastStatus"] == "invalid_value"
    assert row["forecastGeneration"] is None
    assert row["pairStatus"] == "invalid_value"


def test_conflicting_rows_at_winning_publication_are_flagged():
    snapshot = base_snapshot(
        forecasts=[
            forecast("2026-01-01T11:30:00Z", "2026-01-02T00:00:00Z", 100),
            forecast("2026-01-01T11:30:00Z", "2026-01-02T00:00:00Z", 101),
        ],
        actuals=[
            actual("2026-01-02T00:30:00Z", "2026-01-02T00:00:00Z", 80),
            actual("2026-01-02T01:00:00Z", "2026-01-02T00:30:00Z", 100),
        ],
    )
    row = analyze_snapshot(snapshot, date(2026, 1, 1), date(2026, 1, 1), "12:00")["records"][0]
    assert row["forecastStatus"] == "conflict"
    assert row["pairStatus"] == "conflict"
    assert row["forecastGeneration"] is None


def test_delivery_after_january_31_decision_is_february_1():
    snapshot = base_snapshot([], [])
    result = analyze_snapshot(snapshot, date(2026, 1, 31), date(2026, 1, 31), "12:00")
    assert len(result["records"]) == 24
    assert {row["deliveryDate"] for row in result["records"]} == {"2026-02-01"}
    assert result["coverage"]["expectedComparisons"] == 24
    assert result["coverage"]["expectedActualHalfHours"] == 48


def test_january_decision_range_has_expected_hourly_and_half_hourly_denominators():
    result = analyze_snapshot(base_snapshot([], []), date(2026, 1, 1), date(2026, 1, 31), "12:00")
    assert len(result["records"]) == 744
    assert result["coverage"]["expectedForecastSlots"] == 744
    assert result["coverage"]["expectedComparisons"] == 744
    assert result["coverage"]["expectedActualHalfHours"] == 1488


def test_metrics_are_computed_on_valid_pairs_only():
    records = [
        {"forecastGeneration": 100, "actualGeneration": 110, "pairStatus": "paired"},
        {"forecastGeneration": 200, "actualGeneration": 180, "pairStatus": "paired"},
        {"forecastGeneration": None, "actualGeneration": 300, "pairStatus": "missing_forecast"},
    ]
    metrics = calculate_metrics(records)
    assert metrics["n"] == 2
    assert metrics["mae"] == 15
    assert metrics["bias"] == 5
    assert metrics["rmse"] == (250 ** 0.5)
    assert metrics["maxAbsoluteError"] == 20


def test_zero_and_negative_generations_are_not_rejected():
    snapshot = base_snapshot(
        forecasts=[forecast("2026-01-01T11:30:00Z", "2026-01-02T00:00:00Z", 0)],
        actuals=[
            actual("2026-01-02T00:30:00Z", "2026-01-02T00:00:00Z", -2),
            actual("2026-01-02T01:00:00Z", "2026-01-02T00:30:00Z", 0),
        ],
    )
    row = analyze_snapshot(snapshot, date(2026, 1, 1), date(2026, 1, 1), "12:00")["records"][0]
    assert row["forecastStatus"] == "ok"
    assert row["actualStatus"] == "ok"
    assert row["actualGeneration"] == -1
    assert row["error"] == 1


def test_invalid_cutoff_and_out_of_scope_dates_fail():
    snapshot = base_snapshot([], [])
    try:
        analyze_snapshot(snapshot, date(2026, 1, 1), date(2026, 1, 1), "25:90")
    except ValueError as exc:
        assert "HH:MM" in str(exc)
    else:
        raise AssertionError("Invalid cutoff should fail")
    try:
        analyze_snapshot(snapshot, date(2025, 12, 31), date(2026, 1, 1), "12:00")
    except ValueError as exc:
        assert "within January 2026" in str(exc)
    else:
        raise AssertionError("Out-of-scope dates should fail")
