# Decision log

## DL-001 — January dates are purchasing decision dates

**Decision:** Treat 1–31 January 2026 as decision dates and evaluate delivery on the next local calendar day, including 1 February delivery for the 31 January decision.

**Reason:** This best follows the challenge wording: purchasing decisions are made one day before the delivery day. It remains documented as an interpretation in case the client intended delivery dates instead.

## DL-002 — Decision cutoff is configurable

**Decision:** Use 12:00 Europe/London as an illustrative UI default only.

**Reason:** The challenge does not state a clock time. The UI and API responses label the cutoff as an assumption. The value should be changed if the team confirms a different deadline.

## DL-003 — Compare on the hourly WINDFOR grid

**Decision:** Keep forecasts hourly and aggregate the two corresponding half-hour FUELHH actuals using their arithmetic mean. Require both half-hour observations.

**Reason:** The empirical probe observed 744 hourly forecast timestamps and 1,488 half-hour actual timestamps for a 31-day delivery period. Exact timestamp joining would leave half of the actual observations unmatched. The mean-of-two comparison is a transparent modelling convention; it is not established by the API response itself.

## DL-004 — Latest eligible forecast vintage

**Decision:** Choose the maximum `publishTime` for the target hourly `startTime` among records with `publishTime <= decision cutoff`.

**Reason:** This prevents future information from leaking into a historical decision replay. If the selected winning version has an invalid value or conflicting same-publication values, mark the slot invalid/conflicted rather than silently falling back to an older version.

## DL-005 — Static, versioned data snapshot

**Decision:** Ingest once into `data/snapshot.json`; have FastAPI analyse the snapshot rather than calling Elexon for every dashboard request.

**Reason:** The challenge dataset is historical. A snapshot improves reproducibility, avoids repetitive upstream calls, and makes the app's deployed behavior easier to review. `scripts/refresh_snapshot.py` records the retrieval time, query parameters, raw records, and coverage metadata.

## DL-006 — Do not fabricate full-month numbers

**Decision:** The starter snapshot contains only genuine sample records from the feasibility probe and is marked incomplete. The dashboard shows no monthly metric claims until the full snapshot is fetched.

**Reason:** The environment used to package this project cannot resolve the Elexon API hostname. The report from the user's Codex run documents successful live retrieval and is preserved under `docs/`. Running the refresh script in the user's network-enabled environment is required to create the full data snapshot.
