"""
run_gateway.py — Cold Chain Gateway + Sensor Simulator
=======================================================
Simulates 7 LTAT devices across 6 facilities.

DC concepts demonstrated live:
  - Store-and-forward: packets buffered in SQLite when cloud is unreachable
  - Fault tolerance: simulated gateway outages (configurable SIMULATED_OUTAGE_RATE)
  - Clock sync: UTC timestamps attached at acquisition time
  - Naming: structured device_id, gateway_id, facility_id, batch_id
  - Excursion scenarios: LTAT-PUNE-TRUCK-01 and LTAT-NASHIK-01 periodically spike
"""
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
BUFFER_DB    = PROJECT_ROOT / "gateway_buffer.db"
CLOUD_API    = os.getenv("CLOUD_API_BASE",           "http://127.0.0.1:8000")
INTERVAL     = int(os.getenv("SIMULATOR_INTERVAL_SECONDS", "3"))
OUTAGES      = os.getenv("SIMULATE_GATEWAY_OUTAGES",  "true").lower() == "true"
OUTAGE_RATE  = float(os.getenv("SIMULATED_OUTAGE_RATE", "0.18"))

# Per-device state (battery drain, step counter)
STATE: dict[str, dict] = {
    d["device_id"]: {"battery_voltage": d["battery_voltage"], "step": 0}
    for d in DEVICES
}

# ── SQLite buffer ─────────────────────────────────────────────
def get_buf() -> sqlite3.Connection:
    con = sqlite3.connect(BUFFER_DB)
    con.row_factory = sqlite3.Row
    con.execute("""
        CREATE TABLE IF NOT EXISTS buffered_packets (
            packet_id TEXT PRIMARY KEY,
            payload TEXT NOT NULL,
            created_at TEXT NOT NULL
        )
    """)
    con.commit()
    return con

def buffer_packet(payload: dict) -> None:
    con = get_buf()
    try:
        con.execute(
            "INSERT OR REPLACE INTO buffered_packets VALUES (?,?,?)",
            (payload["packet_id"], json.dumps(payload), utc_now()),
        )
        con.commit()
    finally:
        con.close()

def pending_packets() -> list:
    con = get_buf()
    try:
        return con.execute("SELECT * FROM buffered_packets ORDER BY created_at ASC").fetchall()
    finally:
        con.close()

def delete_packet(pid: str) -> None:
    con = get_buf()
    try:
        con.execute("DELETE FROM buffered_packets WHERE packet_id=?", (pid,))
        con.commit()
    finally:
        con.close()

# ── Network helpers ───────────────────────────────────────────
def utc_now() -> str:
    return datetime.now(UTC).replace(microsecond=0).isoformat()

def maybe_fail() -> None:
    if OUTAGES and random.random() < OUTAGE_RATE:
        raise requests.ConnectionError("Simulated gateway outage")

def post_payload(payload: dict) -> None:
    maybe_fail()
    r = requests.post(f"{CLOUD_API}/api/telemetry", json=payload, timeout=4)
    r.raise_for_status()

def flush_buffer() -> None:
    rows = pending_packets()
    if not rows:
        return
    flushed = 0
    for row in rows:
        p = json.loads(row["payload"])
        try:
            post_payload(p)
            delete_packet(row["packet_id"])
            flushed += 1
            print(f"  [flush] {row['packet_id']} replayed OK")
        except Exception as err:
            print(f"  [flush] still blocked: {err}")
            break
    if flushed:
        print(f"  [flush] {flushed} buffered packet(s) delivered")

# ── Temperature simulation ────────────────────────────────────
def drift_temp(device: dict, state: dict) -> float:
    base = device["baseline_temperature"]
    step = state["step"]

    # PUNE TRUCK: periodic excursion (door left open at delivery point)
    if device["device_id"] == "LTAT-PUNE-TRUCK-01" and step % 12 in (4, 5, 6):
        return round(random.uniform(8.4, 9.8), 2)

    # NASHIK clinic: occasional under-cooling (power outage)
    if device["device_id"] == "LTAT-NASHIK-01" and step % 16 in (7, 8):
        return round(random.uniform(1.0, 1.8), 2)

    # KOL transit: mild temperature drift (older gateway)
    if device["device_id"] == "LTAT-KOL-01" and step % 20 in (10, 11):
        return round(random.uniform(8.1, 8.9), 2)

    return round(base + random.uniform(-0.55, 0.55), 2)

# ── Build one packet ──────────────────────────────────────────
def next_payload(device: dict) -> dict:
    state = STATE[device["device_id"]]
    state["step"] += 1
    # Battery drains slowly
    state["battery_voltage"] = max(1.90, round(
        state["battery_voltage"] - random.uniform(0.001, 0.007), 3
    ))

    lat = device["latitude"]
    lon = device["longitude"]
    if device["transport_mode"] == "transit":
        # Vehicle moves along route
        lat = round(lat + random.uniform(-0.009, 0.009), 6)
        lon = round(lon + random.uniform(-0.009, 0.009), 6)

    return {
        "packet_id":       f"PKT-{uuid.uuid4().hex[:10].upper()}",
        "device_id":       device["device_id"],
        "gateway_id":      device["gateway_id"],
        "facility_id":     device["facility_id"],
        "batch_id":        device["batch_id"],
        "recorded_at":     utc_now(),          # ← clock-sync: UTC timestamp at acquisition
        "temperature_c":   drift_temp(device, state),
        "humidity_pct":    round(device["humidity_pct"] + random.uniform(-4.0, 4.0), 2),
        "battery_voltage": state["battery_voltage"],
        "latitude":        lat,
        "longitude":       lon,
        "transport_mode":  device["transport_mode"],
    }

# ── Main loop ─────────────────────────────────────────────────
def run() -> None:
    print("=" * 55)
    print(f"  ColdTrace DC — Gateway Simulator")
    print(f"  Cloud:    {CLOUD_API}")
    print(f"  Buffer:   {BUFFER_DB}")
    print(f"  Devices:  {len(DEVICES)}")
    print(f"  Interval: {INTERVAL}s")
    print(f"  Outages:  {OUTAGES} (rate={OUTAGE_RATE:.0%})")
    print("=" * 55)

    cycle = 0
    while True:
        cycle += 1
        flush_buffer()

        buf_before = len(pending_packets())
        sent = 0
        buffered = 0

        for device in DEVICES:
            payload = next_payload(device)
            try:
                post_payload(payload)
                sent += 1
                print(
                    f"  [OK]  {payload['packet_id']}  {payload['device_id']:<22}"
                    f"  T={payload['temperature_c']:5.2f}°C  "
                    f"bat={payload['battery_voltage']:.3f}V"
                )
            except Exception as err:
                buffer_packet(payload)
                buffered += 1
                print(
                    f"  [BUF] {payload['packet_id']}  {payload['device_id']:<22}"
                    f"  buffered ({err})"
                )

        buf_after = len(pending_packets())
        print(
            f"\n  Cycle {cycle}: sent={sent}  buffered={buffered}  "
            f"buffer_depth={buf_after}  sleep={INTERVAL}s\n"
        )
        time.sleep(INTERVAL)

if __name__ == "__main__":
    run()
