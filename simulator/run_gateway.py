from __future__ import annotations

import json
import os
import random
import sqlite3
import time
import uuid
from datetime import UTC, datetime
from pathlib import Path

import requests

from config import DEVICES


PROJECT_ROOT = Path(__file__).resolve().parents[1]
BUFFER_DB = PROJECT_ROOT / "gateway_buffer.db"
CLOUD_API_BASE = os.getenv("CLOUD_API_BASE", "http://127.0.0.1:8000")
INTERVAL_SECONDS = int(os.getenv("SIMULATOR_INTERVAL_SECONDS", "3"))
SIMULATE_GATEWAY_OUTAGES = os.getenv("SIMULATE_GATEWAY_OUTAGES", "true").lower() == "true"
SIMULATED_OUTAGE_RATE = float(os.getenv("SIMULATED_OUTAGE_RATE", "0.18"))

STATE: dict[str, dict] = {
    device["device_id"]: {"battery_voltage": device["battery_voltage"], "step": 0}
    for device in DEVICES
}


def utc_now() -> str:
    return datetime.now(UTC).replace(microsecond=0).isoformat()


def get_buffer_connection() -> sqlite3.Connection:
    connection = sqlite3.connect(BUFFER_DB)
    connection.row_factory = sqlite3.Row
    connection.execute(
        """
        CREATE TABLE IF NOT EXISTS buffered_packets (
            packet_id TEXT PRIMARY KEY,
            payload TEXT NOT NULL,
            created_at TEXT NOT NULL
        )
        """
    )
    connection.commit()
    return connection


def store_packet(payload: dict) -> None:
    connection = get_buffer_connection()
    try:
        connection.execute(
            "INSERT OR REPLACE INTO buffered_packets (packet_id, payload, created_at) VALUES (?, ?, ?)",
            (payload["packet_id"], json.dumps(payload), utc_now()),
        )
        connection.commit()
    finally:
        connection.close()


def buffered_payloads() -> list[sqlite3.Row]:
    connection = get_buffer_connection()
    try:
        return connection.execute(
            "SELECT packet_id, payload FROM buffered_packets ORDER BY created_at ASC"
        ).fetchall()
    finally:
        connection.close()


def delete_buffered_packet(packet_id: str) -> None:
    connection = get_buffer_connection()
    try:
        connection.execute("DELETE FROM buffered_packets WHERE packet_id = ?", (packet_id,))
        connection.commit()
    finally:
        connection.close()


def maybe_fail_network() -> None:
    if SIMULATE_GATEWAY_OUTAGES and random.random() < SIMULATED_OUTAGE_RATE:
        raise requests.ConnectionError("Simulated gateway outage")


def post_payload(payload: dict) -> None:
    maybe_fail_network()
    response = requests.post(f"{CLOUD_API_BASE}/api/telemetry", json=payload, timeout=4)
    response.raise_for_status()


def flush_buffer() -> None:
    rows = buffered_payloads()
    if not rows:
        return

    for row in rows:
        payload = json.loads(row["payload"])
        try:
            post_payload(payload)
            delete_buffered_packet(row["packet_id"])
            print(f"[flush] sent buffered packet {row['packet_id']}")
        except Exception as error:
            print(f"[flush] still blocked for {row['packet_id']}: {error}")
            break


def drift_temperature(device: dict, state: dict) -> float:
    base = device["baseline_temperature"]
    step = state["step"]

    if device["device_id"] == "LTAT-PUNE-TRUCK-01" and step % 12 in (4, 5, 6):
        return round(random.uniform(8.4, 9.6), 2)

    if device["device_id"] == "LTAT-NASHIK-01" and step % 14 in (6, 7):
        return round(random.uniform(1.2, 1.9), 2)

    return round(base + random.uniform(-0.55, 0.55), 2)


def next_payload(device: dict) -> dict:
    state = STATE[device["device_id"]]
    state["step"] += 1
    state["battery_voltage"] = max(1.95, round(state["battery_voltage"] - random.uniform(0.001, 0.006), 3))

    latitude = device["latitude"]
    longitude = device["longitude"]
    if device["transport_mode"] == "transit":
        latitude = round(latitude + random.uniform(-0.008, 0.008), 6)
        longitude = round(longitude + random.uniform(-0.008, 0.008), 6)

    return {
        "packet_id": f"PKT-{uuid.uuid4().hex[:10].upper()}",
        "device_id": device["device_id"],
        "gateway_id": device["gateway_id"],
        "facility_id": device["facility_id"],
        "batch_id": device["batch_id"],
        "recorded_at": utc_now(),
        "temperature_c": drift_temperature(device, state),
        "humidity_pct": round(device["humidity_pct"] + random.uniform(-4.0, 4.0), 2),
        "battery_voltage": state["battery_voltage"],
        "latitude": latitude,
        "longitude": longitude,
        "transport_mode": device["transport_mode"],
    }


def run() -> None:
    print("Starting Cold Chain gateway simulator")
    print(f"Cloud API: {CLOUD_API_BASE}")
    print(f"Buffer DB:  {BUFFER_DB}")
    print(f"Interval:   {INTERVAL_SECONDS}s")
    print(f"Outages:    {SIMULATE_GATEWAY_OUTAGES} ({SIMULATED_OUTAGE_RATE:.0%})")

    while True:
        flush_buffer()
        for device in DEVICES:
            payload = next_payload(device)
            try:
                post_payload(payload)
                print(
                    f"[send] {payload['packet_id']} {payload['device_id']} "
                    f"{payload['temperature_c']}C battery={payload['battery_voltage']}V"
                )
            except Exception as error:
                store_packet(payload)
                print(
                    f"[buffered] {payload['packet_id']} {payload['device_id']} "
                    f"stored locally because {error}"
                )
        time.sleep(INTERVAL_SECONDS)


if __name__ == "__main__":
    run()
