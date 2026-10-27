"""Load synthetic demo data without replacing existing non-demo records."""

from __future__ import annotations

import argparse
import csv
import sys
from datetime import date
from pathlib import Path

from sqlalchemy import delete, select

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from config import Config
from database import create_database_engine, initialize_schema
from modules.models import consumers, meter_readings, meters

def seed(reset_demo: bool = False, database_url: str | None = None) -> None:
    engine = create_database_engine(database_url or Config.database_url())
    initialize_schema(engine)
    records = list(csv.DictReader((ROOT / "data" / "sample_readings.csv").open(encoding="utf-8", newline="")))
    expected_readings = {
        (row["consumer_type"], row["region"], row["meter_code"], date.fromisoformat(row["reading_date"]), float(row["cumulative_kwh"]))
        for row in records
    }
    expected_consumers = {(row["consumer_type"], row["region"]) for row in records}
    expected_meters = {(row["meter_code"], row["consumer_type"], row["region"]) for row in records}
    with engine.begin() as connection:
        existing_codes = set(connection.execute(select(meters.c.meter_code)).scalars())
        existing_consumers = {
            (row.consumer_type, row.region)
            for row in connection.execute(select(consumers.c.consumer_type, consumers.c.region))
        }
        if reset_demo:
            if Config.ENVIRONMENT != "development":
                raise RuntimeError("Reset is permitted only with APP_ENV=development.")
            existing_readings = {
                (row.consumer_type, row.region, row.meter_code, row.reading_date, float(row.cumulative_kwh))
                for row in connection.execute(
                    select(consumers.c.consumer_type, consumers.c.region, meters.c.meter_code,
                           meter_readings.c.reading_date, meter_readings.c.cumulative_kwh)
                    .select_from(meter_readings.join(meters).join(consumers))
                )
            }
            existing_meters = {
                (row.meter_code, row.consumer_type, row.region)
                for row in connection.execute(
                    select(meters.c.meter_code, consumers.c.consumer_type, consumers.c.region).join(consumers)
                )
            }
            if existing_readings != expected_readings or existing_consumers != expected_consumers or existing_meters != expected_meters:
                raise RuntimeError("Reset refused: database contents differ from the exact shipped demo dataset; no records were deleted.")
            connection.execute(delete(meter_readings))
            connection.execute(delete(meters))
            connection.execute(delete(consumers))
        elif existing_codes or existing_consumers:
            raise RuntimeError("Database already contains records. Seeding stopped without changing data.")
        consumer_ids: dict[tuple[str, str], int] = {}
        meter_ids: dict[str, int] = {}
        for row in records:
            key = (row["consumer_type"], row["region"])
            if key not in consumer_ids:
                consumer_ids[key] = connection.execute(
                    consumers.insert().values(consumer_type=key[0], region=key[1])
                ).inserted_primary_key[0]
            if row["meter_code"] not in meter_ids:
                meter_ids[row["meter_code"]] = connection.execute(
                    meters.insert().values(consumer_id=consumer_ids[key], meter_code=row["meter_code"])
                ).inserted_primary_key[0]
            connection.execute(meter_readings.insert().values(
                meter_id=meter_ids[row["meter_code"]],
                reading_date=date.fromisoformat(row["reading_date"]),
                cumulative_kwh=float(row["cumulative_kwh"]),
            ))
    print(f"Loaded {len(records)} synthetic readings into {engine.url.get_backend_name()}.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--reset-demo", action="store_true", help="Explicitly replace only an entirely synthetic demo dataset in development")
    arguments = parser.parse_args()
    seed(reset_demo=arguments.reset_demo)