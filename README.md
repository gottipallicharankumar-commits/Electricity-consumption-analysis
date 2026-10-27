# Electricity Consumption Analysis System

Project 18 | College demonstration prototype

## Abstract

Gridline manages synthetic electricity consumers, meters, and dated cumulative meter readings. It validates readings, calculates safe consecutive-reading intervals, summarizes consumption where calendar boundaries are supported, and flags usage above a configurable threshold. It is an analysis tool, not a utility billing system.

## Problem Statement and Objectives

Cumulative readings are easy to mistake for interval usage, and an unexplained meter decrease can produce misleading negative consumption. This system keeps readings and interval calculations separate, identifies questionable records, avoids mixing meters, and makes month/year reporting assumptions visible.

Objectives:

- Manage consumers, regions, meters, and dated readings.
- Reject duplicate meter/date entries and invalid values.
- Exclude decreasing or otherwise invalid intervals from normal totals.
- Provide monthly/yearly reports, validation findings, usage alerts, CSV exports, and PNG charts.
- Make calculations runnable without a live MySQL service using explicit SQLite demo mode.

## Scope and Limitations

The included data is synthetic and for demonstration only. Energy is measured in kWh. No hardware, paid API, authentication, billing, or official tariff calculation is included. This local college prototype is not production-secure or designed for sensitive customer records.

## Features

- Consumer, meter, and reading create/list/edit/delete workflows. Deletion is restricted by foreign keys when dependent records exist.
- Consumer type and region are selected from dropdowns; current legacy values remain available when editing existing consumer records.
- Searchable tables and reading date/meter/region filters.
- Reading validation for first readings, duplicates, negative values, decreases/possible reset or rollover, and unusually large increases.
- Multiple dated readings are supported for each meter. A meter/date pair is unique; new entries must be later than that meter's latest reading. Successful saves report calculated consumption, while decreases are retained as possible reset/rollover cases and excluded from ordinary totals.
- NumPy-backed consecutive-reading subtraction and Pandas grouping.
- Monthly/yearly summaries, filters, threshold alerts, CSV downloads, and generated PNG usage charts.
- Consumer-to-consumer comparison chart and table for a selected eligible reporting period; incomplete periods and unallocated intervals are excluded.
- Responsive dashboard showing current database counts, allocated usage, latest readings, validation findings, regional totals, and alerts.
- CSRF-protected state-changing forms.

## Technology Stack

- Python and Flask: server-side application and routes.
- SQLAlchemy Core: parameter-bound queries shared by MySQL and SQLite.
- MySQL 8 with InnoDB: primary database; SQLite is an explicit development/demo fallback only when `DATABASE_URL` is blank.
- Pandas and NumPy: reading normalization, chronological processing, and numerical aggregation.
- Matplotlib: downloadable PNG trend reports.
- Chart.js: interactive dashboard trend, loaded from its public CDN.
- Jinja2, HTML, CSS, and JavaScript: responsive presentation and table interactions.
- pytest: calculation and Flask workflow tests.
- python-dotenv: local `.env` configuration.

## Architecture

`app.py` registers Flask routes and connects request handling to `modules/repository.py`. `modules/models.py` defines portable SQLAlchemy Core tables; `database.py` creates the engine and creates missing tables without dropping data. `modules/validation.py` classifies reading issues. `modules/analysis.py` builds meter-specific intervals and calendar summaries. `modules/reports.py` produces CSV bytes and Matplotlib PNGs. Templates and assets live in `templates/` and `static/`.

## Database Schema

`consumers(consumer_id, consumer_type, region)` has one-to-many relationships with `meters(meter_id, consumer_id, meter_code)`. `meters` has one-to-many relationships with `meter_readings(reading_id, meter_id, reading_date, cumulative_kwh)`. Meter codes are unique; meter/date pairs are unique; foreign keys use RESTRICT; cumulative kWh is nonnegative. See [schema.sql](schema.sql).

## Calculation and Validation Assumptions

For each meter, readings are sorted chronologically. For consecutive valid readings:

`consumption_kwh = current_cumulative_kwh - previous_cumulative_kwh`

A first reading has unknown consumption. A negative cumulative value is invalid. If a later cumulative value decreases, the interval is flagged as a possible reset or rollover, never automatically corrected, and omitted from normal consumption. Duplicate meter/date rows invalidate adjacent affected intervals. A configurable large-jump rule raises a review issue but does not automatically invalidate usage.

NumPy is used for numerical differences and aggregation; Pandas is used for tabular sorting and report grouping. Different meters are always calculated independently.

### Period Allocation

An interval is allocated to a month only when readings exactly span from the first day of one month to the first day of the next. Yearly reports sum boundary-aligned monthly intervals within each calendar year; a single January 1-to-January 1 interval can also represent a complete year. A year is considered complete for threshold alerts only when its valid intervals form uninterrupted coverage from January 1 through January 1 of the following year. This conservative policy avoids falsely describing a cross-period interval as exact consumption. Spanning valid intervals appear in an `Unallocated (spanning)` row: computed kWh is shown separately as unallocated and excluded from allocated totals. Invalid intervals appear in an `Invalid interval` row. No proportional estimate is currently made. Insufficient data remains explicitly unallocated or labeled as an incomplete year.

