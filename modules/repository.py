"""Small SQLAlchemy Core repository for consumer, meter, and reading records."""

from __future__ import annotations

from datetime import date, datetime
import math
from typing import Any

from sqlalchemy import delete, func, insert, select, update
from sqlalchemy.engine import Engine

from modules.models import consumers, meter_readings, meters


def list_consumers(engine: Engine) -> list[dict[str, Any]]:
    with engine.connect() as connection:
        return [dict(row) for row in connection.execute(select(consumers).order_by(consumers.c.consumer_id.desc())).mappings()]


def list_meters(engine: Engine) -> list[dict[str, Any]]:
    query = select(meters, consumers.c.consumer_type, consumers.c.region).join(consumers).order_by(meters.c.meter_id.desc())
    with engine.connect() as connection:
        return [dict(row) for row in connection.execute(query).mappings()]


def list_readings(engine: Engine, filters: dict[str, Any] | None = None) -> list[dict[str, Any]]:
    query = select(
        meter_readings, meters.c.meter_code, meters.c.consumer_id,
        consumers.c.consumer_type, consumers.c.region,
    ).select_from(
        meter_readings.join(meters, meter_readings.c.meter_id == meters.c.meter_id).join(
            consumers, meters.c.consumer_id == consumers.c.consumer_id
        )
    ).order_by(meter_readings.c.reading_date.desc(), meter_readings.c.reading_id.desc())
    filters = filters or {}
    if filters.get("meter_id"):
        query = query.where(meter_readings.c.meter_id == filters["meter_id"])
    if filters.get("region"):
        query = query.where(consumers.c.region == filters["region"])
    if filters.get("start_date"):
        query = query.where(meter_readings.c.reading_date >= filters["start_date"])
    if filters.get("end_date"):
        query = query.where(meter_readings.c.reading_date <= filters["end_date"])
    with engine.connect() as connection:
        return [dict(row) for row in connection.execute(query).mappings()]


def save_consumer(engine: Engine, values: dict[str, Any], consumer_id: int | None = None) -> None:
    with engine.begin() as connection:
        if consumer_id is None:
            connection.execute(insert(consumers).values(**values))
        else:
            connection.execute(update(consumers).where(consumers.c.consumer_id == consumer_id).values(**values))


def save_meter(engine: Engine, values: dict[str, Any], meter_id: int | None = None) -> None:
    with engine.begin() as connection:
        if meter_id is None:
            connection.execute(insert(meters).values(**values))
        else:
            current_consumer = connection.scalar(
                select(meters.c.consumer_id).where(meters.c.meter_id == meter_id)
            )
            if current_consumer is not None and current_consumer != values["consumer_id"]:
                reading_count = connection.scalar(
                    select(func.count()).select_from(meter_readings).where(meter_readings.c.meter_id == meter_id)
                )
                if reading_count:
                    raise ValueError("A meter with historical readings cannot be reassigned to another consumer.")
            connection.execute(update(meters).where(meters.c.meter_id == meter_id).values(**values))


def save_reading(engine: Engine, values: dict[str, Any], reading_id: int | None = None) -> dict[str, float | bool | None]:
    reading_value = float(values["cumulative_kwh"])
    if not math.isfinite(reading_value):
        raise ValueError("Cumulative reading must be a finite number.")
    if reading_value < 0:
        raise ValueError("Cumulative reading cannot be negative.")
    reading_date = values.get("reading_date")
    if not isinstance(reading_date, date) or isinstance(reading_date, datetime):
        raise ValueError("Enter a valid reading date.")

    with engine.begin() as connection:
        if connection.scalar(select(meters.c.meter_id).where(meters.c.meter_id == values["meter_id"])) is None:
            raise ValueError("Select an existing meter.")

        if reading_id is not None:
            current = connection.execute(
                select(meter_readings.c.reading_id).where(meter_readings.c.reading_id == reading_id)
            ).first()
            if current is None:
                raise ValueError("Reading not found.")

        duplicate_query = select(meter_readings.c.reading_id).where(
            meter_readings.c.meter_id == values["meter_id"],
            meter_readings.c.reading_date == reading_date,
        )
        if reading_id is not None:
            duplicate_query = duplicate_query.where(meter_readings.c.reading_id != reading_id)
        if connection.scalar(duplicate_query.limit(1)) is not None:
            raise ValueError("A reading already exists for this meter on this date.")

        previous_query = (
            select(meter_readings.c.cumulative_kwh)
            .where(
                meter_readings.c.meter_id == values["meter_id"],
                meter_readings.c.reading_date < reading_date,
            )
            .order_by(meter_readings.c.reading_date.desc(), meter_readings.c.reading_id.desc())
            .limit(1)
        )
        previous_value = connection.scalar(previous_query)

        if reading_id is None:
            latest_date = connection.scalar(
                select(meter_readings.c.reading_date)
                .where(meter_readings.c.meter_id == values["meter_id"])
                .order_by(meter_readings.c.reading_date.desc())
                .limit(1)
            )
            if latest_date is not None and reading_date <= latest_date:
                raise ValueError("A new reading must be later than the latest reading for this meter.")

        if reading_id is None:
            connection.execute(insert(meter_readings).values(**values))
        else:
            connection.execute(update(meter_readings).where(meter_readings.c.reading_id == reading_id).values(**values))

    possible_reset = previous_value is not None and reading_value < float(previous_value)
    consumption = None if previous_value is None or possible_reset else reading_value - float(previous_value)
    return {"consumption_kwh": consumption, "possible_reset": possible_reset}


def delete_record(engine: Engine, table_name: str, record_id: int) -> None:
    tables = {"consumer": consumers, "meter": meters, "reading": meter_readings}
    table = tables[table_name]
    id_column = table.c[f"{table_name}_id"]
    with engine.begin() as connection:
        connection.execute(delete(table).where(id_column == record_id))


def list_table(engine: Engine, table: Any) -> list[dict[str, Any]]:
    with engine.connect() as connection:
        return [dict(row) for row in connection.execute(select(table)).mappings()]


def count_records(engine: Engine, table: Any) -> int:
    from sqlalchemy import func

    with engine.connect() as connection:
        return int(connection.scalar(select(func.count()).select_from(table)) or 0)


def parse_date(value: str) -> date:
    return date.fromisoformat(value)