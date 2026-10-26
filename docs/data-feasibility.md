# Elexon January 2026 data feasibility

**Verdict: PARTIALLY VERIFIED**

The live APIs returned real January data. FUELHH provides all 1,488 expected half-hour periods in January 2026. WINDFOR provides multiple historical publication versions and 744 distinct January delivery timestamps, but those timestamps are hourly. Only 744 of the 1,488 actual timestamps match exactly. The evidence therefore supports a limited hourly comparison and a real point-in-time example, but does not establish a complete half-hourly forecast-accuracy analysis without an explicit hourly-to-half-hourly convention.

## A. Environment and date

- Investigation run from the Windows workspace on 25 October 2026 (Asia/Calcutta).
- Python standard library `urllib` was used by [api_probe.py](api_probe.py); no credentials were sent.
- The initial sandboxed request could not resolve `data.elexon.co.uk`. The live requests below were then made with network access enabled.
- The challenge document asks for an application, but the separate investigation request explicitly limits this work to feasibility probing; no frontend or production backend was built.

## B. Official documentation

- [WINDFOR stream documentation](https://bmrs.elexon.co.uk/api-documentation/endpoint/datasets/WINDFOR/stream)
- [FUELHH stream documentation](https://bmrs.elexon.co.uk/api-documentation/endpoint/datasets/FUELHH/stream)
- The official endpoint definitions expose `publishDateTimeFrom` / `publishDateTimeTo` on WINDFOR and `settlementDateFrom` / `settlementDateTo` plus `fuelType` on FUELHH. They describe 200, 400, 429 and 500 responses. The screenshots supplied with the request also show these filters and an example FUELHH request using `fuelType=WIND`.

## C. Requests and responses

All requests used `GET` and `Accept: application/json`. The request URLs below contain no credentials. The API returned JSON with the expected content type; no format correction or retry after an error was needed.

| Purpose | Exact request URL | HTTP | Content type | Response bytes | Records |
|---|---|---:|---|---:|---:|
| Narrow WINDFOR probe | `https://data.elexon.co.uk/bmrs/api/v1/datasets/WINDFOR/stream?publishDateTimeFrom=2026-01-01T00%3A00%3A00Z&publishDateTimeTo=2026-01-02T00%3A00%3A00Z` | 200 | `application/json; charset=utf-8` | 65,993 | 584 |
| Narrow FUELHH probe | `https://data.elexon.co.uk/bmrs/api/v1/datasets/FUELHH/stream?settlementDateFrom=2026-01-01&settlementDateTo=2026-01-02&fuelType=WIND` | 200 | `application/json; charset=utf-8` | 17,455 | 96 |
| Month coverage WINDFOR | `https://data.elexon.co.uk/bmrs/api/v1/datasets/WINDFOR/stream?publishDateTimeFrom=2025-12-31T00%3A00%3A00Z&publishDateTimeTo=2026-01-31T23%3A59%3A59Z` | 200 | `application/json; charset=utf-8` | 2,105,753 | 18,688 |
| Month coverage FUELHH | `https://data.elexon.co.uk/bmrs/api/v1/datasets/FUELHH/stream?settlementDateFrom=2026-01-01&settlementDateTo=2026-01-31&fuelType=WIND` | 200 | `application/json; charset=utf-8` | 269,971 | 1,488 |

The two unique request windows were run again while checking the probe and correcting the illustrative match rule. All returned HTTP 200. There were no API error details, 429 responses, unsupported parameters, null values, missing fields, or exact duplicate records in the returned sets.

## D. Schemas and observed data

The narrow WINDFOR response had 584 records with fields `dataset`, `publishTime`, `startTime`, and `generation`; none were missing or null. Its publication times ranged from `2026-01-01T02:30:00Z` to `2026-01-01T22:30:00Z`, and its start times ranged from `2025-12-31T21:00:00Z` to `2026-01-03T21:00:00Z`.

The narrow FUELHH response had 96 records with fields `dataset`, `publishTime`, `startTime`, `settlementDate`, `settlementPeriod`, `fuelType`, and `generation`; none were missing or null. `fuelType` was WIND on the filtered response. Start times ranged from `2026-01-01T00:00:00Z` to `2026-01-02T23:30:00Z`.

On the month request, WINDFOR publication times ranged from `2025-12-31T02:30:00Z` to `2026-01-31T22:30:00Z`; start times ranged from `2025-12-30T21:00:00Z` to `2026-02-02T21:00:00Z`. There were 18,688 records, no missing/null fields and no exact duplicate records. At least 817 distinct start times in the response had multiple publication versions. The month FUELHH response had no missing/null fields or exact duplicates; start times ranged from `2026-01-01T00:00:00Z` through `2026-01-31T23:30:00Z`.

Representative records are saved as actual API data in [reports/windfor_sample.json](reports/windfor_sample.json) and [reports/fuelhh_sample.json](reports/fuelhh_sample.json), with no more than three records per file. The full API responses were not saved.

## E. Historical forecast availability

1. **Can the API return January 2026 forecasts? VERIFIED.** The month request returned January publication history and 744 distinct January `startTime` values.
2. **Can it return actual WIND generation for matching delivery periods? VERIFIED.** The month FUELHH request returned 1,488 January periods with `fuelType=WIND`.
3. **Can it return historical forecast versions? VERIFIED for sampled periods.** More than one `publishTime` was observed for the same target `startTime`; the narrow request alone also exposed multiple publications for target periods. This demonstrates version history in the response, not that every business cutoff has a qualifying version.
4. **Is coverage sufficient for the intended analysis? PARTIALLY VERIFIED.** The APIs expose the fields needed to choose a publication before a cutoff and actuals at common start times. However, the observed forecast timestamps are hourly while actual timestamps are half-hourly, and the business has not specified how to compare an hourly forecast to half-hour actuals.

The chosen WINDFOR publication window starts on 31 December to include forecasts available before the first January delivery day. It returned January delivery targets and later targets too. FUELHH was queried separately by settlement date for the whole delivery month. The endpoint pages show filter-based retrieval and no pagination parameters in these stream operations. One full month request succeeded for each dataset at these observed sizes; this does not establish a service-side maximum for larger requests. For production-scale extraction, retain date-bounded requests and verify returned coverage rather than assuming an unbounded call is complete.

## F. Forecast-actual sample comparison

The probe demonstrates a real eligible next-day comparison using an **illustrative, exclusive cutoff of `2026-01-01T12:00:00Z`**. The selected delivery timestamp is `2026-01-02T00:00:00Z`, the first next-UTC-day hour. Both records have identical UTC `startTime`; no timezone normalization was needed for this pair.

| Value | Record |
|---|---|
| Forecast | publishTime `2026-01-01T11:30:00Z`; generation `18800` |
| Actual WIND | publishTime `2026-01-02T00:30:00Z`; generation `15228` |
| Forecast minus actual | `+3572` |
| Absolute error | `3572` |

These are the actual returned numeric values. The error is in the API's reported generation units; the response sample does not declare units in the record itself. The example is a feasibility check, not a metric for the month. The cutoff is illustrative because the challenge does not define the exact daily purchasing decision time.

## G. Expected volume and coverage

January 2026 has 31 days. Under the UTC half-hour convention used by FUELHH and the observed 48 settlement periods per date, a full month contains **31 × 48 = 1,488 expected actual periods**. The month query returned 1,488 records and 1,488 distinct start times: no missing actual periods were observed for the expected convention.

The month WINDFOR query returned 18,688 versioned records but only **744 distinct January delivery timestamps**, hourly. Exact `startTime` intersection with FUELHH was 744; **744 actual half-hour periods had no exact forecast timestamp**. Therefore:

- Expected actual half-hours: 1,488.
- Actual records returned: 1,488.
- January forecast timestamps returned (unique): 744 hourly timestamps.
- Exact timestamp pairs available: 744.
- Actuals with no exact forecast timestamp: 744.
- Eligible forecasts at the illustrative cutoff for the tested two-day window: 46 numeric common timestamps, after restricting delivery to a later UTC date.
- Missing eligible forecasts beyond that tested example: not established across every per-day cutoff.

An hourly comparison might be possible by aggregating or selecting half-hour actuals, but neither a mapping nor an aggregation rule is specified in the challenge or established by these API responses. Do not silently treat the hourly forecast as two half-hour forecasts.

## H. Errors, timestamp handling, and limits

- The query parameters worked as documented; no 400, 429 or 500 response was observed.
- All timestamps in the paired example were UTC RFC 3339 strings with `Z` and aligned exactly.
- The timestamp cadence differs: hourly WINDFOR start times versus half-hourly FUELHH start times. This is the central unresolved data-grain issue.
- Publication time and delivery time are distinct. WINDFOR filters were by `publishTime`; actuals were filtered by settlement date. A delivery-period filter cannot be substituted for a publication-time decision cutoff.
- The API response fields contained no nulls or omitted fields in the queried records. That does not guarantee future or unqueried windows have no missing data.
- The assignment's exact decision cutoff, desired error metric, treatment of half-hour periods, and whether a daily forecast should be evaluated against one or both half-hours remain unspecified.

## I. Conclusions and unresolved questions

A limited January forecast/actual analysis is demonstrably possible: both datasets return real records, historical publications exist, actual January coverage matches the expected 1,488 periods, and at least one next-day forecast has a matching actual with a computable error. A complete decision-time accuracy analysis is **not yet verified** because only 744 hourly forecast timestamps align exactly with 1,488 half-hour actual timestamps, and business cutoff and aggregation rules are unspecified.

Unresolved:

1. What exact time and timezone define the January day-ahead purchasing cutoff?
2. Should hourly WINDFOR values be compared to the first half-hour, second half-hour, or an aggregation of both FUELHH records?
3. What error measures should be reported (for example MAE, RMSE, bias), and in which generation units?
4. Does every January delivery hour have at least one forecast published before its applicable cutoff? The sampled cutoff does; a systematic per-day cutoff audit remains to be run once the business rule is defined.
5. Are the observed stream response sizes and no-pagination behavior acceptable operationally for repeated or longer-range extraction? The API documentation does not provide a maximum in the material consulted.

**Final verdict: PARTIALLY VERIFIED.** The API can return January forecasts and actuals, and a real eligible next-day point match was calculated. The API evidence does not establish complete accuracy coverage at the actual dataset's half-hour resolution or a complete per-cutoff January audit.

## J. Files created

- `api_probe.py` — repeatable standard-library probe; defaults to the narrow January requests. Options allow the investigated date windows to be changed.
- `api_feasibility_report.md` — findings and limitations.
- `reports/windfor_sample.json` — three real WINDFOR response records.
- `reports/fuelhh_sample.json` — three real FUELHH response records.
- `reports/api_probe_results.json` — machine-readable counts and metadata from the latest month probe (additional supporting evidence).
