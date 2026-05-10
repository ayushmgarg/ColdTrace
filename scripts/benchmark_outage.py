#!/usr/bin/env python3
"""
benchmark_outage.py
===================
Measures data completeness under simulated gateway outages.

For each outage rate in [0 %, 10 %, 20 %, 30 %, 50 %]:
  1. Generate N_PACKETS telemetry packets.
  2. With probability = outage_rate → buffer locally (store-and-forward).
     Otherwise → POST directly to the cloud API.
  3. Flush the buffer (simulate network recovery — 100 % delivery).
  4. Count packets received in coldchain.db since run start.
  5. Report: completeness = received / generated × 100 %.

Usage:
    cd ColdChainDC
    python scripts/benchmark_outage.py [N_PACKETS_PER_RATE]

    python scripts/benchmark_outage.py          # default: 100 packets per rate
    python scripts/benchmark_outage.py 200

Prerequisites:
  - Backend running at http://127.0.0.1:8000
      cd backend && uvicorn app.main:app --reload
  - Stop the simulator (run_gateway.py) before running to avoid interference.

Notes:
  - Uses a separate buffer DB (benchmark_outage_buffer.db) so it does not
    interfere with the simulator's gateway_buffer.db.
  - Completeness is measured via the server-side `created_at` timestamp in
    the telemetry table, so it is immune to clock skew between client and server.
"""
from __future__ import annotations

import json
import random
import sqlite3
import sys
import uuid
from datetime import UTC, datetime
from pathlib import Path

# Force UTF-8 output so non-ASCII chars survive file redirection on Windows
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

import requests

# ── Path setup ────────────────────────────────────────────────
PROJECT_ROOT = Path(__file__).resolve().parents[1]
CLOUD_DB     = PROJECT_ROOT / "coldchain.db"
BUFFER_DB    = PROJECT_ROOT / "benchmark_outage_buffer.db"   # isolated from simulator buffer
CLOUD_API    = "http://127.0.0.1:8000"

N_PACKETS_PER_RATE = int(sys.argv[1]) if len(sys.argv) > 1 else 100
OUTAGE_RATES       = [0.0, 0.10, 0.20, 0.30, 0.50]

sys.path.insert(0, str(PROJECT_ROOT / "simulator"))
from config import DEVICES  # noqa: E402


# ── Helpers ───────────────────────────────────────────────────
def utc_now() -> str:
    return datetime.now(UTC).replace(microsecond=0).isoformat()


def build_payload(device: dict, state: dict) -> dict:
    """Build a normal-range telemetry packet (no excursion injection — isolation)."""
    state["step"] += 1
    state["battery_voltage"] = max(1.90, round(
        state["battery_voltage"] - random.uniform(0.001, 0.007), 3
    ))
    return {
        "packet_id":       f"PKT-OT-{uuid.uuid4().hex[:10].upper()}",
        "device_id":       device["device_id"],
        "gateway_id":      device["gateway_id"],
        "facility_id":     device["facility_id"],
        "batch_id":        device["batch_id"],
        "recorded_at":     utc_now(),
        # Keep temperature in normal range so incidents do not muddy the count
        "temperature_c":   round(device["baseline_temperature"] + random.uniform(-0.5, 0.5), 2),
        "humidity_pct":    round(device["humidity_pct"] + random.uniform(-2.0, 2.0), 2),
        "battery_voltage": state["battery_voltage"],
        "latitude":        device["latitude"],
        "longitude":       device["longitude"],
        "transport_mode":  device["transport_mode"],
    }


# ── Buffer helpers (isolated DB, no maybe_fail()) ────────────
def _buf_con() -> sqlite3.Connection:
    con = sqlite3.connect(BUFFER_DB)
    con.row_factory = sqlite3.Row
    con.execute("""
        CREATE TABLE IF NOT EXISTS buffered_packets (
            packet_id  TEXT PRIMARY KEY,
            payload    TEXT NOT NULL,
            created_at TEXT NOT NULL
        )
    """)
    con.commit()
    return con


def clear_buffer() -> None:
    con = _buf_con()
    try:
        con.execute("DELETE FROM buffered_packets")
        con.commit()
    finally:
        con.close()


def buffer_packet(payload: dict) -> None:
    con = _buf_con()
    try:
        con.execute(
            "INSERT OR REPLACE INTO buffered_packets VALUES (?,?,?)",
            (payload["packet_id"], json.dumps(payload), utc_now()),
        )
        con.commit()
    finally:
        con.close()


