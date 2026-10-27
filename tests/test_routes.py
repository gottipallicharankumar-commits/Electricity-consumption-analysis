import pytest
import csv
from io import StringIO
from sqlalchemy import delete, insert, select
from sqlalchemy.exc import IntegrityError

from app import create_app
from config import Config
from modules.models import consumers, meter_readings, meters
from modules.repository import count_records


def test_core_pages_render(client):
    for path in ("/", "/consumers", "/meters", "/readings", "/reports", "/validation", "/analysis/consumers"):
        assert client.get(path).status_code == 200


def test_consumer_type_and_region_render_as_select_controls(client):
    body = client.get("/consumers").get_data(as_text=True)
    assert '<select name="consumer_type"' in body
    assert '<select name="region"' in body
    assert '<option value="Residential">Residential</option>' in body
    assert '<option value="Central">Central</option>' in body


def test_consumer_dropdown_values_are_validated_on_server(client, app):
    response = client.post("/consumers", data={"consumer_type": "Residential", "region": "North"})
    assert response.status_code == 302
    assert count_records(app.extensions["db_engine"], consumers) == 1
    response = client.post("/consumers", data={"consumer_type": "Invented Type", "region": "North"})
    assert response.status_code == 302
    assert count_records(app.extensions["db_engine"], consumers) == 1


def test_legacy_consumer_values_are_scoped_to_the_existing_record(client, app):
    with app.extensions["db_engine"].begin() as connection:
        legacy_id = connection.execute(
            insert(consumers).values(consumer_type="Legacy Housing", region="Old District")
        ).inserted_primary_key[0]
        standard_id = connection.execute(
            insert(consumers).values(consumer_type="Residential", region="North")
        ).inserted_primary_key[0]

    body = client.get("/consumers").get_data(as_text=True)
    legacy_row = body.split(f'id="consumer-edit-{legacy_id}"', 1)[0].rsplit("<tr>", 1)[-1]
    standard_row = body.split(f'id="consumer-edit-{standard_id}"', 1)[0].rsplit("<tr>", 1)[-1]
    assert "Legacy Housing" in legacy_row and "Old District" in legacy_row
    assert "Legacy Housing" not in standard_row and "Old District" not in standard_row

    rejected_create = client.post("/consumers", data={"consumer_type": "Legacy Housing", "region": "Old District"})
    assert rejected_create.status_code == 302
    assert count_records(app.extensions["db_engine"], consumers) == 2

    rejected_edit = client.post(
        f"/consumers/{standard_id}/edit",
        data={"consumer_type": "Legacy Housing", "region": "Old District"},
    )
    assert rejected_edit.status_code == 302
    with app.extensions["db_engine"].connect() as connection:
        stored_type = connection.execute(
            select(consumers.c.consumer_type).where(consumers.c.consumer_id == standard_id)
        ).scalar_one()
    assert stored_type == "Residential"
    assert count_records(app.extensions["db_engine"], consumers) == 2


def test_consumer_comparison_page_uses_real_period_data(client):
    client.post("/consumers", data={"consumer_type": "Residential", "region": "North"})
    client.post("/meters", data={"consumer_id": "1", "meter_code": "COMPARE-1"})
    for month in range(1, 13):
        client.post("/readings", data={"meter_id": "1", "reading_date": f"2024-{month:02d}-01", "cumulative_kwh": str(month * 100)})
    client.post("/readings", data={"meter_id": "1", "reading_date": "2025-01-01", "cumulative_kwh": "1300"})
    response = client.get("/analysis/consumers?period=year&selected_period=2024")
    body = response.get_data(as_text=True)
    assert response.status_code == 200
    assert "COMPARE-1" not in body
    assert "1200.000 kWh" in body


