# Website Feature Report

## Electricity Consumption Analysis System

**Project number:** 18  
**Application name:** Gridline Energy Analytics  
**Project type:** Flask web application for electricity meter data management and consumption analysis  
**Demonstration URL:** http://127.0.0.1:5000  
**Data status:** Uses synthetic demonstration records; all energy values are in kWh.

## 1. Purpose

The website manages electricity consumers, their meters, and dated cumulative meter readings. It validates readings, calculates consumption between consecutive readings on the same meter, summarizes defensibly allocated monthly or yearly usage, and highlights periods above a configurable threshold.

It is an educational analysis prototype. It does not create official utility bills, confirm faults, or connect to physical meters or paid services.

## 2. Website Pages and Features

### Overview Dashboard

The dashboard provides a current view of the records in the configured database:

- Total valid consumption allocated to complete calendar periods.
- Registered consumer, meter, and reading counts.
- Monthly usage trend chart and downloadable PNG.
- Regional usage comparison based on allocated consumption.
- Recent meter readings.
- Validation findings and high-usage alerts for review.

The dashboard is data-driven. An empty database displays empty states rather than fabricated values. The interactive trend uses Chart.js; its browser library is loaded from a public CDN.

### Consumers

Users can add, view, edit, search, and delete consumer records. Each record stores a consumer type and region. Required fields and maximum lengths are checked by the server. A consumer cannot be deleted while meters still reference it.

### Meters

Users can add, view, edit, search, and delete meters. Each meter has a unique meter code and must belong to an existing consumer. The meter list shows the linked consumer and region. A meter with readings cannot be deleted.

### Meter Readings

Users can record, review, edit, filter, search, and delete dated cumulative readings for a meter. The reading list supports meter, region, and date-range filters. Negative, non-numeric, non-finite, malformed-date, duplicate meter/date, and orphan-meter submissions are rejected by input validation or database constraints.

Editing or deleting a reading causes interval calculations to be recomputed from the updated record history.

### Reading Validation

The validation page reports the meter, date, cumulative reading, issue, severity, and recommended action. It can identify:

- A first reading without a previous value.
- Duplicate meter/date readings.
- Negative or invalid cumulative values.
- A decrease from the preceding reading, classified as a possible reset or rollover.
- A suspiciously large increase according to the configurable rule.

A decrease is not automatically corrected or assumed to be a rollover. The affected interval is excluded from ordinary consumption totals pending review.

### Reports

The Reports page provides monthly and yearly summaries and filters by consumer, meter, consumer type, and region. It shows valid allocated kWh, valid and invalid interval counts, and unallocated intervals. The page also lists high-usage threshold alerts, including period, consumer, meter, usage, threshold, and excess.

Threshold alerts are review signals only. They are not confirmed faults, waste events, electrical emergencies, or bills.

### Consumer Comparison

The **Compare consumers** page provides a chart and table comparing valid kWh for one selected monthly or yearly period. Users can narrow the comparison by consumer and region. Only complete eligible periods are shown; spanning intervals and incomplete annual coverage are not included.

## 3. Required Report Outputs

| Output | Website location | Description |
|---|---|---|
| Monthly consumption report | Reports page; `/export/monthly.csv` | Boundary-aligned monthly consumption, interval status/counts, and report timestamp. |
| High-usage list | Reports page; `/export/high-usage.csv` | Complete allocated periods exceeding the configured threshold. |
| Usage trend chart | Dashboard; `/charts/usage-trend.png` | Interactive browser chart and downloadable Matplotlib PNG. |
| Reading-validation report | Validation page; `/export/validation.csv` | Reading issues with severity and recommended action. |
| Consumer comparison | Compare consumers; `/analysis/consumers` | Per-consumer valid allocated kWh chart and table for one selected eligible period. |

CSV downloads include a report name and UTC generation timestamp. Downloads are streamed to the browser and are not automatically written to the project’s `exports/` or `charts/` folders.

## 4. Calculation and Reporting Rules

For consecutive valid readings from the same meter:

`consumption_kwh = current_cumulative_kwh - previous_cumulative_kwh`

Readings are sorted chronologically and meters are analyzed separately. A first reading has unknown consumption. Invalid or decreasing intervals are never silently counted as negative consumption.

A consumption interval is assigned to a month only when the readings span exactly from the first day of one month to the first day of the next. Yearly reports sum these valid boundary-aligned monthly intervals within each year; a single January 1-to-January 1 interval also covers a complete year. A year is considered complete for threshold alerts only when its valid intervals form uninterrupted January 1-to-January 1 coverage. Intervals that span periods without supported boundaries are shown as **Unallocated (spanning)**; no estimated split is currently applied. Invalid intervals are shown separately and excluded from allocated totals. Incomplete years are labeled and do not trigger yearly threshold alerts. Missing intervals are not treated as zero usage.

High-usage comparisons use only complete boundary-aligned periods and the absolute threshold set by `HIGH_USAGE_THRESHOLD_KWH` (default: 120 kWh). This avoids comparing short partial periods directly with complete periods.

## 5. Technology and Data Protection

- **Backend:** Python 3 and Flask.
- **Database:** MySQL 8/InnoDB is the primary target. SQLite is used for local demonstration only when `DATABASE_URL` is blank; a configured MySQL connection error does not silently select SQLite.
- **Analysis:** Pandas and NumPy.
- **Charts:** Chart.js for browser interaction and Matplotlib for PNG output.
- **Frontend:** HTML, CSS, JavaScript, and Jinja templates.
- **Testing:** pytest with isolated SQLite test databases.

Database calls use SQLAlchemy Core parameter binding. Database constraints enforce unique meter codes, one reading per meter/date, nonnegative readings, and foreign-key relationships. State-changing forms use POST and CSRF protection. No authentication is implemented; the app is intended for local college demonstration and is not production-secure.

## 6. Demonstration Dataset

`data/sample_readings.csv` contains clearly synthetic consumers and readings from 2024 and 2025 across multiple regions. It includes ordinary consumption, a commercial threshold example, and a separate decreasing-reading scenario to demonstrate validation. The seed command refuses to load into a database that already contains records. Reset is explicit and guarded to development databases containing only demo-prefixed records.

## 7. Running and Demonstrating the Website

With dependencies installed and the project environment activated:

```sh
python scripts/seed_database.py
python app.py
```

Open http://127.0.0.1:5000. A useful demonstration sequence is:

1. Review the dashboard totals, monthly chart, regions, recent readings, and review queue.
2. Open Consumers and Meters to show linked account and meter records.
3. Open Readings to filter and review cumulative meter values.
4. Open Validation to show the possible reset/rollover finding and its recommended action.
5. Open Reports, switch between monthly and yearly views, apply a filter, and inspect the threshold alert.
6. Open Compare consumers and compare consumers for an eligible month or complete year.
7. Download the CSV reports and usage trend PNG.
8. Add or edit a reading and observe that summaries and validation findings are recalculated.

## 8. Verification and Limitations

The current automated test suite has **32 passing tests** for calculations, validation, monthly/yearly period allocation, complete-year threshold behavior, export data flow, Flask routes, database constraints, safe seed/reset behavior, CSRF, and configured-database failure messaging. Python compilation and a seeded dashboard response check also passed.

The app was run using SQLite in the available environment. A live MySQL server was not available, so MySQL connectivity has not been verified. Calendar summaries require exact period-boundary readings; spanning intervals remain unallocated rather than estimated. The interactive Chart.js chart requires browser access to its CDN. Authentication, pagination, and production deployment hardening are outside the current prototype scope.
