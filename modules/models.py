"""Portable relational schema shared by SQLite development and MySQL 8."""

from sqlalchemy import (
    CheckConstraint,
    Column,
    Date,
    ForeignKey,
    Integer,
    Index,
    MetaData,
    Numeric,
    String,
    Table,
    UniqueConstraint,
)

metadata = MetaData()

consumers = Table(
    "consumers",
    metadata,
    Column("consumer_id", Integer, primary_key=True, autoincrement=True),
    Column("consumer_type", String(40), nullable=False),
    Column("region", String(80), nullable=False, index=True),
)
Index("ix_consumers_type", consumers.c.consumer_type)

meters = Table(
    "meters",
    metadata,
    Column("meter_id", Integer, primary_key=True, autoincrement=True),
    Column(
        "consumer_id",
        Integer,
        ForeignKey("consumers.consumer_id", ondelete="RESTRICT", onupdate="CASCADE"),
        nullable=False,
        index=True,
    ),
    Column("meter_code", String(64), nullable=False, unique=True),
)

meter_readings = Table(
    "meter_readings",
    metadata,
    Column("reading_id", Integer, primary_key=True, autoincrement=True),
    Column(
        "meter_id",
        Integer,
        ForeignKey("meters.meter_id", ondelete="RESTRICT", onupdate="CASCADE"),
        nullable=False,
        index=True,
    ),
    Column("reading_date", Date, nullable=False, index=True),
    Column("cumulative_kwh", Numeric(12, 3), nullable=False),
    UniqueConstraint("meter_id", "reading_date", name="uq_reading_meter_date"),
    CheckConstraint("cumulative_kwh >= 0", name="ck_reading_nonnegative"),
)