High-usage checks compare only allocated, complete boundary-aligned periods against the configured absolute kWh threshold. The default is 120 kWh. A threshold alert is a review signal, not a confirmed fault, waste event, emergency, or bill.

## Setup

### macOS / Linux

From the project directory:

```sh
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
cp .env.example .env
python scripts/seed_database.py
python app.py
```

### Windows PowerShell

```powershell
py -3 -m venv .venv
.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
Copy-Item .env.example .env
python scripts/seed_database.py
python app.py
```

Open <http://127.0.0.1:5000>. The app starts in local development mode; do not expose it directly to the internet.

### Database Configuration

Without a `DATABASE_URL`, the application explicitly uses `SQLITE_PATH` (default: `instance/electricity_demo.db`). It does not silently replace a configured MySQL database with SQLite. To use MySQL 8:

1. Install and start MySQL using the official [MySQL installation documentation](https://dev.mysql.com/doc/).
2. Create a database, for example `CREATE DATABASE electricity_analysis CHARACTER SET utf8mb4;`.
3. Set in `.env`: `DATABASE_URL=mysql+pymysql://YOUR_USER:YOUR_PASSWORD@localhost/electricity_analysis`.
4. Seed with `python scripts/seed_database.py` or initialize tables by starting the app. Existing tables/records are not dropped during startup.

Do not put real credentials in source control. `.env` is ignored by git. `schema.sql` is provided for inspection or manual MySQL setup.

### Vercel Deployment

Vercel deployments require `FLASK_SECRET_KEY` and `DATABASE_URL` environment variables. Configure `DATABASE_URL` with a reachable managed MySQL database, for example `mysql+pymysql://USER:PASSWORD@HOST/DATABASE`; SQLite files in `instance/` are local-development storage only and are not included in Git or persistent on Vercel. Existing local SQLite records are not automatically copied to the managed database. Configure these variables in the Vercel project settings for each deployment environment, then redeploy.

To adjust high usage and jump detection, set `HIGH_USAGE_THRESHOLD_KWH` and `LARGE_JUMP_MULTIPLIER` in `.env`.

## Demo Data and Reset

`data/sample_readings.csv` contains synthetic North/Central/South consumer records over 2024 and 2025, including ordinary usage, a commercial threshold example, and a separate meter with a decreasing reading. The seed command refuses to proceed when existing consumers or meter codes are found.

Reset is explicitly guarded and only accepts a database whose existing consumer types and meter codes are all demo-prefixed:

```sh
APP_ENV=development python scripts/seed_database.py --reset-demo
```

PowerShell:

```powershell
$env:APP_ENV = "development"
python scripts/seed_database.py --reset-demo
```

The reset deletes only data after the guard confirms the database contains demo-only records. Back up any database before using reset.

## Testing

```sh
python -m pytest -q
```

The tests use isolated temporary SQLite databases and do not connect to or delete MySQL data. They cover reading order and arithmetic, first readings, negative/decreasing values, duplicate dates, meter separation, invalid interval exclusion, month/year boundaries, spanning-period allocation, threshold fairness, CSV/PNG output, and core routes.

## Reports and Exports

- Monthly/yearly consumption, threshold alert list, and report filters: **Reports** in the application.
- Reading validation findings: **Validation** in the application.
- Usage trend PNG: `GET /charts/usage-trend.png`.
- CSV downloads: `/export/monthly.csv`, `/export/high-usage.csv`, and `/export/validation.csv`.
- Downloads stream directly; generated files are not automatically written to disk. `charts/` and `exports/` are reserved for optional local copies.
- CSVs include report name and UTC generation timestamp. Report assumptions are stated in the interface and this document.

## Consumer Comparison

Open **Compare consumers** in the navigation or visit `/analysis/consumers`. Select monthly or yearly and an available reporting period, then optionally filter by consumer and region. The comparison chart and table aggregate valid, allocated usage per consumer. Monthly comparisons require a complete boundary-aligned month; annual comparisons require uninterrupted full-year coverage. Unallocated and incomplete periods are not compared.

## Screenshots Checklist

For a college submission, capture: dashboard with seeded data; consumer and meter registries; reading history; validation findings including the possible reset; monthly and yearly reports; and a high-usage alert. Keep the synthetic/demo label visible.

## Known Limitations and Future Enhancements

- MySQL connectivity must be configured and tested in an environment with a running MySQL server; this workspace did not have a MySQL client/server available.
- Dashboard Chart.js requires browser access to the CDN; PNG generation is local via Matplotlib.
- Exact boundary readings are required for calendar allocation; there is no estimated split, relative detector, authentication, pagination, or production deployment configuration.
- Suggested extensions: configurable interval allocation strategies, authenticated roles, migrations, audit history, export scheduling, and deployment hardening.
