#!/usr/bin/env python3
"""
benchmark_anomaly.py
====================
Evaluates the Alert Engine's anomaly detection accuracy AND verifies the
SHA-256 hash-linked audit chain.

Phase 1 — Inject packets
    Sends N_STEPS cycles × 7 devices = N_STEPS × 7 packets at no sleep delay.
    The exact drift_temp() logic from run_gateway.py is replicated locally so
    we know the ground-truth excursion timestamps.

    Ground-truth excursion sequences per N_STEPS = 240:
        LTAT-PUNE-TRUCK-01  step % 12 ∈ {4,5,6}  → 20 sequences
        LTAT-NASHIK-01      step % 16 ∈ {7,8}    → 15 sequences
        LTAT-KOL-01         step % 20 ∈ {10,11}  → 12 sequences

Phase 2 — Compare to detected incidents
    Queries coldchain.db for incidents of type temperature_excursion whose
    opened_at >= run_start, then matches them to the ground truth by
    (device_id, ±MATCH_WINDOW_SEC).

Phase 3 — Report metrics
    Precision, Recall, F1-score, per-device breakdown, average detection delay.

Phase 4 — Audit chain verification
    Walks every entry in audit_log in chronological order and checks that
    previous_hash[i] == entry_hash[i-1].  Reports any broken links.

Usage:
    cd ColdChainDC
    python scripts/benchmark_anomaly.py [N_STEPS]

    python scripts/benchmark_anomaly.py          # 240 steps (default)
    python scripts/benchmark_anomaly.py 120      # faster test

Prerequisites:
  - Backend running at http://127.0.0.1:8000
      cd backend && uvicorn app.main:app --reload
  - Recommend a fresh DB (delete coldchain.db and restart backend) so
    pre-existing open incidents do not affect the ground-truth alignment.
    The script auto-adjusts for pre-existing open incidents when possible.
"""
from __future__ import annotations

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
CLOUD_API    = "http://127.0.0.1:8000"
N_STEPS      = int(sys.argv[1]) if len(sys.argv) > 1 else 240

sys.path.insert(0, str(PROJECT_ROOT / "simulator"))
from config import DEVICES  # noqa: E402

TEMP_MIN       = 2.0   # device threshold min_temp_c (from seed_reference_data)
TEMP_MAX       = 8.0   # device threshold max_temp_c
MATCH_WINDOW_S = 30    # seconds tolerance for GT ↔ incident time matching


# ── Simulator helpers (exact replica of run_gateway.py) ───────
def utc_now() -> str:
    return datetime.now(UTC).replace(microsecond=0).isoformat()


def drift_temp(device: dict, state: dict) -> float:
    """Exact replica of run_gateway.drift_temp() — DO NOT modify."""
    base = device["baseline_temperature"]
    step = state["step"]
    if device["device_id"] == "LTAT-PUNE-TRUCK-01" and step % 12 in (4, 5, 6):
        return round(random.uniform(8.4, 9.8), 2)
    if device["device_id"] == "LTAT-NASHIK-01" and step % 16 in (7, 8):
        return round(random.uniform(1.0, 1.8), 2)
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
        "packet_id":       f"PKT-AN-{uuid.uuid4().hex[:10].upper()}",
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


def parse_iso(ts: str) -> datetime:
    return datetime.fromisoformat(ts.replace("Z", "+00:00"))


# ── Phase 4: Audit chain verification ────────────────────────
def verify_audit_chain() -> None:
    print("\n" + "=" * 60)
    print("  Audit Chain Integrity (SHA-256 hash-linked log)")
    print("=" * 60)

    con = sqlite3.connect(CLOUD_DB)
    con.row_factory = sqlite3.Row
    try:
        rows = con.execute(
            """
            SELECT id, entity_type, entity_id, action,
                   entry_hash, previous_hash, created_at
            FROM audit_log
            ORDER BY created_at ASC, rowid ASC
            """
        ).fetchall()
    finally:
        con.close()

    if not rows:
        print("  No audit entries found.")
        return

    total      = len(rows)
    valid      = 0
    first_break: int | None = None

    for i, row in enumerate(rows):
        expected_prev = "" if i == 0 else rows[i - 1]["entry_hash"]
        if row["previous_hash"] == expected_prev:
            valid += 1
        else:
            if first_break is None:
                first_break = i + 1
                print(f"  [BREAK] Entry {i + 1} of {total}")
                print(f"    id              : {row['id']}")
                print(f"    action          : {row['entity_type']}/{row['action']}")
                print(f"    expected prev   : {expected_prev[:24]}...")
                print(f"    actual   prev   : {row['previous_hash'][:24]}...")

    print(f"\n  Total audit entries : {total}")
    print(f"  Valid hash links    : {valid}")
    chain_ok = first_break is None
    print(f"  Chain intact        : {'YES [OK]' if chain_ok else f'NO - first break at entry {first_break}'}")
    if chain_ok and rows:
        print(f"  Tip hash (first 32) : {rows[-1]['entry_hash'][:32]}...")


