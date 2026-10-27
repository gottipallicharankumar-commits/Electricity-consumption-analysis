# Project Handoff and Verification

## Project

Electricity Consumption Analysis System (Project 18), a Flask demo for synthetic consumers, meters, cumulative readings, validation, period reports, and high-usage alerts. MySQL 8/InnoDB is the intended primary database. A blank `DATABASE_URL` explicitly selects SQLite for local development.

## Verified Findings

- Consecutive readings are sorted and calculated independently per meter. First readings have unknown consumption; decreases are flagged as possible resets/rollovers and excluded; negative, non-finite, malformed-date, and duplicate-date intervals are invalid.
- Monthly allocation requires exact first-of-month boundaries. Yearly reports aggregate valid boundary-aligned monthly intervals; a year is complete for threshold alerts only with uninterrupted January 1-to-January 1 coverage. Partial years are labeled and do not trigger alerts.
- Multi-month/year spanning intervals are explicit unallocated rows with zero ordinary allocated kWh. Invalid intervals are in separate excluded rows. The Reports table displays allocation status.
- Threshold comparisons are strict `>` and apply only to complete reporting periods.
- Consumer comparison is available at `/analysis/consumers`; chart and table aggregate valid allocated usage for a selected eligible period and omit unallocated/incomplete periods.
- Monthly, high-usage, and validation CSV routes contain real calculated data. The PNG route receives analyzed summary data; output has a PNG signature and rendered-content checks.
- CSRF-less state changes are rejected. SQLite tests verify orphan rejection and restrictive deletes. Configured unavailable MySQL gives an actionable startup error instead of falling back to SQLite.
- Seed/reset tests use temporary SQLite databases. Reset accepts the exact shipped demo dataset and refuses changed/additional records without deleting them.
- A meter with historical readings cannot be reassigned to another consumer, preserving history attribution.
- Consumer type and region use dropdown controls on both create and edit forms; server validation rejects values not in the options, while existing legacy values remain selectable.
- Legacy consumer options are scoped to that same record's edit dropdown and are not accepted for new consumers or other records.
- Reading creation is transactional and verifies meter existence, strict ISO form date, finite nonnegative cumulative kWh, duplicate meter/date, and newest-date ordering. Duplicate and validation feedback is specific; successful saves report interval kWh; decreases save with a possible reset/rollover warning and no negative consumption.
- Validation now shows each consecutive pair, both cumulative values, calculated interval kWh, and validity/exclusion reason. Valid spanning-interval kWh is carried in `unallocated_kwh` and displayed/exported separately from ordinary allocated totals.

## Defects Fixed During Audit

- Annual reports treated monthly intervals as spanning; annual aggregation now totals them by year.
- Incomplete annual periods could have been presented as comparable alerts; annual completeness is checked and alerts are suppressed for incomplete years.
- Reports omitted explanations for unallocated/incomplete intervals; status is rendered in the summary table.
- Malformed imported dates could crash during interval comparisons/duration calculation; invalid dates are safely reported and excluded.
- NaN/Infinity values were not consistently classified; non-finite readings are now flagged and excluded.
- Demo reset previously relied on naming prefixes and could erase changed demo-prefixed data; it now verifies exact sample contents before deletion.
- Meter reassignment could retroactively change the consumer shown for historical readings; reassignment is blocked after readings exist.
- Default Flask secret was a known literal; development now uses an ephemeral random secret, and non-development startup requires an explicitly configured secret.
- Report download filenames now reflect monthly versus yearly summaries.

## Test Results

