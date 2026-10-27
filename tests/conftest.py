from __future__ import annotations

import pytest

from app import create_app


@pytest.fixture
def app(tmp_path):
    database_path = tmp_path / "test.db"
    application = create_app({
        "TESTING": True,
        "WTF_CSRF_ENABLED": False,
        "DATABASE_URL": f"sqlite:///{database_path}",
        "HIGH_USAGE_THRESHOLD_KWH": 100.0,
        "LARGE_JUMP_MULTIPLIER": 3.0,
    })
    yield application
    application.extensions["db_engine"].dispose()


@pytest.fixture
def client(app):
    return app.test_client()


@pytest.fixture
def sample_records():
    def build(readings, meter_id=1, **overrides):
        return [
            {
                "reading_id": index,
                "meter_id": meter_id,
                "meter_code": f"M-{meter_id}",
                "consumer_id": meter_id,
                "consumer_type": "Residential",
                "region": "North",
                "reading_date": reading_date,
                "cumulative_kwh": value,
                **overrides,
            }
            for index, (reading_date, value) in enumerate(readings, start=1)
        ]
    return build