# ── Main benchmark ────────────────────────────────────────────
def main() -> None:
    print("ColdTrace DC — Anomaly Detection Benchmark")
    print(f"Target API      : {CLOUD_API}")
    print(f"Steps per device: {N_STEPS}")
    print(f"Total packets   : {N_STEPS * len(DEVICES)}")

    try:
        r = requests.get(f"{CLOUD_API}/health", timeout=5)
        r.raise_for_status()
        print(f"Backend         : OK ({r.json().get('service', 'ok')})\n")
    except Exception as e:
        print(f"\nBackend unreachable: {e}")
        print("Start with: cd backend && uvicorn app.main:app --reload")
        sys.exit(1)

    # ── Init local state ──────────────────────────────────────
    local_state: dict[str, dict] = {
        d["device_id"]: {"battery_voltage": d["battery_voltage"], "step": 0}
        for d in DEVICES
    }

    # Adjust in_excursion for any pre-existing open incidents (avoid GT mismatch)
    con = sqlite3.connect(CLOUD_DB)
    con.row_factory = sqlite3.Row
    pre_open = con.execute(
        "SELECT device_id FROM incidents WHERE status='open' AND incident_type='temperature_excursion'"
    ).fetchall()
    con.close()
    pre_open_ids = {row["device_id"] for row in pre_open}
    in_excursion: dict[str, bool] = {
        d["device_id"]: (d["device_id"] in pre_open_ids) for d in DEVICES
    }
    if pre_open_ids:
        print(f"Note: {len(pre_open_ids)} device(s) have pre-existing open incidents - "
              f"adjusted ground-truth tracking: {pre_open_ids}\n")

    # ── Phase 1: Send packets, track ground truth ─────────────
    run_start  = utc_now()
    ground_truth: list[dict] = []   # one entry per excursion sequence start
    total_sent = total_errors = 0

    print(f"Sending {N_STEPS} steps x {len(DEVICES)} devices...")

    for step in range(1, N_STEPS + 1):
        for device in DEVICES:
            did     = device["device_id"]
            state   = local_state[did]
            payload = build_payload(device, state)   # increments state["step"]
            temp    = payload["temperature_c"]
            is_exc  = temp < TEMP_MIN or temp > TEMP_MAX

            # Track the FIRST packet of each new excursion sequence
            if is_exc and not in_excursion[did]:
                ground_truth.append({
                    "device_id":   did,
                    "recorded_at": payload["recorded_at"],
                    "step":        state["step"],
                    "temp":        temp,
                })
                in_excursion[did] = True
            elif not is_exc:
                in_excursion[did] = False   # sequence ended; next excursion = new GT

            try:
                r = requests.post(
                    f"{CLOUD_API}/api/telemetry", json=payload, timeout=10
                )
                if r.status_code in (200, 201):
                    total_sent += 1
                else:
                    total_errors += 1
            except Exception as exc:
                total_errors += 1

        # Progress ticker every 60 steps
        if step % 60 == 0 or step == N_STEPS:
            print(f"  step {step}/{N_STEPS}  |  GT so far: {len(ground_truth)}")

    print(f"\nPackets sent={total_sent}, errors={total_errors}")
    print(f"Ground truth excursion sequences: {len(ground_truth)}")

    # ── Phase 2: Query detected incidents ─────────────────────
    con = sqlite3.connect(CLOUD_DB)
    con.row_factory = sqlite3.Row
    detected_rows = con.execute(
        """
        SELECT id, device_id, batch_id, incident_type, opened_at, severity
        FROM   incidents
        WHERE  incident_type = 'temperature_excursion'
          AND  opened_at >= ?
        ORDER  BY opened_at ASC
        """,
        (run_start,),
    ).fetchall()
    con.close()

    detected: list[dict] = [dict(r) for r in detected_rows]
    print(f"Detected incidents (temperature_excursion, opened_at >= run_start): {len(detected)}")

    # ── Phase 3: Match GT → detected (greedy, by device+time) ─
    matched_detected: set[int] = set()
    tp_delays: list[float]    = []
    tp_count = fn_count        = 0

    per_device: dict[str, dict] = {
        d["device_id"]: {"gt": 0, "tp": 0, "fn": 0} for d in DEVICES
    }

    for gt in ground_truth:
        did     = gt["device_id"]
        gt_time = parse_iso(gt["recorded_at"])
        per_device[did]["gt"] += 1

        best_idx   = None
        best_delta = float("inf")

        for i, inc in enumerate(detected):
            if i in matched_detected:
                continue
            if inc["device_id"] != did:
                continue
            delta = abs((parse_iso(inc["opened_at"]) - gt_time).total_seconds())
            if delta <= MATCH_WINDOW_S and delta < best_delta:
                best_delta = delta
                best_idx   = i

        if best_idx is not None:
            matched_detected.add(best_idx)
            tp_count += 1
            tp_delays.append(best_delta)
            per_device[did]["tp"] += 1
        else:
            fn_count += 1
            per_device[did]["fn"] += 1

    fp_count  = len(detected) - len(matched_detected)
    precision = tp_count / (tp_count + fp_count) if (tp_count + fp_count) > 0 else 0.0
    recall    = tp_count / (tp_count + fn_count) if (tp_count + fn_count) > 0 else 0.0
    f1        = (2 * precision * recall / (precision + recall)) if (precision + recall) > 0 else 0.0
    avg_delay = sum(tp_delays) / len(tp_delays) if tp_delays else 0.0

    # ── Print aggregate results ───────────────────────────────
    print("\n" + "=" * 60)
    print("  Anomaly Detection Results")
    print("=" * 60)
    print(f"\n  {'Metric':<28}  {'Value':>12}")
    print(f"  {'-'*43}")
    print(f"  {'Ground truth events':<28}  {len(ground_truth):>12}")
    print(f"  {'Detected incidents':<28}  {len(detected):>12}")
    print(f"  {'True Positives  (TP)':<28}  {tp_count:>12}")
    print(f"  {'False Positives (FP)':<28}  {fp_count:>12}")
    print(f"  {'False Negatives (FN)':<28}  {fn_count:>12}")
    print(f"  {'Precision':<28}  {precision:>11.1%}")
    print(f"  {'Recall':<28}  {recall:>11.1%}")
    print(f"  {'F1 Score':<28}  {f1:>12.4f}")
    print(f"  {'Avg detection delay (s)':<28}  {avg_delay:>11.2f}")
    print(f"  {'Match window used (s)':<28}  {MATCH_WINDOW_S:>12}")

    # ── Per-device breakdown ──────────────────────────────────
    excursion_note = {
        "LTAT-PUNE-TRUCK-01": "door-open (step%12 in {4,5,6})",
        "LTAT-NASHIK-01":     "power-cut (step%16 in {7,8})",
        "LTAT-KOL-01":        "gw-drift  (step%20 in {10,11})",
    }

    print(f"\n  Per-device breakdown (only excursion devices show GT > 0):")
    print(f"  {'Device':<26}  {'GT':>4}  {'TP':>4}  {'FN':>4}  {'Recall':>8}  Note")
    print(f"  {'-'*72}")
    for did, c in per_device.items():
        gt  = c["gt"]
        tp  = c["tp"]
        fn  = c["fn"]
        rec = tp / gt if gt > 0 else 0.0
        note = excursion_note.get(did, "")
        print(f"  {did:<26}  {gt:>4}  {tp:>4}  {fn:>4}  {rec:>7.0%}  {note}")

    print(f"\n  Expected excursion counts for N_STEPS = {N_STEPS}:")
    print(f"    PUNE   (step%12 in {{4,5,6}}) : {N_STEPS // 12} sequences")
    print(f"    NASHIK (step%16 in {{7,8}}  ) : {N_STEPS // 16} sequences")
    print(f"    KOL    (step%20 in {{10,11}}) : {N_STEPS // 20} sequences")
    print(f"    Total                      : {N_STEPS//12 + N_STEPS//16 + N_STEPS//20}")

    # ── Phase 4: Audit chain verification ────────────────────
    verify_audit_chain()

    print(f"\nDone.")


if __name__ == "__main__":
    main()
