"""Public API response schemas used by FastAPI's OpenAPI contract."""
from __future__ import annotations
from typing import Any
from pydantic import BaseModel, Field


class MetricSet(BaseModel):
    n: int
    mae: float | None = None
    rmse: float | None = None
    bias: float | None = None
    maxAbsoluteError: float | None = None
    p90AbsoluteError: float | None = None
    p95AbsoluteError: float | None = None


class DailyMetric(MetricSet):
    decisionDate: str
    deliveryDate: str
    expectedComparisons: int
    forecastValid: int
    actualValid: int
    pairedCoveragePct: float


class Coverage(BaseModel):
    expectedForecastSlots: int
    expectedActualHalfHours: int
    expectedComparisons: int
    eligibleForecastSlots: int
    actualHourlySlotsComplete: int
    actualHalfHoursAvailable: int
    pairedIntervals: int
    forecastCoveragePct: float
    actualCoveragePct: float
    actualHalfHourCoveragePct: float
    pairedCoveragePct: float
    missingForecasts: int
    invalidForecasts: int
    forecastConflicts: int
    missingActualHourlySlots: int
    invalidActualHourlySlots: int
    actualConflicts: int


class IntervalRecord(BaseModel):
    decisionDate: str
    deliveryDate: str
    deliveryStartUtc: str
    deliveryStartLocal: str
    decisionCutoffUtc: str
    forecastPublishTimeUtc: str | None = None
    forecastGeneration: float | None = None
    forecastStatus: str
    forecastLeadTimeMinutes: float | None = None
    actualGeneration: float | None = None
    actualStatus: str
    actualPublishTimeUtc: str | None = None
    actualVintageCount: int
    actualHalfHourValues: list[float] | None = None
    error: float | None = None
    absoluteError: float | None = None
    pairStatus: str


class Methodology(BaseModel):
    forecastGridMinutes: int
    actualGridMinutes: int
    comparisonGridMinutes: int
    actualAggregation: str
    forecastSelection: str
    errorConvention: str
    cutoffIsDefault: bool
    cutoffSource: str
    percentileMethod: str
    unit: str


class DataQuality(BaseModel):
    status: str
    source: str
    snapshotComplete: bool
    snapshotRetrievedAtUtc: str | None = None
    rawForecastRecordCount: int
    rawActualRecordCount: int
    exactForecastDuplicatesCollapsed: int
    exactActualDuplicatesCollapsed: int
    malformedForecastRecords: int
    malformedActualRecords: int
    winningVersionConflicts: int
    messages: list[str] = Field(default_factory=list)
    snapshotValidation: dict[str, Any] = Field(default_factory=dict)


class AnalysisPeriod(BaseModel):
    decisionStartDate: str
    decisionEndDate: str
    deliveryStartDate: str
    deliveryEndDate: str
    decisionTimezone: str
    cutoffTimeLocal: str


class AnalysisResponse(BaseModel):
    period: AnalysisPeriod
    methodology: Methodology
    metrics: MetricSet
    coverage: Coverage
    daily: list[DailyMetric]
    records: list[IntervalRecord]
    dataQuality: DataQuality


class ForecastVersion(BaseModel):
    publishTimeUtc: str | None = None
    startTimeUtc: str | None = None
    generation: float | None = None
    eligible: bool


class ForecastVersionsResponse(BaseModel):
    deliveryStartUtc: str
    cutoffUtc: str
    versionsFound: int
    eligibleVersions: int
    versions: list[ForecastVersion]
    source: str
