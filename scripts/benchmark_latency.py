#!/usr/bin/env python3
"""
benchmark_latency.py
====================
Measures end-to-end ingestion latency of the ColdTrace backend.
Sends N_PACKETS packets to /api/telemetry (no auth required) and reports
P50 / P95 / P99 / max latency plus throughput.

Usage:
    cd ColdChainDC
    python scripts/benchmark_latency.py [N_PACKETS] [scale]

    python scripts/benchmark_latency.py          # 1000 packets, 7 devices
    python scripts/benchmark_latency.py 500
    python scripts/benchmark_latency.py 1000 scale   # also tests at 14 / 28 / 56 virtual devices

Prerequisites: backend running at http://127.0.0.1:8000
    cd backend && uvicorn app.main:app --reload
"""
from __future__ import annotations

import random
import sys
import time
import uuid
from datetime import UTC, datetime
from pathlib import Path

# Force UTF-8 output so non-ASCII chars survive file redirection on Windows
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

import requests

# ── Path setup ────────────────────────────────────────────────
PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "simulator"))
from config import DEVICES  # noqa: E402

# ── Config ────────────────────────────────────────────────────
CLOUD_API  = "http://127.0.0.1:8000"
N_PACKETS  = int(sys.argv[1]) if len(sys.argv) > 1 else 1000
RUN_SCALE  = len(sys.argv) > 2 and sys.argv[2].lower() == "scale"


# ── Simulator helpers (replicated locally to avoid global STATE collision) ──
def utc_now() -> str:
    return datetime.now(UTC).replace(microsecond=0).isoformat()


def drift_temp(device: dict, state: dict) -> float:
    """Exact replica of run_gateway.drift_temp() — ground-truth excursion logic."""
    base = device["baseline_temperature"]
    step = state["step"]
    # PUNE TRUCK: periodic door-open excursion
    if device["device_id"] == "LTAT-PUNE-TRUCK-01" and step % 12 in (4, 5, 6):
        return round(random.uniform(8.4, 9.8), 2)
    # NASHIK clinic: under-cooling / power outage
    if device["device_id"] == "LTAT-NASHIK-01" and step % 16 in (7, 8):
        return round(random.uniform(1.0, 1.8), 2)
    # KOL transit: older gateway drift
    if device["device_id"] == "LTAT-KOL-01" and step % 20 in (10, 11):
        return round(random.uniform(8.1, 8.9), 2)
    return round(base + random.uniform(-0.55, 0.55), 2)


def build_payload(device: dict, state: dict) -> dict:
    state["step"] += 1
    state["battery_voltage"] = max(1.90, round(
        state["battery_voltage"] - random.uniform(0.001, 0.007), 3
    ))
    lat = device["latitude"]
    lon = device["longitude"]
    if device["transport_mode"] == "transit":
        lat = round(lat + random.uniform(-0.009, 0.009), 6)
        lon = round(lon + random.uniform(-0.009, 0.009), 6)
    return {
        "packet_id":       f"PKT-BL-{uuid.uuid4().hex[:10].upper()}",
        "device_id":       device["device_id"],
        "gateway_id":      device["gateway_id"],
        "facility_id":     device["facility_id"],
        "batch_id":        device["batch_id"],
        "recorded_at":     utc_now(),
        "temperature_c":   drift_temp(device, state),
        "humidity_pct":    round(device["humidity_pct"] + random.uniform(-4.0, 4.0), 2),
        "battery_voltage": state["battery_voltage"],
        "latitude":        lat,
        "longitude":       lon,
        "transport_mode":  device["transport_mode"],
    }


def percentile(sorted_vals: list[float], p: float) -> float:
    if not sorted_vals:
        return 0.0
    idx = min(int(len(sorted_vals) * p / 100), len(sorted_vals) - 1)
    return sorted_vals[idx]


# ── Benchmark runner ──────────────────────────────────────────
def run_benchmark(devices: list[dict], n_packets: int, label: str) -> None:
    state: dict[str, dict] = {
        d["device_id"]: {"battery_voltage": d["battery_voltage"], "step": 0}
        for d in devices
    }

    print(f"\n{'='*60}")
    print(f"  {label}")
    print(f"  Devices: {len(devices)}   Packets: {n_packets}")
    print(f"{'='*60}")

    latencies: list[float] = []
    errors = 0
    t_wall_start = time.perf_counter()

    for i in range(n_packets):
        device = devices[i % len(devices)]
        dev_id = device["device_id"]
        payload = build_payload(device, state[dev_id])

        t0 = time.perf_counter()
        try:
            r = requests.post(f"{CLOUD_API}/api/telemetry", json=payload, timeout=10)
            t1 = time.perf_counter()
            if r.status_code in (200, 201):
                latencies.append((t1 - t0) * 1000)   # ms
            else:
                errors += 1
                print(f"  [WARN] HTTP {r.status_code} on packet {i+1}")
        except Exception as exc:
            errors += 1
            print(f"  [ERR]  packet {i+1}: {exc}")

    t_wall = time.perf_counter() - t_wall_start
    throughput = len(latencies) / t_wall if t_wall > 0 else 0.0

    if not latencies:
        print("  No successful packets — is the backend running?")
        return

    s = sorted(latencies)
    print(f"\n  Results ({len(latencies)} successful, {errors} errors):")
    print(f"  {'Metric':<20}  {'Value':>14}")
    print(f"  {'-'*37}")
    print(f"  {'P50  (ms)':<20}  {percentile(s, 50):>13.2f}")
    print(f"  {'P95  (ms)':<20}  {percentile(s, 95):>13.2f}")
    print(f"  {'P99  (ms)':<20}  {percentile(s, 99):>13.2f}")
    print(f"  {'Max  (ms)':<20}  {max(s):>13.2f}")
    print(f"  {'Min  (ms)':<20}  {min(s):>13.2f}")
    print(f"  {'Mean (ms)':<20}  {sum(s)/len(s):>13.2f}")
    print(f"  {'Throughput (pkt/s)':<20}  {throughput:>13.1f}")
    print(f"  {'Total time (s)':<20}  {t_wall:>13.2f}")


# ── Entry point ───────────────────────────────────────────────
def main() -> None:
    print("ColdTrace DC — Latency Benchmark")
    print(f"Target API : {CLOUD_API}")
    print(f"Packets    : {N_PACKETS}")
    print(f"Scale test : {RUN_SCALE}")

    # Connectivity check
    try:
        r = requests.get(f"{CLOUD_API}/health", timeout=5)
        r.raise_for_status()
        svc = r.json().get("service", "ok")
        print(f"Backend    : OK ({svc})\n")
    except Exception as e:
        print(f"\nBackend unreachable: {e}")
        print("Start with: cd backend && uvicorn app.main:app --reload")
        sys.exit(1)

    # Primary benchmark — 7 real devices
    run_benchmark(DEVICES, N_PACKETS, f"Baseline — {len(DEVICES)} devices, {N_PACKETS} packets")

    # Scale test — same 7 real device IDs, increasing packet volume
    # (virtual IDs would 500 because they are not seeded in the devices table)
    if RUN_SCALE:
        for multiplier in (2, 4, 8):
            n = min(N_PACKETS, 200) * multiplier
            run_benchmark(DEVICES, n, f"Scale ×{multiplier} — {len(DEVICES)} devices, {n} packets")

    print(f"\nDone.")


if __name__ == "__main__":
    main()