def flush_all_buffered() -> tuple[int, int]:
    """
    Deliver all buffered packets to the cloud (recovery phase — no simulated failure).
    Returns (flushed_count, failed_count).
    """
    con = _buf_con()
    try:
        rows = con.execute(
            "SELECT * FROM buffered_packets ORDER BY created_at ASC"
        ).fetchall()
    finally:
        con.close()

    flushed = failed = 0
    for row in rows:
        p = json.loads(row["payload"])
        try:
            r = requests.post(f"{CLOUD_API}/api/telemetry", json=p, timeout=8)
            if r.status_code in (200, 201):
                c2 = _buf_con()
                try:
                    c2.execute(
                        "DELETE FROM buffered_packets WHERE packet_id=?",
                        (p["packet_id"],),
                    )
                    c2.commit()
                finally:
                    c2.close()
                flushed += 1
            else:
                failed += 1
        except Exception:
            failed += 1

    return flushed, failed


def post_direct(payload: dict) -> bool:
    try:
        r = requests.post(f"{CLOUD_API}/api/telemetry", json=payload, timeout=8)
        return r.status_code in (200, 201)
    except Exception:
        return False


def count_telemetry_since(run_start: str) -> int:
    """Count rows in cloud DB whose server-side created_at >= run_start."""
    con = sqlite3.connect(CLOUD_DB)
    try:
        return con.execute(
            "SELECT COUNT(*) FROM telemetry WHERE created_at >= ?", (run_start,)
        ).fetchone()[0]
    finally:
        con.close()


# ── Main ──────────────────────────────────────────────────────
def main() -> None:
    print("ColdTrace DC — Outage & Completeness Benchmark")
    print(f"Target API          : {CLOUD_API}")
    print(f"Packets per rate    : {N_PACKETS_PER_RATE}")
    print(f"Outage rates tested : {[f'{r:.0%}' for r in OUTAGE_RATES]}")
    print(f"Buffer DB           : {BUFFER_DB.name}")

    try:
        r = requests.get(f"{CLOUD_API}/health", timeout=5)
        r.raise_for_status()
        print(f"Backend             : OK ({r.json().get('service', 'ok')})\n")
    except Exception as e:
        print(f"\nBackend unreachable: {e}")
        print("Start with: cd backend && uvicorn app.main:app --reload")
        sys.exit(1)

    header = (
        f"{'Outage Rate':>12}  {'Generated':>10}  {'Buffered':>9}  "
        f"{'Delivered':>10}  {'Completeness':>13}  {'Flushed':>8}"
    )
    print(header)
    print("-" * len(header))

    for outage_rate in OUTAGE_RATES:
        clear_buffer()
        run_start = utc_now()

        local_state: dict[str, dict] = {
            d["device_id"]: {"battery_voltage": d["battery_voltage"], "step": 0}
            for d in DEVICES
        }

        generated = buffered_count = direct_ok = direct_fail = 0

        for i in range(N_PACKETS_PER_RATE):
            device  = DEVICES[i % len(DEVICES)]
            payload = build_payload(device, local_state[device["device_id"]])
            generated += 1

            if random.random() < outage_rate:
                # Simulated outage → buffer
                buffer_packet(payload)
                buffered_count += 1
            else:
                ok = post_direct(payload)
                if ok:
                    direct_ok += 1
                else:
                    # Backend-side error → buffer as fallback
                    buffer_packet(payload)
                    buffered_count += 1

        # Network recovery — flush everything with no outage simulation
        flushed, flush_failed = flush_all_buffered()

        # Count how many ended up in the cloud DB (server-side timestamp)
        delivered    = count_telemetry_since(run_start)
        completeness = (delivered / generated * 100) if generated > 0 else 0.0

        print(
            f"{outage_rate:>11.0%}  {generated:>10}  {buffered_count:>9}  "
            f"{delivered:>10}  {completeness:>12.1f}%  {flushed:>8}"
        )

    print()
    print("Completeness = packets received in cloud DB / packets generated × 100")
    print("After recovery flush, completeness should approach 100 % at all outage rates.")
    print("Divergence indicates packets lost during the flush retry (backend errors).")


if __name__ == "__main__":
    main()
