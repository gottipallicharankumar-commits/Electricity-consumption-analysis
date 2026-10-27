"""Consumption intervals and defensible calendar-period summaries."""

from __future__ import annotations

from datetime import date
from typing import Any

import numpy as np
import pandas as pd

from modules.validation import validate_readings


def calculate_intervals(records: list[dict[str, Any]], large_jump_multiplier: float = 3.0) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    readings, issues = validate_readings(records, large_jump_multiplier)
    intervals: list[dict[str, Any]] = []
    for meter_id, group in readings.groupby("meter_id", sort=False):
        ordered = group.sort_values("reading_date")
        previous = None
        for current in ordered.itertuples():
            if previous is not None:
                valid = (
                    _valid_reading(previous.cumulative_kwh, previous.reading_date)
                    and _valid_reading(current.cumulative_kwh, current.reading_date)
                    and not bool(getattr(previous, "duplicate_meter_date", False))
                    and not bool(getattr(current, "duplicate_meter_date", False))
                    and current.reading_date > previous.reading_date
                    and float(current.cumulative_kwh) >= float(previous.cumulative_kwh)
                )
                consumption = float(np.subtract(float(current.cumulative_kwh), float(previous.cumulative_kwh))) if valid else None
                days = (
                    (current.reading_date - previous.reading_date).days
                    if pd.notna(current.reading_date) and pd.notna(previous.reading_date)
                    else 0
                )
                if valid:
                    interval_status = "Valid interval"
                elif (
                    _valid_reading(previous.cumulative_kwh, previous.reading_date)
                    and _valid_reading(current.cumulative_kwh, current.reading_date)
                    and float(current.cumulative_kwh) < float(previous.cumulative_kwh)
                ):
                    interval_status = "Possible reset or rollover; excluded"
                else:
                    interval_status = "Invalid reading/date or duplicate date; excluded"
                intervals.append({
                    "meter_id": meter_id,
                    "meter_code": current.meter_code,
                    "consumer_id": current.consumer_id,
                    "consumer_type": current.consumer_type,
                    "region": current.region,
                    "start_date": previous.reading_date,
                    "end_date": current.reading_date,
                    "previous_cumulative_kwh": previous.cumulative_kwh,
                    "current_cumulative_kwh": current.cumulative_kwh,
                    "consumption_kwh": consumption,
                    "valid": bool(valid),
                    "status": interval_status,
                    "days": days,
                })
            previous = current
    return readings, pd.DataFrame(intervals), issues


