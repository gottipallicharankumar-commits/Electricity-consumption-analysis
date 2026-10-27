from datetime import date

import pytest
from sqlalchemy import insert, select

from database import create_database_engine
from modules.models import meter_readings, meters
from modules.repository import count_records
from scripts.seed_database import seed


def test_seed_refuses_additional_user_data_without_deleting_it(tmp_path):
    database_url = f"sqlite:///{tmp_path / 'seed.db'}"
    seed(database_url=database_url)
    engine = create_database_engine(database_url)
    with engine.begin() as connection:
        meter_id = connection.scalar(select(meters.c.meter_id).where(meters.c.meter_code == "DEMO-HOME-01"))
        connection.execute(insert(meter_readings).values(
            meter_id=meter_id, reading_date=date(2026, 1, 1), cumulative_kwh=9999,
        ))
    before = count_records(engine, meter_readings)
    with pytest.raises(RuntimeError, match="exact shipped demo dataset"):
        seed(reset_demo=True, database_url=database_url)
    assert count_records(engine, meter_readings) == before
    engine.dispose()


def test_reset_accepts_only_exact_demo_dataset(tmp_path):
    database_url = f"sqlite:///{tmp_path / 'reset.db'}"
    seed(database_url=database_url)
    seed(reset_demo=True, database_url=database_url)
    engine = create_database_engine(database_url)
    assert count_records(engine, meter_readings) == 51
    engine.dispose()