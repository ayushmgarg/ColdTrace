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
    connection.execute("PRAGMA journal_mode = WAL;")
    return connection


SCHEMA = """
CREATE TABLE IF NOT EXISTS facilities (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    facility_type TEXT NOT NULL,
    region TEXT NOT NULL,
    status TEXT NOT NULL,
    latitude REAL,
    longitude REAL,
    address TEXT,
    contact_name TEXT,
    contact_phone TEXT
);

CREATE TABLE IF NOT EXISTS gateways (
    id TEXT PRIMARY KEY,
    facility_id TEXT NOT NULL,
    model TEXT NOT NULL DEFAULT 'IGD-v2',
    status TEXT NOT NULL DEFAULT 'online',
    firmware_version TEXT DEFAULT '2.1.4',
    last_seen_at TEXT,
    buffered_packets INTEGER DEFAULT 0,
    FOREIGN KEY (facility_id) REFERENCES facilities(id)
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
    firmware_version TEXT DEFAULT '1.4.2',
    sensor_count INTEGER DEFAULT 5,
    FOREIGN KEY (facility_id) REFERENCES facilities(id)
);

CREATE TABLE IF NOT EXISTS vaccines (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    manufacturer TEXT NOT NULL,
    storage_temp_min REAL NOT NULL DEFAULT 2.0,
    storage_temp_max REAL NOT NULL DEFAULT 8.0,
    shelf_life_days INTEGER NOT NULL DEFAULT 730,
    requires_freezer INTEGER DEFAULT 0
);

CREATE TABLE IF NOT EXISTS batches (
    id TEXT PRIMARY KEY,
    vaccine_id TEXT,
    vaccine_name TEXT NOT NULL,
    manufacturer TEXT NOT NULL,
    lot_number TEXT,
    origin_facility_id TEXT NOT NULL,
    destination_facility_id TEXT NOT NULL,
    status TEXT NOT NULL,
    doses_total INTEGER NOT NULL,
    doses_remaining INTEGER,
    manufactured_at TEXT,
    expires_at TEXT,
    FOREIGN KEY (vaccine_id) REFERENCES vaccines(id),
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
    rolling_avg_c REAL,
    trend_slope REAL,
    created_at TEXT NOT NULL,
    FOREIGN KEY (device_id) REFERENCES devices(id),
    FOREIGN KEY (facility_id) REFERENCES facilities(id),
    FOREIGN KEY (batch_id) REFERENCES batches(id)
);

CREATE INDEX IF NOT EXISTS idx_telemetry_device_time ON telemetry(device_id, recorded_at DESC);
CREATE INDEX IF NOT EXISTS idx_telemetry_facility ON telemetry(facility_id);

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

CREATE TABLE IF NOT EXISTS dc_events (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    event_type TEXT NOT NULL,
    node_id TEXT NOT NULL,
    description TEXT NOT NULL,
    metadata TEXT,
    occurred_at TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_dc_events_time ON dc_events(occurred_at DESC);
"""


def init_db() -> None:
    connection = get_connection()
    try:
        connection.executescript(SCHEMA)
        _run_migrations(connection)
        connection.commit()
    finally:
        connection.close()


def _run_migrations(connection: sqlite3.Connection) -> None:
    migrations = [
        "ALTER TABLE notifications ADD COLUMN provider TEXT DEFAULT 'simulation'",
        "ALTER TABLE notifications ADD COLUMN provider_message_id TEXT DEFAULT ''",
        "ALTER TABLE notifications ADD COLUMN error_message TEXT DEFAULT ''",
        "ALTER TABLE telemetry ADD COLUMN rolling_avg_c REAL",
        "ALTER TABLE telemetry ADD COLUMN trend_slope REAL",
        "ALTER TABLE batches ADD COLUMN vaccine_id TEXT",
        "ALTER TABLE batches ADD COLUMN lot_number TEXT",
        "ALTER TABLE batches ADD COLUMN doses_remaining INTEGER",
        "ALTER TABLE batches ADD COLUMN manufactured_at TEXT",
        "ALTER TABLE batches ADD COLUMN expires_at TEXT",
        "ALTER TABLE devices ADD COLUMN firmware_version TEXT DEFAULT '1.4.2'",
        "ALTER TABLE devices ADD COLUMN sensor_count INTEGER DEFAULT 5",
    ]
    for stmt in migrations:
        try:
            connection.execute(stmt)
        except sqlite3.OperationalError:
            pass
