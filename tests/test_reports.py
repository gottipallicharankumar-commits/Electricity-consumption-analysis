import pandas as pd

from modules.reports import csv_bytes, trend_png


def test_csv_has_units_and_expected_columns():
    payload = csv_bytes(pd.DataFrame([{"period": "2024-01", "consumption_kwh": 25}]), "monthly")
    text = payload.decode()
    assert "period,consumption_kwh,report_name,generated_at_utc" in text
    assert "2024-01,25,monthly," in text


def test_png_chart_is_generated():
    data = trend_png(pd.DataFrame([{"period": "2024-01", "consumption_kwh": 25}]))
    assert data.startswith(b"\x89PNG\r\n\x1a\n")


def test_png_contains_plotted_data_not_only_a_valid_header():
    from PIL import Image
    from io import BytesIO

    data = trend_png(pd.DataFrame([{"period": "2024-01", "consumption_kwh": 25, "valid_intervals": 1}]))
    image = Image.open(BytesIO(data)).convert("RGB")
    colors = image.getcolors(maxcolors=image.width * image.height)
    assert colors is not None
    assert len(colors) > 20