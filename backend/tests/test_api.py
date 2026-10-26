import json

from fastapi.testclient import TestClient
from app import main as main_module

client = TestClient(main_module.app)


def test_health_endpoint_reports_sample_fixture(tmp_path, monkeypatch):
    # Create an isolated sample snapshot so this test does not depend
    # on whether the real January dataset has been downloaded.
    fixture_path = tmp_path / "snapshot.json"

    fixture_path.write_text(
        json.dumps(
            {
                "schemaVersion": 1,
                "retrievalMode": "sample_fixture",
                "complete": False,
                "forecastRecords": [
                    {
                        "publishTime": "2026-01-01T10:00:00Z",
                        "startTime": "2026-01-02T00:00:00Z",
                        "generation": 100,
                    }
                ],
                "actualRecords": [
                    {
                        "publishTime": "2026-01-02T00:30:00Z",
                        "startTime": "2026-01-02T00:00:00Z",
                        "fuelType": "WIND",
                        "generation": 110,
                    }
                ],
            }
        ),
        encoding="utf-8",
    )

    # Point the API at the temporary fixture for this test only.
    monkeypatch.setattr(main_module, "SNAPSHOT_PATH", fixture_path)

    response = client.get("/api/v1/health")

    assert response.status_code == 200

    body = response.json()

    assert body["status"] == "ok"
    assert body["snapshotLoaded"] is True
    assert body["snapshotComplete"] is False
    assert body["snapshotMode"] == "sample_fixture"
    assert body["forecastRecords"] == 1
    assert body["actualRecords"] == 1


def test_analysis_api_reports_hourly_comparison_grid():
    response = client.get("/api/v1/analysis")

    assert response.status_code == 200

    body = response.json()

    assert body["coverage"]["expectedComparisons"] == 744
    assert body["coverage"]["expectedActualHalfHours"] == 1488
    assert body["methodology"]["forecastGridMinutes"] == 60


def test_invalid_dates_use_consistent_400_error():
    response = client.get(
        "/api/v1/analysis",
        params={
            "startDecisionDate": "2025-12-31",
            "endDecisionDate": "2026-01-02",
        },
    )

    assert response.status_code == 400
    assert response.json()["error"] == "INVALID_ANALYSIS_REQUEST"


def test_diagnostics_validate_delivery_timestamp():
    response = client.get(
        "/api/v1/diagnostics/forecast-versions",
        params={
            "deliveryStartUtc": "2026-01-02T00:30:00Z",
            "cutoffUtc": "2026-01-01T12:00:00Z",
        },
    )

    assert response.status_code == 400