def test_csrf_rejects_state_change_without_token(tmp_path):
    protected_app = create_app({
        "TESTING": True,
        "DATABASE_URL": f"sqlite:///{tmp_path / 'csrf.db'}",
    })
    try:
        response = protected_app.test_client().post(
            "/consumers", data={"consumer_type": "Residential", "region": "North"}
        )
        assert response.status_code == 400
    finally:
        protected_app.extensions["db_engine"].dispose()


def test_non_development_requires_configured_secret():
    with pytest.raises(RuntimeError, match="Set FLASK_SECRET_KEY"):
        create_app({"ENVIRONMENT": "production", "SECRET_KEY_CONFIGURED": False})


def test_non_development_requires_persistent_database(monkeypatch):
    monkeypatch.setattr(Config, "DATABASE_URL", "")
    monkeypatch.setattr(Config, "ENVIRONMENT", "production")
    with pytest.raises(RuntimeError, match="DATABASE_URL.*persistent database"):
        Config.database_url()


def test_add_consumer_meter_readings_and_export(client, app):
    response = client.post("/consumers", data={"consumer_type": "Residential", "region": "North"})
    assert response.status_code == 302
    response = client.post("/meters", data={"consumer_id": "1", "meter_code": "TEST-1"})
    assert response.status_code == 302
    client.post("/readings", data={"meter_id": "1", "reading_date": "2024-01-01", "cumulative_kwh": "10"})
    client.post("/readings", data={"meter_id": "1", "reading_date": "2024-02-01", "cumulative_kwh": "40"})
    assert count_records(app.extensions["db_engine"], consumers) == 1
    assert count_records(app.extensions["db_engine"], meters) == 1
    assert count_records(app.extensions["db_engine"], meter_readings) == 2
    assert client.get("/export/monthly.csv").mimetype == "text/csv"
    assert client.get("/charts/usage-trend.png").data.startswith(b"\x89PNG")


def test_exports_include_calculated_values_and_png_receives_summary(client, app, monkeypatch):
    client.post("/consumers", data={"consumer_type": "Residential", "region": "North"})
    client.post("/meters", data={"consumer_id": "1", "meter_code": "EXPORT-1"})
    client.post("/readings", data={"meter_id": "1", "reading_date": "2024-01-01", "cumulative_kwh": "10"})
    client.post("/readings", data={"meter_id": "1", "reading_date": "2024-02-01", "cumulative_kwh": "260"})

    monthly = client.get("/export/monthly.csv").get_data(as_text=True)
    high_usage = client.get("/export/high-usage.csv").get_data(as_text=True)
    assert "2024-01" in monthly and "250.0" in monthly
    assert "EXPORT-1" in high_usage and "150.0" in high_usage
    assert "filename=monthly-consumption.csv" in client.get("/export/monthly.csv").headers["Content-Disposition"]
    assert "filename=yearly-consumption.csv" in client.get("/export/monthly.csv?period=year").headers["Content-Disposition"]

    captured = {}
    def capture_chart(summary):
        captured["summary"] = summary.copy()
        return b"png-test"
    monkeypatch.setattr("app.trend_png", capture_chart)
    chart = client.get("/charts/usage-trend.png")
    assert chart.data == b"png-test"
    assert captured["summary"].iloc[0].consumption_kwh == 250


def test_reports_explain_unallocated_intervals(client):
    client.post("/consumers", data={"consumer_type": "Residential", "region": "North"})
    client.post("/meters", data={"consumer_id": "1", "meter_code": "SPAN-1"})
    client.post("/readings", data={"meter_id": "1", "reading_date": "2024-01-15", "cumulative_kwh": "10"})
    client.post("/readings", data={"meter_id": "1", "reading_date": "2024-04-15", "cumulative_kwh": "410"})
    body = client.get("/reports").get_data(as_text=True)
    assert "Unallocated (spanning)" in body
    assert "Valid consumption spans periods; no allocation estimated" in body