- Initial requested baseline: **17 passed in 0.28s** with `/usr/local/bin/python3 -m pytest -q`.
- Final suite after reading-entry fix: **45 passed in 0.89s** with `/usr/local/bin/python3 -m pytest -q`.
- Consumer-comparison regression slice: **3 passed** for aggregation eligibility, route-rendered calculated values, and page registration. A full-suite rerun is still required after these additions.
- Consumer dropdown regression tests included in the latest full suite: dropdown rendering and valid/invalid submitted choices.
- Python compilation passed with `/usr/local/bin/python3 -m compileall -q app.py config.py database.py modules scripts tests`.
- SQLAlchemy MySQL dialect DDL compilation passed and showed expected AUTO_INCREMENT, foreign-key, unique, numeric, and check declarations. This is not a live MySQL integration test.
- Seeded dashboard check returned HTTP 200 and showed the synthetic commercial alert and possible-reset issue.
- No existing database was reset or deleted during this audit. Seed/reset checks used temporary files.
- Latest read-only database check found 0 consumers, 0 meters, and 0 readings. No database changes were made during this bug review.
- Read-only SQLite check during this reading fix confirmed `reading_id` is the row primary key, and the sole unique reading index covers `(meter_id, reading_date)`. Multiple dates per meter are supported; there is no meter-ID-only unique constraint and no migration was needed.
- End-to-end test verified 2026-10-01 at 1250 kWh followed by 2026-10-27 at 1450 kWh saves two distinct reading IDs and reports 200 kWh; because the interval is not month-boundary aligned, it is shown as 200 unallocated kWh and excluded from allocated totals/alerts.
- The active SQLite database was inspected read-only before and after the change; no migration, reset, or direct data edit was performed.

## Database and Security Status

- SQLAlchemy Core uses bound parameters. Schema models include PKs, unique meter code, unique meter/date, nonnegative check, foreign keys with RESTRICT and ON UPDATE CASCADE; SQLite enables FK enforcement.
- `create_all` creates missing tables but does not migrate existing ones. Existing installations require explicit migration for schema changes.
- The existing meter/date uniqueness is already correct for one reading per meter per date; multiple dates for one meter are allowed. No schema migration was required for this fix.
- MySQL DDL compiles for the SQLAlchemy MySQL dialect, but live compatibility is **unverified** because no MySQL server/client was available. Confirm CHECK enforcement with the target MySQL 8 minor version and run integration tests against a dedicated test database before claiming server compatibility.
- CSRF is enabled; tests disable it in the standard test fixture and separately verify rejection when enabled. Non-development runs must set a strong `FLASK_SECRET_KEY`.
- No authentication, pagination, production deployment hardening, or estimated period allocation is implemented. Chart.js loads from a CDN; Matplotlib PNG generation is local.

## Environment and Run Commands

Verified terminal interpreter: macOS Python 3.14.6 at `/usr/local/bin/python3`. MySQL was unavailable. Default demo threshold is 120 kWh and large-jump multiplier is 3. Pylance diagnostics currently use a different interpreter and report NumPy/Pandas unresolved; terminal tests run successfully with the configured Framework Python or project virtual environment.

```sh
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
cp .env.example .env
python scripts/seed_database.py
python app.py
```

Open `http://127.0.0.1:5000`. The demo database already existed before this audit; the commands above are setup guidance, not commands rerun against that database. To use MySQL, configure `DATABASE_URL` in `.env`, create the database separately, then seed only an empty target database.

## Files Changed During This Audit

- Application files updated during this reading fix: `modules/repository.py`, `modules/analysis.py`, `app.py`, `templates/reports.html`, `templates/validation.html`, and `static/css/style.css`.
- Tests updated: `tests/test_routes.py`.
- Documentation updated: `README.md` and this file.

## Next Steps

1. Run MySQL 8 integration tests on a dedicated, disposable database and verify constraints/transaction behavior on the intended minor version.
2. Visually inspect all pages at mobile and desktop widths; verify Chart.js CDN access in the presentation environment.
3. If desired, implement schema migrations before upgrading an existing deployment and add server-side pagination for larger datasets.

## Current Demo Database State

- On 2026-10-27, verified all 51 stored readings matched the shipped synthetic CSV exactly, then removed only the three known sample meters, their readings, and the three corresponding demo consumers in a SQLite transaction.
- Preserved the separate user-added consumer (`Residential`, `North`, ID 4). Current counts verified after removal: 1 consumer, 0 meters, 0 readings.
- Verified `/`, `/consumers`, `/meters`, `/readings`, `/reports`, `/validation`, and `/analysis/consumers` each return HTTP 200 on the empty/sample-removed database.
- To restore the sample later, use the seed command only after deciding to load synthetic records into this database; the remaining consumer currently causes the seed's non-empty-database guard to refuse. Do not remove it automatically.
