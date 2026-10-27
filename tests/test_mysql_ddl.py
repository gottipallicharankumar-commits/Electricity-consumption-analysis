from sqlalchemy.dialects import mysql
from sqlalchemy.schema import CreateTable

from modules.models import consumers, meter_readings, meters


def test_schema_compiles_for_mysql_dialect_without_claiming_server_compatibility():
    dialect = mysql.dialect()
    consumer_sql = str(CreateTable(consumers).compile(dialect=dialect))
    meter_sql = str(CreateTable(meters).compile(dialect=dialect))
    reading_sql = str(CreateTable(meter_readings).compile(dialect=dialect))
    assert "AUTO_INCREMENT" in consumer_sql
    assert "FOREIGN KEY" in meter_sql and "UNIQUE" in meter_sql
    assert "NUMERIC(12, 3)" in reading_sql
    assert "UNIQUE" in reading_sql and "CHECK" in reading_sql