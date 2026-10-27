"""Flask entry point for the Electricity Consumption Analysis System."""

from __future__ import annotations

from datetime import date

import pandas as pd
from flask import Flask, Response, flash, redirect, render_template, request, url_for
from flask_wtf.csrf import CSRFProtect
from sqlalchemy.exc import IntegrityError, SQLAlchemyError

from config import Config
from database import create_database_engine, initialize_schema
from modules.analysis import calculate_intervals, compare_consumers, high_usage_alerts, summarize_periods
from modules.models import consumers, meter_readings, meters
from modules.reports import csv_bytes, trend_png
from modules.repository import (
    count_records,
    delete_record,
    list_consumers,
    list_meters,
    list_readings,
    list_table,
    parse_date,
    save_consumer,
    save_meter,
    save_reading,
)

CONSUMER_TYPE_OPTIONS = ("Residential", "Commercial", "Industrial", "Institutional", "Agricultural", "Other")
REGION_OPTIONS = ("North", "South", "East", "West", "Central", "Northeast", "Northwest", "Southeast", "Southwest", "Other")


def create_app(test_config: dict | None = None) -> Flask:
    app = Flask(__name__)
    app.config.from_object(Config)
    if test_config:
        app.config.update(test_config)
    if app.config["ENVIRONMENT"] != "development" and not app.config.get("SECRET_KEY_CONFIGURED"):
        raise RuntimeError("Set FLASK_SECRET_KEY to a strong random value outside development mode.")
    csrf = CSRFProtect(app)
    del csrf
    engine = create_database_engine(app.config["DATABASE_URL"] or Config.database_url())
    try:
        initialize_schema(engine)
    except SQLAlchemyError as error:
        engine.dispose()
        raise RuntimeError(
            "Could not initialize the configured database. Verify DATABASE_URL, server availability, and database permissions. "
            "SQLite is selected only when DATABASE_URL is blank."
        ) from error
    app.extensions["db_engine"] = engine

    @app.errorhandler(SQLAlchemyError)
    def handle_database_error(error: SQLAlchemyError):
        app.logger.warning("Database operation failed: %s", error.__class__.__name__)
        original_error = str(getattr(error, "orig", error)).lower()
        if "uq_reading_meter_date" in original_error or "meter_readings.meter_id, meter_readings.reading_date" in original_error:
            flash("A reading already exists for this meter on this date.", "error")
            return redirect(request.referrer or url_for("readings_page"))
        flash("The database rejected that change. Check for duplicate values or dependent records.", "error")
        return redirect(request.referrer or url_for("dashboard"))

    @app.errorhandler(ValueError)
    def handle_invalid_input(error: ValueError):
        flash(str(error) or "Check the submitted values and try again.", "error")
        return redirect(request.referrer or url_for("dashboard"))

    @app.get("/")
    def dashboard():
        records = list_readings(engine)
        summary, issues = summarize_periods(records, "month", large_jump_multiplier=app.config["LARGE_JUMP_MULTIPLIER"])
        alerts = high_usage_alerts(summary, app.config["HIGH_USAGE_THRESHOLD_KWH"])
        _, _, findings = calculate_intervals(records, app.config["LARGE_JUMP_MULTIPLIER"])
        if not findings.empty:
            findings = findings.sort_values("reading_date", ascending=False)
        allocated = summary[summary["valid_intervals"] > 0] if not summary.empty else summary
        trend = allocated.groupby("period", as_index=False)["consumption_kwh"].sum().tail(12) if not allocated.empty else pd.DataFrame(columns=["period", "consumption_kwh"])
        region = summary.groupby("region", as_index=False)["consumption_kwh"].sum().sort_values("consumption_kwh", ascending=False) if not summary.empty else pd.DataFrame(columns=["region", "consumption_kwh"])
        return render_template(
            "dashboard.html", consumers=count_records(engine, consumers), meters=count_records(engine, meters),
            readings=count_records(engine, meter_readings), issues=findings.to_dict("records"), alerts=alerts.to_dict("records"),
            total=float(summary["consumption_kwh"].sum()) if not summary.empty else 0,
            trend=trend.to_dict("records"), regions=region.to_dict("records"), recent=records[:8],
        )

    @app.route("/consumers", methods=["GET", "POST"])
    def consumers_page():
        existing_consumers = list_consumers(engine)
        if request.method == "POST":
            values = _required_choices(request.form, {"consumer_type": CONSUMER_TYPE_OPTIONS, "region": REGION_OPTIONS})
            save_consumer(engine, values)
            flash("Consumer added.", "success")
            return redirect(url_for("consumers_page"))
        edit_options = {
            item["consumer_id"]: {
                "consumer_types": _with_existing_options(CONSUMER_TYPE_OPTIONS, [item], "consumer_type"),
                "regions": _with_existing_options(REGION_OPTIONS, [item], "region"),
            }
            for item in existing_consumers
        }
        return render_template(
            "consumers.html", consumers=existing_consumers,
            consumer_types=CONSUMER_TYPE_OPTIONS, regions=REGION_OPTIONS,
            edit_options=edit_options,
        )

    @app.post("/consumers/<int:consumer_id>/edit")
    def edit_consumer(consumer_id: int):
        current = next((item for item in list_consumers(engine) if item["consumer_id"] == consumer_id), None)
        if current is None:
            return "Consumer not found", 404
        choices = {
            "consumer_type": _with_existing_options(CONSUMER_TYPE_OPTIONS, [current], "consumer_type"),
            "region": _with_existing_options(REGION_OPTIONS, [current], "region"),
        }
        save_consumer(engine, _required_choices(request.form, choices), consumer_id)
        flash("Consumer updated.", "success")
        return redirect(url_for("consumers_page"))

    @app.post("/consumers/<int:consumer_id>/delete")
    def remove_consumer(consumer_id: int):
        delete_record(engine, "consumer", consumer_id)
        flash("Consumer deleted.", "success")
        return redirect(url_for("consumers_page"))

    @app.route("/meters", methods=["GET", "POST"])
    def meters_page():
        if request.method == "POST":
            consumer_id = _positive_int(request.form.get("consumer_id"), "Select a valid consumer.")
            code = request.form.get("meter_code", "").strip()
            _validate_meter_code(code)
            from modules.repository import save_meter
            save_meter(engine, {"consumer_id": consumer_id, "meter_code": code})
            flash("Meter added.", "success")
            return redirect(url_for("meters_page"))
        return render_template("meters.html", meters=list_meters(engine), consumers=list_consumers(engine))

    @app.post("/meters/<int:meter_id>/edit")
    def edit_meter(meter_id: int):
        values = {"consumer_id": _positive_int(request.form.get("consumer_id"), "Select a valid consumer."), "meter_code": request.form.get("meter_code", "").strip()}
        _validate_meter_code(values["meter_code"])
        from modules.repository import save_meter
        save_meter(engine, values, meter_id)
        flash("Meter updated.", "success")
        return redirect(url_for("meters_page"))

    @app.post("/meters/<int:meter_id>/delete")
    def remove_meter(meter_id: int):
        delete_record(engine, "meter", meter_id)
        flash("Meter deleted.", "success")
        return redirect(url_for("meters_page"))

    @app.route("/readings", methods=["GET", "POST"])
    def readings_page():
        if request.method == "POST":
            values = _reading_form_values(request.form)
            result = save_reading(engine, values)
            _flash_reading_result("Reading recorded", result)
            return redirect(url_for("readings_page"))
        filters = {"meter_id": request.args.get("meter_id"), "region": request.args.get("region"), "start_date": _date_filter("start_date"), "end_date": _date_filter("end_date")}
        return render_template("readings.html", readings=list_readings(engine, filters), meters=list_meters(engine), regions=sorted({meter["region"] for meter in list_meters(engine)}))

    @app.post("/readings/<int:reading_id>/edit")
    def edit_reading(reading_id: int):
        values = _reading_form_values(request.form)
        result = save_reading(engine, values, reading_id)
        _flash_reading_result("Reading updated", result)
        return redirect(url_for("readings_page"))

    @app.post("/readings/<int:reading_id>/delete")
    def remove_reading(reading_id: int):
        delete_record(engine, "reading", reading_id)
        flash("Reading deleted; affected intervals will be recalculated.", "success")
        return redirect(url_for("readings_page"))

    @app.get("/validation")
    def validation_page():
        _, intervals, issues = calculate_intervals(list_readings(engine), app.config["LARGE_JUMP_MULTIPLIER"])
        return render_template("validation.html", issues=issues.to_dict("records"), intervals=intervals.to_dict("records"))

    @app.get("/reports")
    def reports_page():
        records = list_readings(engine)
        filters = _report_filters()
        summary, issues = summarize_periods(records, request.args.get("period", "month"), filters=filters, large_jump_multiplier=app.config["LARGE_JUMP_MULTIPLIER"])
        alerts = high_usage_alerts(summary, app.config["HIGH_USAGE_THRESHOLD_KWH"])
        return render_template("reports.html", summary=summary.to_dict("records"), alerts=alerts.to_dict("records"), issues=issues.to_dict("records"), period=request.args.get("period", "month"), threshold=app.config["HIGH_USAGE_THRESHOLD_KWH"], consumers=list_consumers(engine), meters=list_meters(engine), regions=sorted({meter["region"] for meter in list_meters(engine)}), filters=filters)

    @app.get("/analysis/consumers")
    def consumer_comparison_page():
        period = request.args.get("period", "month")
        records = list_readings(engine)
        summary, _ = summarize_periods(records, period, filters=_report_filters(), large_jump_multiplier=app.config["LARGE_JUMP_MULTIPLIER"])
        period_labels = sorted(
            label for label in summary.get("period", pd.Series(dtype=str)).astype(str).unique()
            if label.isdigit() or (len(label) == 7 and label[4] == "-")
        )
        selected_period = request.args.get("selected_period") or (period_labels[-1] if period_labels else None)
        comparison = compare_consumers(summary, selected_period)
        return render_template(
            "comparison.html", period=period, selected_period=selected_period,
            period_labels=period_labels, comparison=comparison.to_dict("records"),
            filters=_report_filters(), consumers=list_consumers(engine), meters=list_meters(engine),
            regions=sorted({meter["region"] for meter in list_meters(engine)}),
        )

    @app.get("/export/<kind>.csv")
    def export_csv(kind: str):
        records = list_readings(engine)
        summary, issues = summarize_periods(records, request.args.get("period", "month"), filters=_report_filters(), large_jump_multiplier=app.config["LARGE_JUMP_MULTIPLIER"])
        alerts = high_usage_alerts(summary, app.config["HIGH_USAGE_THRESHOLD_KWH"])
        frames = {"monthly": summary, "high-usage": alerts, "validation": issues}
        if kind not in frames:
            return "Not found", 404
        period_name = request.args.get("period", "month")
        filename = {
            "monthly": "yearly-consumption.csv" if period_name == "year" else "monthly-consumption.csv",
            "high-usage": "high-usage-alerts.csv",
            "validation": "reading-validation.csv",
        }[kind]
        return Response(csv_bytes(frames[kind], kind), mimetype="text/csv", headers={"Content-Disposition": f"attachment; filename={filename}"})

    @app.get("/charts/usage-trend.png")
    def export_chart():
        summary, _ = summarize_periods(list_readings(engine), "month", large_jump_multiplier=app.config["LARGE_JUMP_MULTIPLIER"])
        return Response(trend_png(summary), mimetype="image/png", headers={"Content-Disposition": "attachment; filename=usage-trend.png"})

    return app


