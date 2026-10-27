"""CSV and PNG report generation from analyzed application records."""

from __future__ import annotations

from datetime import datetime, timezone
from io import BytesIO, StringIO

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import pandas as pd


def csv_bytes(frame: pd.DataFrame, report_name: str) -> bytes:
    output = StringIO()
    export = frame.copy()
    export["report_name"] = report_name
    export["generated_at_utc"] = datetime.now(timezone.utc).isoformat()
    export.to_csv(output, index=False)
    return output.getvalue().encode("utf-8")


def trend_png(summary: pd.DataFrame) -> bytes:
    figure, axis = plt.subplots(figsize=(9, 4.5), constrained_layout=True)
    if not summary.empty and "valid_intervals" in summary:
        summary = summary[summary["valid_intervals"] > 0]
    if summary.empty:
        axis.text(0.5, 0.5, "No boundary-aligned consumption data", ha="center", va="center", transform=axis.transAxes)
        axis.set_axis_off()
    else:
        trend = summary.groupby("period", as_index=False)["consumption_kwh"].sum()
        axis.plot(trend["period"], trend["consumption_kwh"], color="#087f72", marker="o", linewidth=2)
        axis.set_ylabel("Consumption (kWh)")
        axis.set_xlabel("Reporting period")
        axis.tick_params(axis="x", rotation=35)
        axis.grid(axis="y", alpha=0.2)
        axis.spines[["top", "right"]].set_visible(False)
    buffer = BytesIO()
    figure.savefig(buffer, format="png", dpi=160, facecolor="white")
    plt.close(figure)
    return buffer.getvalue()