def test_validation_csv_contains_real_reading_issue(client):
    client.post("/consumers", data={"consumer_type": "Residential", "region": "North"})
    client.post("/meters", data={"consumer_id": "1", "meter_code": "RESET-1"})
    client.post("/readings", data={"meter_id": "1", "reading_date": "2024-01-01", "cumulative_kwh": "100"})
    client.post("/readings", data={"meter_id": "1", "reading_date": "2024-02-01", "cumulative_kwh": "20"})
    response = client.get("/export/validation.csv")
    text = response.get_data(as_text=True)
    assert response.mimetype == "text/csv"
    assert "Cumulative reading decreased; possible reset or rollover" in text
    assert "RESET-1" in text and "Verify the meter history" in text


def test_duplicate_meter_date_rejected_by_database(client, app):
    client.post("/consumers", data={"consumer_type": "Residential", "region": "North"})
    client.post("/meters", data={"consumer_id": "1", "meter_code": "TEST-1"})
    client.post("/readings", data={"meter_id": "1", "reading_date": "2024-01-01", "cumulative_kwh": "10"})
    client.post("/readings", data={"meter_id": "1", "reading_date": "2024-01-01", "cumulative_kwh": "20"})
    assert count_records(app.extensions["db_engine"], meter_readings) == 1


def test_reading_workflow_calculates_consumption_and_confirms_success(client, app):
    client.post("/consumers", data={"consumer_type": "Commercial", "region": "South"})
    client.post("/meters", data={"consumer_id": "1", "meter_code": "MTR-001"})
    first = client.post("/readings", data={"meter_id": "1", "reading_date": "2026-10-01", "cumulative_kwh": "1250"}, follow_redirects=True)
    assert "No previous reading exists" in first.get_data(as_text=True)

    second = client.post("/readings", data={"meter_id": "1", "reading_date": "2026-10-27", "cumulative_kwh": "1450"}, follow_redirects=True)
    assert "Consumption since the previous reading: 200.000 kWh" in second.get_data(as_text=True)
    assert count_records(app.extensions["db_engine"], meter_readings) == 2


def test_saved_spanning_interval_flows_through_validation_reports_and_exports(client, app):
    client.post("/consumers", data={"consumer_type": "Commercial", "region": "South"})
    client.post("/meters", data={"consumer_id": "1", "meter_code": "MTR-001"})
    client.post("/readings", data={"meter_id": "1", "reading_date": "2026-10-01", "cumulative_kwh": "1250"})
    client.post("/readings", data={"meter_id": "1", "reading_date": "2026-10-27", "cumulative_kwh": "1450"})

    interval_page = client.get("/validation").get_data(as_text=True)
    assert "1250.000 kWh" in interval_page
    assert "1450.000 kWh" in interval_page
    assert "200.000" in interval_page

    report_page = client.get("/reports").get_data(as_text=True)
    assert "Unallocated (spanning)" in report_page
    assert "200.000" in report_page

    summary_csv = client.get("/export/monthly.csv").get_data(as_text=True)
    summary_row = next(csv.DictReader(StringIO(summary_csv)))
    assert summary_row["period"] == "Unallocated (spanning)"
    assert float(summary_row["consumption_kwh"]) == 0
    assert float(summary_row["unallocated_kwh"]) == 200

    alerts_csv = client.get("/export/high-usage.csv").get_data(as_text=True)
    assert "MTR-001" not in alerts_csv
    chart = client.get("/charts/usage-trend.png")
    assert chart.status_code == 200
    assert chart.mimetype == "image/png"
    assert chart.data.startswith(b"\x89PNG\r\n\x1a\n")

    with app.extensions["db_engine"].connect() as connection:
        rows = connection.execute(
            select(meter_readings.c.reading_id, meter_readings.c.reading_date)
            .where(meter_readings.c.meter_id == 1)
            .order_by(meter_readings.c.reading_date)
        ).all()
    assert len(rows) == 2
    assert rows[0].reading_id != rows[1].reading_id