def summarize_periods(
    records: list[dict[str, Any]],
    period: str = "month",
    *,
    filters: dict[str, Any] | None = None,
    large_jump_multiplier: float = 3.0,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Allocate only intervals matching exact calendar boundaries; leave others unallocated."""
    if period not in {"month", "year"}:
        raise ValueError("period must be 'month' or 'year'")
    filtered = _filter_records(records, filters or {})
    _, intervals, issues = calculate_intervals(filtered, large_jump_multiplier)
    if intervals.empty:
        return pd.DataFrame(columns=["period", "consumer_id", "meter_id", "meter_code", "region", "consumer_type", "consumption_kwh", "unallocated_kwh", "valid_intervals", "invalid_intervals", "unallocated_intervals", "complete_period", "status"]), issues
    intervals["period"] = intervals.apply(lambda row: _allocated_period(row.start_date, row.end_date, period) if row.valid else None, axis=1)
    allocated = intervals[intervals["valid"] & intervals["period"].notna()].copy()
    keys = ["consumer_id", "meter_id", "meter_code", "region", "consumer_type"]
    groups: list[dict[str, Any]] = []
    allocated_groups = allocated.groupby(["period", *keys], dropna=False).agg(
        consumption_kwh=("consumption_kwh", lambda values: float(np.sum(values.to_numpy(dtype=float)))),
        valid_intervals=("valid", "sum"),
        first_date=("start_date", "min"),
        last_date=("end_date", "max"),
    ).reset_index()
    for row in allocated_groups.to_dict("records"):
        matching = allocated[
            (allocated["period"] == row["period"])
            & (allocated["meter_id"] == row["meter_id"])
        ].sort_values("start_date")
        complete = _period_is_complete(row["period"], matching, period)
        row["complete_period"] = complete
        row.update(
            unallocated_kwh=0.0,
            invalid_intervals=0,
            unallocated_intervals=0,
            status=("Complete boundary-aligned period" if complete else "Incomplete period; threshold alert suppressed"),
        )
        groups.append(row)
    spanning = intervals[intervals["valid"] & intervals["period"].isna()]
    if not spanning.empty:
        for row in spanning.groupby(keys, dropna=False).agg(
            count=("valid", "size"),
            unallocated_kwh=("consumption_kwh", lambda values: float(np.sum(values.to_numpy(dtype=float)))),
        ).reset_index().to_dict("records"):
            row.update(period="Unallocated (spanning)", consumption_kwh=0.0, valid_intervals=0, invalid_intervals=0, unallocated_intervals=int(row.pop("count")), complete_period=False, status="Valid consumption spans periods; no allocation estimated")
            groups.append(row)
    invalid = intervals[~intervals["valid"]]
    if not invalid.empty:
        for row in invalid.groupby(keys, dropna=False).size().reset_index(name="count").to_dict("records"):
            row.update(period="Invalid interval", consumption_kwh=0.0, unallocated_kwh=0.0, valid_intervals=0, invalid_intervals=int(row.pop("count")), unallocated_intervals=0, complete_period=False, status="Excluded pending reading review")
            groups.append(row)
    summary = pd.DataFrame(groups)
    if summary.empty:
        return pd.DataFrame(columns=["period", "consumer_id", "meter_id", "meter_code", "region", "consumer_type", "consumption_kwh", "unallocated_kwh", "valid_intervals", "invalid_intervals", "unallocated_intervals", "complete_period", "status"]), issues
    summary["consumption_kwh"] = summary["consumption_kwh"].round(3)
    summary["unallocated_kwh"] = summary["unallocated_kwh"].round(3)
    return summary.sort_values(["period", "meter_code"]).reset_index(drop=True), issues


def high_usage_alerts(summary: pd.DataFrame, threshold_kwh: float) -> pd.DataFrame:
    """Alert only on complete calendar periods supported by boundary readings."""
    columns = ["consumer_id", "meter_id", "meter_code", "region", "period", "consumption_kwh", "threshold_kwh", "excess_kwh", "alert"]
    if summary.empty:
        return pd.DataFrame(columns=columns)
    complete = summary[summary["complete_period"] & (summary["valid_intervals"] > 0)]
    alerts = complete[complete["consumption_kwh"] > threshold_kwh].copy()
    if alerts.empty:
        return pd.DataFrame(columns=columns)
    alerts["threshold_kwh"] = float(threshold_kwh)
    alerts["excess_kwh"] = (alerts["consumption_kwh"] - float(threshold_kwh)).round(3)
    alerts["alert"] = "Threshold exceeded; review usage, not a confirmed fault"
    return alerts[columns].reset_index(drop=True)


def compare_consumers(summary: pd.DataFrame, period_label: str | None = None) -> pd.DataFrame:
    """Aggregate comparable allocated usage by consumer for a selected period."""
    columns = ["consumer_id", "consumer_type", "region", "period", "consumption_kwh", "valid_intervals", "meter_count"]
    if summary.empty:
        return pd.DataFrame(columns=columns)
    comparable = summary[
        summary["complete_period"]
        & (summary["valid_intervals"] > 0)
        & summary["period"].astype(str).str.match(r"^\d{4}(?:-\d{2})?$")
    ].copy()
    if period_label is not None:
        comparable = comparable[comparable["period"] == period_label]
    if comparable.empty:
        return pd.DataFrame(columns=columns)
    return (
        comparable.groupby(["consumer_id", "consumer_type", "region", "period"], as_index=False)
        .agg(
            consumption_kwh=("consumption_kwh", "sum"),
            valid_intervals=("valid_intervals", "sum"),
            meter_count=("meter_id", "nunique"),
        )
        .sort_values("consumption_kwh", ascending=False)
        .reset_index(drop=True)
    )[columns]


def _allocated_period(start: date, end: date, period: str) -> str | None:
    if not start or not end:
        return None
    if period == "month":
        first = start.replace(day=1)
        next_month = date(start.year + (start.month == 12), 1 if start.month == 12 else start.month + 1, 1)
        return f"{start.year:04d}-{start.month:02d}" if start == first and end == next_month else None
    if start == date(start.year, 1, 1) and end == date(start.year + 1, 1, 1):
        return str(start.year)
    if start.day == 1 and end.day == 1 and _next_month(start) == end:
        return str(start.year)
    return None


def _next_month(value: date) -> date:
    return date(value.year + (value.month == 12), 1 if value.month == 12 else value.month + 1, 1)


def _period_is_complete(period_label: str, intervals: pd.DataFrame, period: str) -> bool:
    if period == "month":
        return len(intervals) == 1
    year = int(period_label)
    ordered = intervals.sort_values("start_date")
    expected_start = date(year, 1, 1)
    expected_end = date(year + 1, 1, 1)
    if ordered.empty or ordered.iloc[0]["start_date"] != expected_start or ordered.iloc[-1]["end_date"] != expected_end:
        return False
    previous_end = expected_start
    for row in ordered.itertuples():
        if row.start_date != previous_end:
            return False
        previous_end = row.end_date
    return previous_end == expected_end


def _valid_reading(value: Any, reading_date: Any) -> bool:
    try:
        return reading_date is not None and not pd.isna(reading_date) and not pd.isna(value) and np.isfinite(float(value)) and float(value) >= 0
    except (TypeError, ValueError):
        return False


def _filter_records(records: list[dict[str, Any]], filters: dict[str, Any]) -> list[dict[str, Any]]:
    result = records
    for key in ("consumer_id", "meter_id", "consumer_type", "region"):
        target = filters.get(key)
        if target not in (None, ""):
            result = [record for record in result if str(record.get(key)) == str(target)]
    return result