def _required_text(form, fields: tuple[str, ...]) -> dict[str, str]:
    values = {field: form.get(field, "").strip() for field in fields}
    if any(not value for value in values.values()):
        raise ValueError("All fields are required.")
    if len(values["consumer_type"]) > 40 or len(values["region"]) > 80:
        raise ValueError("Consumer type or region is too long.")
    return values


def _required_choices(form, choices: dict[str, tuple[str, ...]]) -> dict[str, str]:
    values = {field: form.get(field, "").strip() for field in choices}
    if any(not value for value in values.values()):
        raise ValueError("Select a consumer type and region.")
    if any(values[field] not in allowed for field, allowed in choices.items()):
        raise ValueError("Choose a consumer type and region from the available options.")
    return values


def _with_existing_options(options: tuple[str, ...], existing: list[dict], field: str) -> tuple[str, ...]:
    legacy = sorted({str(item[field]) for item in existing if item[field] and item[field] not in options})
    return (*options, *legacy)


def _positive_int(value: str | None, message: str) -> int:
    parsed = int(value or "")
    if parsed <= 0:
        raise ValueError(message)
    return parsed


def _validate_meter_code(value: str) -> None:
    if not value:
        raise ValueError("Meter code is required.")
    if len(value) > 64:
        raise ValueError("Meter code must be 64 characters or fewer.")


