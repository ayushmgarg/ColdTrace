from __future__ import annotations

import os
import sqlite3
from pathlib import Path


DEFAULT_DB_PATH = Path(__file__).resolve().parents[2] / "coldchain.db"


def get_db_path() -> Path:
    configured = os.getenv("COLDCHAIN_DB_PATH")
    return Path(configured).resolve() if configured else DEFAULT_DB_PATH


def get_connection() -> sqlite3.Connection:
    connection = sqlite3.connect(get_db_path(), check_same_thread=False)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA foreign_keys = ON;")
    return connection


SCHEMA = """
CREATE TABLE IF NOT EXISTS facilities (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    facility_type TEXT NOT NULL,
    region TEXT NOT NULL,
    status TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS devices (
    id TEXT PRIMARY KEY,
    facility_id TEXT NOT NULL,
    gateway_id TEXT NOT NULL,
    device_type TEXT NOT NULL,
    status TEXT NOT NULL,
    min_temp_c REAL NOT NULL,
    max_temp_c REAL NOT NULL,
    last_seen_at TEXT,
    FOREIGN KEY (facility_id) REFERENCES facilities(id)
);

CREATE TABLE IF NOT EXISTS batches (
    id TEXT PRIMARY KEY,
    vaccine_name TEXT NOT NULL,
    manufacturer TEXT NOT NULL,
    origin_facility_id TEXT NOT NULL,
    destination_facility_id TEXT NOT NULL,
    status TEXT NOT NULL,
    doses_total INTEGER NOT NULL,
    FOREIGN KEY (origin_facility_id) REFERENCES facilities(id),
    FOREIGN KEY (destination_facility_id) REFERENCES facilities(id)
);

CREATE TABLE IF NOT EXISTS telemetry (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    packet_id TEXT NOT NULL UNIQUE,
    device_id TEXT NOT NULL,
    gateway_id TEXT NOT NULL,
    facility_id TEXT NOT NULL,
    batch_id TEXT NOT NULL,
    recorded_at TEXT NOT NULL,
    temperature_c REAL NOT NULL,
    humidity_pct REAL NOT NULL,
    battery_voltage REAL NOT NULL,
    latitude REAL,
    longitude REAL,
    transport_mode TEXT NOT NULL,
    created_at TEXT NOT NULL,
    FOREIGN KEY (device_id) REFERENCES devices(id),
    FOREIGN KEY (facility_id) REFERENCES facilities(id),
    FOREIGN KEY (batch_id) REFERENCES batches(id)
);

CREATE TABLE IF NOT EXISTS incidents (
    id TEXT PRIMARY KEY,
    device_id TEXT NOT NULL,
    batch_id TEXT NOT NULL,
    facility_id TEXT NOT NULL,
    incident_type TEXT NOT NULL,
    severity TEXT NOT NULL,
    status TEXT NOT NULL,
    reason TEXT NOT NULL,
    opened_at TEXT NOT NULL,
    resolved_at TEXT,
    latest_temperature_c REAL,
    min_temperature_c REAL,
    max_temperature_c REAL,
    battery_voltage REAL,
    FOREIGN KEY (device_id) REFERENCES devices(id),
    FOREIGN KEY (facility_id) REFERENCES facilities(id),
    FOREIGN KEY (batch_id) REFERENCES batches(id)
);

CREATE TABLE IF NOT EXISTS notifications (
    id TEXT PRIMARY KEY,
    incident_id TEXT NOT NULL,
    channel TEXT NOT NULL,
    recipient TEXT NOT NULL,
    payload TEXT NOT NULL,
    status TEXT NOT NULL,
    sent_at TEXT NOT NULL,
    provider TEXT DEFAULT 'simulation',
    provider_message_id TEXT DEFAULT '',
    error_message TEXT DEFAULT '',
    FOREIGN KEY (incident_id) REFERENCES incidents(id)
);

CREATE TABLE IF NOT EXISTS audit_log (
    id TEXT PRIMARY KEY,
    entity_type TEXT NOT NULL,
    entity_id TEXT NOT NULL,
    action TEXT NOT NULL,
    payload TEXT NOT NULL,
    previous_hash TEXT,
    entry_hash TEXT NOT NULL,
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS users (
    id TEXT PRIMARY KEY,
    full_name TEXT NOT NULL,
    email TEXT NOT NULL UNIQUE,
    role TEXT NOT NULL,
    assigned_facility_id TEXT,
    phone_number TEXT,
    password_salt TEXT NOT NULL,
    password_hash TEXT NOT NULL,
    is_active INTEGER NOT NULL DEFAULT 1,
    created_at TEXT NOT NULL,
    FOREIGN KEY (assigned_facility_id) REFERENCES facilities(id)
);
"""


def init_db() -> None:
    connection = get_connection()
    try:
        connection.executescript(SCHEMA)
        migrations = [
            "ALTER TABLE notifications ADD COLUMN provider TEXT DEFAULT 'simulation'",
            "ALTER TABLE notifications ADD COLUMN provider_message_id TEXT DEFAULT ''",
            "ALTER TABLE notifications ADD COLUMN error_message TEXT DEFAULT ''",
        ]
        for statement in migrations:
            try:
                connection.execute(statement)
            except sqlite3.OperationalError:
                pass
        connection.commit()
    finally:
        connection.close()