@pytest.mark.parametrize(
    ("reading_date", "cumulative_kwh", "message"),
    [
        ("2026-09-30", "1300", "later than the latest reading"),
        ("bad-date", "1400", "valid reading date"),
        ("2026-10-28", "-1", "cannot be negative"),
        ("2026-10-28", "not-a-number", "numeric cumulative kWh"),
    ],
)
def test_invalid_or_out_of_order_readings_are_rejected(client, app, reading_date, cumulative_kwh, message):
    client.post("/consumers", data={"consumer_type": "Commercial", "region": "South"})
    client.post("/meters", data={"consumer_id": "1", "meter_code": "MTR-001"})
    client.post("/readings", data={"meter_id": "1", "reading_date": "2026-10-01", "cumulative_kwh": "1250"})
    response = client.post(
        "/readings",
        data={"meter_id": "1", "reading_date": reading_date, "cumulative_kwh": cumulative_kwh},
        follow_redirects=True,
    )
    assert message in response.get_data(as_text=True)
    assert count_records(app.extensions["db_engine"], meter_readings) == 1


def test_duplicate_reading_has_clear_message_and_reset_uses_existing_rules(client, app):
    client.post("/consumers", data={"consumer_type": "Commercial", "region": "South"})
    client.post("/meters", data={"consumer_id": "1", "meter_code": "MTR-001"})
    client.post("/readings", data={"meter_id": "1", "reading_date": "2026-10-01", "cumulative_kwh": "1250"})
    duplicate = client.post(
        "/readings", data={"meter_id": "1", "reading_date": "2026-10-01", "cumulative_kwh": "1260"}, follow_redirects=True
    )
    assert "A reading already exists for this meter on this date." in duplicate.get_data(as_text=True)
    assert count_records(app.extensions["db_engine"], meter_readings) == 1

    reset = client.post(
        "/readings", data={"meter_id": "1", "reading_date": "2026-10-27", "cumulative_kwh": "50"}, follow_redirects=True
    )
    assert "possible reset or rollover" in reset.get_data(as_text=True)
    assert count_records(app.extensions["db_engine"], meter_readings) == 2


def test_meter_with_readings_cannot_be_reassigned(client, app):
    client.post("/consumers", data={"consumer_type": "Residential", "region": "North"})
    client.post("/consumers", data={"consumer_type": "Commercial", "region": "South"})
    client.post("/meters", data={"consumer_id": "1", "meter_code": "HISTORY-1"})
    client.post("/readings", data={"meter_id": "1", "reading_date": "2024-01-01", "cumulative_kwh": "10"})
    response = client.post("/meters/1/edit", data={"consumer_id": "2", "meter_code": "HISTORY-1"})
    assert response.status_code == 302
    with app.extensions["db_engine"].connect() as connection:
        stored = connection.execute(
            select(meters.c.consumer_id).where(meters.c.meter_id == 1)
        ).scalar_one()
    assert stored == 1


def test_foreign_keys_reject_orphans_and_restrict_consumer_delete(app):
    engine = app.extensions["db_engine"]
    with pytest.raises(IntegrityError):
        with engine.begin() as connection:
            connection.execute(insert(meters).values(consumer_id=999, meter_code="ORPHAN"))
    with engine.begin() as connection:
        consumer_id = connection.execute(insert(consumers).values(consumer_type="Residential", region="North")).inserted_primary_key[0]
        connection.execute(insert(meters).values(consumer_id=consumer_id, meter_code="LINKED"))
    with pytest.raises(IntegrityError):
        with engine.begin() as connection:
            connection.execute(delete(consumers).where(consumers.c.consumer_id == consumer_id))


def test_unavailable_configured_mysql_reports_actionable_error():
    with pytest.raises(RuntimeError, match="SQLite is selected only when DATABASE_URL is blank"):
        create_app({
            "TESTING": True,
            "DATABASE_URL": "mysql+pymysql://demo:demo@127.0.0.1:1/electricity_analysis",
        })