def _report_filters() -> dict[str, str]:
    return {key: request.args.get(key, "") for key in ("consumer_id", "meter_id", "consumer_type", "region") if request.args.get(key, "")}


def _date_filter(field: str) -> date | None:
    value = request.args.get(field)
    return date.fromisoformat(value) if value else None


def _reading_form_values(form) -> dict[str, Any]:
    meter_id = _positive_int(form.get("meter_id"), "Select a valid meter.")
    try:
        reading_date = parse_date(form.get("reading_date", ""))
    except (TypeError, ValueError) as error:
        raise ValueError("Enter a valid reading date.") from error
    try:
        cumulative_kwh = float(form.get("cumulative_kwh", ""))
    except (TypeError, ValueError) as error:
        raise ValueError("Enter a numeric cumulative kWh reading.") from error
    return {"meter_id": meter_id, "reading_date": reading_date, "cumulative_kwh": cumulative_kwh}


def _flash_reading_result(action: str, result: dict[str, float | bool | None]) -> None:
    if result["possible_reset"]:
        flash(
            f"{action}; the cumulative value decreased. This interval is flagged as a possible reset or rollover and excluded from ordinary consumption.",
            "warning",
        )
    elif result["consumption_kwh"] is None:
        flash(f"{action}. No previous reading exists, so interval consumption is unknown.", "success")
    else:
        flash(f"{action}. Consumption since the previous reading: {result['consumption_kwh']:.3f} kWh.", "success")


app = create_app()


if __name__ == "__main__":
    app.run(debug=Config.ENVIRONMENT == "development")