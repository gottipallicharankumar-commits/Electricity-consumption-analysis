"""Validate cumulative readings and identify safe intervals for analysis."""

from __future__ import annotations

from collections import Counter
from datetime import date
from typing import Any

import numpy as np
import pandas as pd


READING_COLUMNS = ["reading_id", "meter_id", "meter_code", "consumer_id", "consumer_type", "region", "reading_date", "cumulative_kwh"]


def validate_readings(records: list[dict[str, Any]], large_jump_multiplier: float = 3.0) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Return normalized readings and issues; decreasing intervals are never consumed."""
    frame = pd.DataFrame(records)
    if frame.empty:
        return pd.DataFrame(columns=READING_COLUMNS), pd.DataFrame(columns=["meter_code", "reading_date", "reading_kwh", "issue", "severity", "action"])
    for column in READING_COLUMNS:
        if column not in frame:
            frame[column] = None
    frame["reading_date"] = pd.to_datetime(frame["reading_date"], format="%Y-%m-%d", errors="coerce").dt.date
    frame["cumulative_kwh"] = pd.to_numeric(frame["cumulative_kwh"], errors="coerce")
    frame = frame.sort_values(["meter_id", "reading_date", "reading_id"], na_position="last").reset_index(drop=True)
    issues: list[dict[str, Any]] = []

    duplicates = Counter((row.meter_id, row.reading_date) for row in frame.itertuples() if pd.notna(row.reading_date))
    frame["duplicate_meter_date"] = [
        bool(pd.notna(row.reading_date) and duplicates[(row.meter_id, row.reading_date)] > 1)
        for row in frame.itertuples()
    ]
    for row in frame.itertuples():
        date_value = row.reading_date
        value = row.cumulative_kwh
        if pd.isna(date_value):
            issues.append(_issue(row, "Invalid or missing reading date", "high", "Correct the date before analysis."))
        if pd.isna(value):
            issues.append(_issue(row, "Invalid or missing cumulative reading", "high", "Enter a numeric kWh value."))
        elif not np.isfinite(float(value)):
            issues.append(_issue(row, "Non-finite cumulative reading", "high", "Enter a finite numeric kWh value."))
        elif value < 0:
            issues.append(_issue(row, "Negative cumulative reading", "high", "Verify the source reading; negative values are excluded."))
        if pd.notna(date_value) and duplicates[(row.meter_id, date_value)] > 1:
            issues.append(_issue(row, "Duplicate meter/date reading", "high", "Keep one corrected reading for this meter and date."))

    for _, group in frame.groupby("meter_id", sort=False, dropna=False):
        previous = None
        for row in group.itertuples():
            if previous is None:
                issues.append(_issue(row, "First reading; no previous reading", "info", "Record a later reading to establish consumption."))
            elif pd.notna(row.cumulative_kwh) and pd.notna(previous.cumulative_kwh):
                delta = float(row.cumulative_kwh) - float(previous.cumulative_kwh)
                if delta < 0:
                    issues.append(_issue(row, "Cumulative reading decreased; possible reset or rollover", "high", "Verify the meter history; exclude this interval unless corrected explicitly."))
                elif (
                    delta > 0
                    and _is_valid_value(previous.cumulative_kwh)
                    and _is_valid_value(row.cumulative_kwh)
                    and pd.notna(row.reading_date)
                    and pd.notna(previous.reading_date)
                ):
                    duration_days = (row.reading_date - previous.reading_date).days
                    if duration_days > 0:
                        daily = delta / duration_days
                        baseline = _prior_daily_median(group, row.reading_date, large_jump_multiplier)
                        if baseline is not None and daily > baseline * large_jump_multiplier:
                            issues.append(_issue(row, "Unusually large increase", "medium", "Review the reading; a large increase is not automatically invalid."))
            previous = row
    return frame, pd.DataFrame(issues, columns=["meter_code", "reading_date", "reading_kwh", "issue", "severity", "action"])


def _is_valid_value(value: Any) -> bool:
    return not pd.isna(value) and float(value) >= 0


def _issue(row: Any, issue: str, severity: str, action: str) -> dict[str, Any]:
    return {
        "meter_code": getattr(row, "meter_code", None),
        "reading_date": getattr(row, "reading_date", None),
        "reading_kwh": getattr(row, "cumulative_kwh", None),
        "issue": issue,
        "severity": severity,
        "action": action,
    }


def _prior_daily_median(group: pd.DataFrame, current_date: date, multiplier: float) -> float | None:
    del multiplier
    prior = group[group["reading_date"] < current_date]
    if len(prior) < 3:
        return None
    values = prior["cumulative_kwh"].to_numpy(dtype=float)
    dates = pd.to_datetime(prior["reading_date"]).to_numpy()
    deltas = np.diff(values)
    days = np.diff(dates).astype("timedelta64[D]").astype(float)
    valid = (deltas >= 0) & (days > 0)
    if not valid.any():
        return None
    return float(np.median(deltas[valid] / days[valid]))