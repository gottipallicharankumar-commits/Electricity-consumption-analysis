-- Electricity Consumption Analysis System (Project 18)
-- MySQL 8 / InnoDB. Cumulative meter values are recorded in kWh.
CREATE TABLE IF NOT EXISTS consumers (
    consumer_id INT NOT NULL AUTO_INCREMENT,
    consumer_type VARCHAR(40) NOT NULL,
    region VARCHAR(80) NOT NULL,
    PRIMARY KEY (consumer_id),
    KEY ix_consumers_region (region),
    KEY ix_consumers_type (consumer_type)
) ENGINE=InnoDB COMMENT='Synthetic or authorized electricity consumers';

CREATE TABLE IF NOT EXISTS meters (
    meter_id INT NOT NULL AUTO_INCREMENT,
    consumer_id INT NOT NULL,
    meter_code VARCHAR(64) NOT NULL,
    PRIMARY KEY (meter_id),
    UNIQUE KEY uq_meters_meter_code (meter_code),
    KEY ix_meters_consumer_id (consumer_id),
    CONSTRAINT fk_meters_consumer FOREIGN KEY (consumer_id)
        REFERENCES consumers (consumer_id) ON DELETE RESTRICT ON UPDATE CASCADE
) ENGINE=InnoDB COMMENT='Meters assigned to an existing consumer';

CREATE TABLE IF NOT EXISTS meter_readings (
    reading_id INT NOT NULL AUTO_INCREMENT,
    meter_id INT NOT NULL,
    reading_date DATE NOT NULL,
    cumulative_kwh DECIMAL(12,3) NOT NULL,
    PRIMARY KEY (reading_id),
    UNIQUE KEY uq_reading_meter_date (meter_id, reading_date),
    KEY ix_readings_date (reading_date),
    CONSTRAINT ck_reading_nonnegative CHECK (cumulative_kwh >= 0),
    CONSTRAINT fk_readings_meter FOREIGN KEY (meter_id)
        REFERENCES meters (meter_id) ON DELETE RESTRICT ON UPDATE CASCADE
) ENGINE=InnoDB COMMENT='Dated cumulative meter readings, in kWh';