from __future__ import annotations

import hashlib
import json
import sqlite3
import threading
import uuid
from collections import Counter
from datetime import UTC, datetime, timedelta

from .auth import ROLE_VACCINATOR
from .config import settings
from .integrations import send_email, send_sms
from .schemas import TelemetryIn


DB_LOCK = threading.Lock()


def now_iso() -> str:
    return datetime.now(UTC).replace(microsecond=0).isoformat()


def parse_iso(timestamp: str) -> datetime:
    return datetime.fromisoformat(timestamp.replace("Z", "+00:00"))


def facility_scope_for_user(user: dict | None) -> str | None:
    if user and user.get("role") == ROLE_VACCINATOR and user.get("facility_id"):
        return user["facility_id"]
    return None


def create_audit_entry(
    connection: sqlite3.Connection,
    entity_type: str,
    entity_id: str,
    action: str,
    payload: dict,
) -> None:
    serialized = json.dumps(payload, sort_keys=True)
    previous = connection.execute(
        "SELECT entry_hash FROM audit_log ORDER BY created_at DESC, id DESC LIMIT 1"
    ).fetchone()
    previous_hash = previous["entry_hash"] if previous else ""
    raw_hash = f"{entity_type}|{entity_id}|{action}|{serialized}|{previous_hash}"
    entry_hash = hashlib.sha256(raw_hash.encode("utf-8")).hexdigest()
    connection.execute(
        """
        INSERT INTO audit_log (id, entity_type, entity_id, action, payload, previous_hash, entry_hash, created_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (str(uuid.uuid4()), entity_type, entity_id, action, serialized, previous_hash, entry_hash, now_iso()),
    )


def log_dc_event(
    connection: sqlite3.Connection,
    event_type: str,
    node_id: str,
    description: str,
    metadata: dict | None = None,
) -> None:
    connection.execute(
        "INSERT INTO dc_events (event_type, node_id, description, metadata, occurred_at) VALUES (?, ?, ?, ?, ?)",
        (event_type, node_id, description, json.dumps(metadata or {}), now_iso()),
    )


def seed_reference_data(connection: sqlite3.Connection) -> None:
    if connection.execute("SELECT COUNT(*) FROM facilities").fetchone()[0]:
        return

    facilities = [
        ("FAC-MUM-HUB",      "Mumbai Regional Cold Hub",      "regional_hub", "Mumbai",   "healthy", 19.0760, 72.8777, "Plot 12, MIDC Andheri E, Mumbai 400093", "Dr. Priya Nair",      "+91-22-40001111"),
        ("FAC-PUNE-TRANSIT",  "Pune Transit Vehicle Dock",     "transit",      "Pune",     "healthy", 18.5204, 73.8567, "Gate 4, Bhosari MIDC, Pune 411026",      "Rajan Mehta",         "+91-20-40002222"),
        ("FAC-NASHIK-CLINIC", "Nashik Outreach Clinic",        "clinic",       "Nashik",   "watch",   19.9975, 73.7898, "Primary Health Centre, Deolali, Nashik", "Anita Kulkarni",      "+91-253-4000333"),
        ("FAC-AUR-STORE",     "Aurangabad Cold Store",         "cold_storage", "Aurangabad","healthy", 19.8762, 75.3433, "Civil Hospital Complex, Aurangabad",     "Suresh Patil",        "+91-240-4000444"),
        ("FAC-NGP-HUB",       "Nagpur Northern Hub",           "regional_hub", "Nagpur",   "healthy", 21.1458, 79.0882, "Medical Square, Nagpur 440009",          "Dr. Ramesh Deshmukh", "+91-712-4000555"),
        ("FAC-KOL-TRANSIT",   "Kolhapur Transit Point",        "transit",      "Kolhapur", "healthy", 16.7050, 74.2433, "NH-4 Bypass, Kolhapur 416001",           "Meera Joshi",         "+91-231-4000666"),
    ]

    gateways = [
        ("IGD-MUM-01",    "FAC-MUM-HUB",      "IGD-v2", "online",  "2.1.4", None, 0),
        ("IGD-PUNE-01",   "FAC-PUNE-TRANSIT",  "IGD-v2", "online",  "2.1.4", None, 0),
        ("IGD-NASHIK-01", "FAC-NASHIK-CLINIC", "IGD-v1", "online",  "2.0.9", None, 3),
        ("IGD-AUR-01",    "FAC-AUR-STORE",     "IGD-v2", "online",  "2.1.4", None, 0),
        ("IGD-NGP-01",    "FAC-NGP-HUB",       "IGD-v2", "online",  "2.1.4", None, 0),
        ("IGD-KOL-01",    "FAC-KOL-TRANSIT",   "IGD-v1", "degraded","2.0.7", None, 12),
    ]

    devices = [
        ("LTAT-MUM-01",       "FAC-MUM-HUB",      "IGD-MUM-01",    "cold_room",       "active",  2.0, 8.0, None, "1.4.2", 5),
        ("LTAT-MUM-02",       "FAC-MUM-HUB",      "IGD-MUM-01",    "refrigerator",    "active",  2.0, 8.0, None, "1.4.2", 5),
        ("LTAT-PUNE-TRUCK-01","FAC-PUNE-TRANSIT",  "IGD-PUNE-01",   "vehicle",         "active",  2.0, 8.0, None, "1.4.2", 5),
        ("LTAT-NASHIK-01",    "FAC-NASHIK-CLINIC", "IGD-NASHIK-01", "portable_carrier","active",  2.0, 8.0, None, "1.3.8", 5),
        ("LTAT-AUR-01",       "FAC-AUR-STORE",     "IGD-AUR-01",    "cold_room",       "active",  2.0, 8.0, None, "1.4.2", 5),
        ("LTAT-NGP-01",       "FAC-NGP-HUB",       "IGD-NGP-01",    "cold_room",       "active",  2.0, 8.0, None, "1.4.2", 5),
        ("LTAT-KOL-01",       "FAC-KOL-TRANSIT",   "IGD-KOL-01",    "vehicle",         "active",  2.0, 8.0, None, "1.3.5", 5),
    ]

    vaccines = [
        ("VAC-CVX",  "Covishield",  "Serum Institute of India",   2.0, 8.0, 730, 0),
        ("VAC-CVN",  "Covaxin",     "Bharat Biotech",             2.0, 8.0, 365, 0),
        ("VAC-RVX",  "Rotavac",     "Bharat Biotech",             2.0, 8.0, 730, 0),
        ("VAC-IPV",  "IPV",         "Bio-Med Pvt Ltd",            2.0, 8.0, 730, 0),
        ("VAC-OPV",  "OPV",         "Panacea Biotec",             2.0, 8.0, 365, 0),
    ]

    batches = [
        ("BATCH-CVX-001", "VAC-CVX", "Covishield",  "Serum Institute of India", "LOT-SII-2025-041",  "FAC-MUM-HUB",     "FAC-NASHIK-CLINIC", "in_transit",  1200, 1200, "2025-01-15T00:00:00+00:00", "2026-07-15T00:00:00+00:00"),
        ("BATCH-CVX-002", "VAC-CVX", "Covaxin",     "Bharat Biotech",           "LOT-BB-2025-089",   "FAC-MUM-HUB",     "FAC-PUNE-TRANSIT",  "stored",       800,  800, "2025-02-01T00:00:00+00:00", "2026-02-01T00:00:00+00:00"),
        ("BATCH-RVX-001", "VAC-RVX", "Rotavac",     "Bharat Biotech",           "LOT-BB-2025-112",   "FAC-NGP-HUB",     "FAC-AUR-STORE",     "delivered",    500,  480, "2025-03-10T00:00:00+00:00", "2027-03-10T00:00:00+00:00"),
        ("BATCH-IPV-001", "VAC-IPV", "IPV",         "Bio-Med Pvt Ltd",          "LOT-BM-2025-019",   "FAC-NGP-HUB",     "FAC-NASHIK-CLINIC", "in_transit",   300,  300, "2025-04-01T00:00:00+00:00", "2027-04-01T00:00:00+00:00"),
        ("BATCH-OPV-001", "VAC-OPV", "OPV",         "Panacea Biotec",           "LOT-PB-2025-203",   "FAC-MUM-HUB",     "FAC-KOL-TRANSIT",   "in_transit",  2000, 2000, "2025-04-05T00:00:00+00:00", "2026-04-05T00:00:00+00:00"),
    ]

    connection.executemany(
        "INSERT INTO facilities (id,name,facility_type,region,status,latitude,longitude,address,contact_name,contact_phone) VALUES (?,?,?,?,?,?,?,?,?,?)",
        facilities,
    )
    connection.executemany(
        "INSERT INTO gateways (id,facility_id,model,status,firmware_version,last_seen_at,buffered_packets) VALUES (?,?,?,?,?,?,?)",
        gateways,
    )
    connection.executemany(
        "INSERT INTO devices (id,facility_id,gateway_id,device_type,status,min_temp_c,max_temp_c,last_seen_at,firmware_version,sensor_count) VALUES (?,?,?,?,?,?,?,?,?,?)",
        devices,
    )
    connection.executemany(
        "INSERT INTO vaccines (id,name,manufacturer,storage_temp_min,storage_temp_max,shelf_life_days,requires_freezer) VALUES (?,?,?,?,?,?,?)",
        vaccines,
    )
    connection.executemany(
        "INSERT INTO batches (id,vaccine_id,vaccine_name,manufacturer,lot_number,origin_facility_id,destination_facility_id,status,doses_total,doses_remaining,manufactured_at,expires_at) VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
        batches,
    )
    create_audit_entry(
        connection, "system", "bootstrap", "seed_reference_data",
        {"facilities": len(facilities), "devices": len(devices), "batches": len(batches)},
    )
    log_dc_event(connection, "system_boot", "CLOUD-01", "Reference data seeded", {"nodes": len(devices)})


def compute_trend_slope(values: list[float]) -> float:
    n = len(values)
    if n < 2:
        return 0.0
    xs = list(range(n))
    x_mean = sum(xs) / n
    y_mean = sum(values) / n
    numerator = sum((x - x_mean) * (y - y_mean) for x, y in zip(xs, values, strict=False))
    denominator = sum((x - x_mean) ** 2 for x in xs) or 1
    return numerator / denominator


def close_open_incidents(
    connection: sqlite3.Connection, device_id: str, batch_id: str, resolved_at: str,
) -> None:
    rows = connection.execute(
        "SELECT id FROM incidents WHERE device_id = ? AND batch_id = ? AND status = 'open'",
        (device_id, batch_id),
    ).fetchall()
    for row in rows:
        connection.execute(
            "UPDATE incidents SET status = 'resolved', resolved_at = ? WHERE id = ?",
            (resolved_at, row["id"]),
        )
        create_audit_entry(connection, "incident", row["id"], "resolved", {"resolved_at": resolved_at})
        log_dc_event(connection, "incident_resolved", device_id, f"Incident {row['id']} auto-resolved")


def get_notification_targets(connection: sqlite3.Connection, facility_id: str) -> list[dict]:
    rows = connection.execute(
        """
        SELECT id, full_name, email, phone_number, role, assigned_facility_id
        FROM users
        WHERE is_active = 1
          AND role IN ('admin', 'vaccine_manager', 'supervisor', 'vaccinator')
          AND (assigned_facility_id IS NULL OR assigned_facility_id = ?)
        ORDER BY role, full_name
        """,
        (facility_id,),
    ).fetchall()
    return [dict(row) for row in rows]


def create_notifications(
    connection: sqlite3.Connection, incident_id: str, reading: TelemetryIn, issue: dict,
) -> list[dict]:
    recipients = get_notification_targets(connection, reading.facility_id)
    created = []
    sms_text = (
        f"[{settings.app_name}] {issue['incident_type']} at {reading.facility_id} "
        f"for {reading.device_id}: {issue['reason']} at {reading.recorded_at}"
    )
    email_subject = f"{settings.app_name}: {issue['incident_type'].replace('_', ' ').title()}"
    email_html = (
        "<h2>Cold Chain Incident</h2>"
        f"<p><strong>Facility:</strong> {reading.facility_id}</p>"
        f"<p><strong>Device:</strong> {reading.device_id}</p>"
        f"<p><strong>Batch:</strong> {reading.batch_id}</p>"
        f"<p><strong>Temperature:</strong> {reading.temperature_c:.2f} C</p>"
        f"<p><strong>Battery:</strong> {reading.battery_voltage:.2f} V</p>"
        f"<p><strong>Reason:</strong> {issue['reason']}</p>"
        f"<p><strong>Recorded at:</strong> {reading.recorded_at}</p>"
    )

    for recipient in recipients:
        if recipient.get("phone_number"):
            sms_result = send_sms(recipient["phone_number"], sms_text)
            nid = f"NTF-{uuid.uuid4().hex[:8].upper()}"
            connection.execute(
                "INSERT INTO notifications (id,incident_id,channel,recipient,payload,status,sent_at,provider,provider_message_id,error_message) VALUES (?,?,'sms',?,?,?,?,?,?,?)",
                (nid, incident_id, recipient["phone_number"],
                 json.dumps({"user_id": recipient["id"], "body": sms_text}, sort_keys=True),
                 sms_result["status"], now_iso(), sms_result.get("provider","simulation"),
                 sms_result.get("provider_message_id",""),
                 "" if sms_result["status"] != "failed" else sms_result.get("message","")),
            )
            created.append({"notification_id": nid, "channel": "sms", "status": sms_result["status"]})

        if recipient.get("email"):
            email_result = send_email(recipient["email"], email_subject, email_html, sms_text)
            nid = f"NTF-{uuid.uuid4().hex[:8].upper()}"
            connection.execute(
                "INSERT INTO notifications (id,incident_id,channel,recipient,payload,status,sent_at,provider,provider_message_id,error_message) VALUES (?,?,'email',?,?,?,?,?,?,?)",
                (nid, incident_id, recipient["email"],
                 json.dumps({"user_id": recipient["id"], "subject": email_subject}, sort_keys=True),
                 email_result["status"], now_iso(), email_result.get("provider","simulation"),
                 email_result.get("provider_message_id",""),
                 "" if email_result["status"] != "failed" else email_result.get("message","")),
            )
            created.append({"notification_id": nid, "channel": "email", "status": email_result["status"]})

    log_dc_event(connection, "alert_multicast", "CLOUD-01",
                 f"Reliable multicast to {len(created)} channels for {incident_id}",
                 {"incident_id": incident_id, "channels": len(created)})
    return created


def open_or_update_incident(connection: sqlite3.Connection, reading: TelemetryIn, issue: dict) -> dict:
    open_incident = connection.execute(
        "SELECT * FROM incidents WHERE device_id = ? AND batch_id = ? AND incident_type = ? AND status = 'open' ORDER BY opened_at DESC LIMIT 1",
        (reading.device_id, reading.batch_id, issue["incident_type"]),
    ).fetchone()

    if open_incident:
        connection.execute(
            "UPDATE incidents SET latest_temperature_c=?, battery_voltage=?, min_temperature_c=MIN(min_temperature_c,?), max_temperature_c=MAX(max_temperature_c,?), severity=? WHERE id=?",
            (reading.temperature_c, reading.battery_voltage, reading.temperature_c, reading.temperature_c, issue["severity"], open_incident["id"]),
        )
        create_audit_entry(connection, "incident", open_incident["id"], "updated",
                           {"packet_id": reading.packet_id, "severity": issue["severity"]})
        return {"incident_id": open_incident["id"], "status": "updated", **issue}

    incident_id = f"INC-{uuid.uuid4().hex[:8].upper()}"
    connection.execute(
        "INSERT INTO incidents (id,device_id,batch_id,facility_id,incident_type,severity,status,reason,opened_at,resolved_at,latest_temperature_c,min_temperature_c,max_temperature_c,battery_voltage) VALUES (?,?,?,?,?,?,'open',?,?,NULL,?,?,?,?)",
        (incident_id, reading.device_id, reading.batch_id, reading.facility_id,
         issue["incident_type"], issue["severity"], issue["reason"], reading.recorded_at,
         reading.temperature_c, reading.temperature_c, reading.temperature_c, reading.battery_voltage),
    )
    notifications = create_notifications(connection, incident_id, reading, issue)
    create_audit_entry(connection, "incident", incident_id, "opened",
                       {"packet_id": reading.packet_id, "issue": issue, "notifications": len(notifications)})
    log_dc_event(connection, "incident_opened", reading.device_id,
                 f"{issue['incident_type']} at {reading.facility_id}: {issue['reason']}",
                 {"incident_id": incident_id, "severity": issue["severity"]})
    return {"incident_id": incident_id, "status": "opened", "notifications": notifications, **issue}


def evaluate_reading(connection: sqlite3.Connection, reading: TelemetryIn) -> dict:
    device = connection.execute(
        "SELECT min_temp_c, max_temp_c FROM devices WHERE id = ?", (reading.device_id,),
    ).fetchone()
    window_start = (parse_iso(reading.recorded_at) - timedelta(minutes=30)).isoformat()
    history = connection.execute(
        "SELECT recorded_at, temperature_c FROM telemetry WHERE device_id = ? AND recorded_at >= ? ORDER BY recorded_at ASC",
        (reading.device_id, window_start),
    ).fetchall()
    temperatures = [row["temperature_c"] for row in history]
    rolling_average = round(sum(temperatures) / len(temperatures), 2) if temperatures else reading.temperature_c
    trend_slope = round(compute_trend_slope(temperatures), 4) if len(temperatures) >= 2 else 0.0

    issue = None
    if reading.temperature_c < device["min_temp_c"] or reading.temperature_c > device["max_temp_c"]:
        issue = {
            "incident_type": "temperature_excursion",
            "severity": "critical" if abs(reading.temperature_c - 5.0) >= 4 else "warning",
            "reason": f"Temperature out of range: {reading.temperature_c:.2f} C",
            "rolling_average_c": rolling_average,
            "trend_slope": trend_slope,
        }
    elif reading.battery_voltage < 2.1:
        issue = {
            "incident_type": "low_battery",
            "severity": "warning",
            "reason": f"Battery low: {reading.battery_voltage:.2f} V",
            "rolling_average_c": rolling_average,
            "trend_slope": trend_slope,
        }

    if issue:
        return open_or_update_incident(connection, reading, issue)

    close_open_incidents(connection, reading.device_id, reading.batch_id, reading.recorded_at)
    return {"incident_type": None, "rolling_average_c": rolling_average, "trend_slope": trend_slope}


def insert_telemetry(connection: sqlite3.Connection, reading: TelemetryIn) -> dict:
    with DB_LOCK:
        if connection.execute("SELECT id FROM telemetry WHERE packet_id = ?", (reading.packet_id,)).fetchone():
            return {"status": "duplicate", "packet_id": reading.packet_id}

        incident = evaluate_reading(connection, reading)

        connection.execute(
            "INSERT INTO telemetry (packet_id,device_id,gateway_id,facility_id,batch_id,recorded_at,temperature_c,humidity_pct,battery_voltage,latitude,longitude,transport_mode,rolling_avg_c,trend_slope,created_at) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (reading.packet_id, reading.device_id, reading.gateway_id, reading.facility_id,
             reading.batch_id, reading.recorded_at, reading.temperature_c, reading.humidity_pct,
             reading.battery_voltage, reading.latitude, reading.longitude, reading.transport_mode,
             incident.get("rolling_average_c"), incident.get("trend_slope"), now_iso()),
        )
        connection.execute(
            "UPDATE devices SET last_seen_at = ?, status = 'active' WHERE id = ?",
            (reading.recorded_at, reading.device_id),
        )
        connection.execute(
            "UPDATE gateways SET last_seen_at = ?, buffered_packets = 0 WHERE id = ?",
            (reading.recorded_at, reading.gateway_id),
        )
        create_audit_entry(connection, "telemetry", reading.packet_id, "ingested", reading.model_dump())
        log_dc_event(connection, "packet_ingested", reading.gateway_id,
                     f"Packet from {reading.device_id} ingested",
                     {"temp": reading.temperature_c, "battery": reading.battery_voltage})
        connection.commit()
        return {"status": "ingested", "packet_id": reading.packet_id, "incident": incident}


def build_overview(connection: sqlite3.Connection, user: dict | None = None) -> dict:
    scoped = facility_scope_for_user(user)
    p = [scoped] if scoped else []

    def wc(base_where="", extra=""):
        if scoped:
            return f" WHERE facility_id = ? {extra}"
        return f" {base_where} {extra}" if base_where else f" {extra}"

    active_incidents = connection.execute(
        f"SELECT COUNT(*) FROM incidents WHERE status = 'open'" + (" AND facility_id = ?" if scoped else ""),
        p,
    ).fetchone()[0]
    telemetry_total = connection.execute(
        "SELECT COUNT(*) FROM telemetry" + (" WHERE facility_id = ?" if scoped else ""),
        p,
    ).fetchone()[0]

    low_battery_sql = """
        SELECT COUNT(*) FROM (
            SELECT device_id, MAX(recorded_at) AS latest_at FROM telemetry {w} GROUP BY device_id
        ) latest
        JOIN telemetry t ON t.device_id = latest.device_id AND t.recorded_at = latest.latest_at
        WHERE t.battery_voltage < 2.1
    """.format(w="WHERE facility_id = ?" if scoped else "")
    low_battery_nodes = connection.execute(low_battery_sql, p).fetchone()[0]

    facilities = connection.execute(
        "SELECT COUNT(DISTINCT facility_id) FROM telemetry" + (" WHERE facility_id = ?" if scoped else ""),
        p,
    ).fetchone()[0] or connection.execute("SELECT COUNT(*) FROM facilities").fetchone()[0]

    latest_temps_sql = "SELECT device_id, temperature_c FROM telemetry WHERE id IN (SELECT MAX(id) FROM telemetry GROUP BY device_id)"
    latest_temps_p: list = []
    if scoped:
        latest_temps_sql = "SELECT device_id, temperature_c FROM telemetry WHERE facility_id = ? AND id IN (SELECT MAX(id) FROM telemetry WHERE facility_id = ? GROUP BY device_id)"
        latest_temps_p = [scoped, scoped]
    temps = [r["temperature_c"] for r in connection.execute(latest_temps_sql, latest_temps_p).fetchall()]
    average_temp = round(sum(temps) / len(temps), 2) if temps else None

    facility_health = [
        dict(r) for r in connection.execute(
            """SELECT f.id, f.name, f.status, f.region, f.latitude, f.longitude, COUNT(d.id) AS device_count,
               COALESCE(g.status, 'unknown') AS gateway_status
               FROM facilities f
               LEFT JOIN devices d ON d.facility_id = f.id
               LEFT JOIN gateways g ON g.facility_id = f.id
               """ + ("WHERE f.id = ?" if scoped else "") + " GROUP BY f.id ORDER BY f.name",
            p,
        ).fetchall()
    ]
    incident_mix = Counter(
        r["incident_type"] for r in connection.execute(
            "SELECT incident_type FROM incidents WHERE status = 'open'" + (" AND facility_id = ?" if scoped else ""),
            p,
        ).fetchall()
    )
    transit_assets = connection.execute(
        "SELECT COUNT(DISTINCT device_id) FROM telemetry WHERE transport_mode = 'transit'" + (" AND facility_id = ?" if scoped else ""),
        p,
    ).fetchone()[0]

    gateways = [dict(r) for r in connection.execute("SELECT * FROM gateways ORDER BY facility_id").fetchall()]

    return {
        "summary": {
            "facilities": facilities,
            "telemetry_packets": telemetry_total,
            "open_incidents": active_incidents,
            "low_battery_nodes": low_battery_nodes,
            "average_temperature_c": average_temp,
            "active_transit_assets": transit_assets,
        },
        "facility_health": facility_health,
        "incident_mix": dict(incident_mix),
        "gateways": gateways,
    }


def list_recent_telemetry(connection: sqlite3.Connection, limit: int = 20, user: dict | None = None) -> list[dict]:
    scoped = facility_scope_for_user(user)
    sql = """
        SELECT t.packet_id, t.device_id, t.gateway_id, t.facility_id, t.batch_id, t.recorded_at,
               t.temperature_c, t.humidity_pct, t.battery_voltage, t.latitude, t.longitude,
               t.transport_mode, t.rolling_avg_c, t.trend_slope, d.min_temp_c, d.max_temp_c,
               f.name AS facility_name
        FROM telemetry t
        JOIN devices d ON d.id = t.device_id
        JOIN facilities f ON f.id = t.facility_id
    """
    params: list = []
    if scoped:
        sql += " WHERE t.facility_id = ?"
        params.append(scoped)
    sql += " ORDER BY t.recorded_at DESC, t.id DESC LIMIT ?"
    params.append(limit)
    return [dict(r) for r in connection.execute(sql, params).fetchall()]


def list_incidents(connection: sqlite3.Connection, limit: int = 20, user: dict | None = None) -> list[dict]:
    scoped = facility_scope_for_user(user)
    sql = "SELECT i.*, f.name AS facility_name FROM incidents i JOIN facilities f ON f.id = i.facility_id"
    params: list = []
    if scoped:
        sql += " WHERE i.facility_id = ?"
        params.append(scoped)
    sql += " ORDER BY i.opened_at DESC LIMIT ?"
    params.append(limit)
    return [dict(r) for r in connection.execute(sql, params).fetchall()]


def list_notifications(connection: sqlite3.Connection, limit: int = 25, user: dict | None = None) -> list[dict]:
    scoped = facility_scope_for_user(user)
    sql = "SELECT n.*, i.incident_type, i.severity, i.facility_id FROM notifications n JOIN incidents i ON i.id = n.incident_id"
    params: list = []
    if scoped:
        sql += " WHERE i.facility_id = ?"
        params.append(scoped)
    sql += " ORDER BY n.sent_at DESC LIMIT ?"
    params.append(limit)
    return [dict(r) for r in connection.execute(sql, params).fetchall()]


def list_batches(connection: sqlite3.Connection, user: dict | None = None) -> list[dict]:
    scoped = facility_scope_for_user(user)
    sql = """
        SELECT b.*, origin.name AS origin_name, dest.name AS destination_name, v.storage_temp_min, v.storage_temp_max
        FROM batches b
        JOIN facilities origin ON origin.id = b.origin_facility_id
        JOIN facilities dest ON dest.id = b.destination_facility_id
        LEFT JOIN vaccines v ON v.id = b.vaccine_id
    """
    params: list = []
    if scoped:
        sql += " WHERE b.origin_facility_id = ? OR b.destination_facility_id = ?"
        params.extend([scoped, scoped])
    sql += " ORDER BY b.id"
    return [dict(r) for r in connection.execute(sql, params).fetchall()]


def list_transit_locations(connection: sqlite3.Connection, user: dict | None = None) -> list[dict]:
    scoped = facility_scope_for_user(user)
    sql = """
        SELECT t.device_id, t.facility_id, t.batch_id, t.recorded_at, t.temperature_c,
               t.latitude, t.longitude, t.transport_mode
        FROM telemetry t
        WHERE t.transport_mode = 'transit'
          AND t.id IN (SELECT MAX(id) FROM telemetry WHERE transport_mode = 'transit' GROUP BY device_id)
    """
    params: list = []
    if scoped:
        sql += " AND t.facility_id = ?"
        params.append(scoped)
    return [dict(r) for r in connection.execute(sql, params).fetchall()]


def list_dc_events(connection: sqlite3.Connection, limit: int = 30) -> list[dict]:
    rows = connection.execute(
        "SELECT * FROM dc_events ORDER BY occurred_at DESC LIMIT ?", (limit,)
    ).fetchall()
    return [dict(r) for r in rows]


def list_vaccines(connection: sqlite3.Connection) -> list[dict]:
    return [dict(r) for r in connection.execute("SELECT * FROM vaccines ORDER BY name").fetchall()]


def list_gateways(connection: sqlite3.Connection) -> list[dict]:
    return [dict(r) for r in connection.execute(
        "SELECT g.*, f.name AS facility_name FROM gateways g JOIN facilities f ON f.id = g.facility_id ORDER BY g.id"
    ).fetchall()]


def build_analytics(connection: sqlite3.Connection, user: dict | None = None) -> dict:
    scoped = facility_scope_for_user(user)
    where = "WHERE facility_id = ?" if scoped else ""
    p = [scoped] if scoped else []

    totals = connection.execute(
        f"SELECT COUNT(*) AS packets, SUM(CASE WHEN temperature_c BETWEEN 2 AND 8 THEN 1 ELSE 0 END) AS compliant_packets, AVG(temperature_c) AS avg_temp, AVG(battery_voltage) AS avg_battery FROM telemetry {where}",
        p,
    ).fetchone()
    incident_totals = connection.execute(
        "SELECT COUNT(*) AS incident_count, SUM(CASE WHEN status='open' THEN 1 ELSE 0 END) AS open_incidents, SUM(CASE WHEN incident_type='temperature_excursion' THEN 1 ELSE 0 END) AS excursions, SUM(CASE WHEN incident_type='low_battery' THEN 1 ELSE 0 END) AS battery_events FROM incidents" + (" WHERE facility_id = ?" if scoped else ""),
        p,
    ).fetchone()

    facility_sql = """
        SELECT t.facility_id, f.name AS facility_name,
               ROUND(AVG(t.temperature_c),2) AS avg_temp_c,
               ROUND(MIN(t.battery_voltage),2) AS lowest_battery_v,
               SUM(CASE WHEN t.temperature_c<2 OR t.temperature_c>8 THEN 1 ELSE 0 END) AS excursions
        FROM telemetry t JOIN facilities f ON f.id = t.facility_id
    """
    fp: list = []
    if scoped:
        facility_sql += " WHERE t.facility_id = ?"
        fp.append(scoped)
    facility_sql += " GROUP BY t.facility_id, f.name ORDER BY excursions DESC"
    facility_performance = [dict(r) for r in connection.execute(facility_sql, fp).fetchall()]

    recent_points_sql = "SELECT device_id, recorded_at, temperature_c, battery_voltage, rolling_avg_c, trend_slope FROM telemetry"
    rp: list = []
    if scoped:
        recent_points_sql += " WHERE facility_id = ?"
        rp.append(scoped)
    recent_points_sql += " ORDER BY recorded_at DESC LIMIT 20"
    recent_points = [dict(r) for r in connection.execute(recent_points_sql, rp).fetchall()]

    delivery_sql = "SELECT n.channel, n.status, n.provider, COUNT(*) AS total FROM notifications n JOIN incidents i ON i.id = n.incident_id"
    dp: list = []
    if scoped:
        delivery_sql += " WHERE i.facility_id = ?"
        dp.append(scoped)
    delivery_sql += " GROUP BY n.channel, n.status, n.provider ORDER BY total DESC"
    delivery_channels = [dict(r) for r in connection.execute(delivery_sql, dp).fetchall()]

    packet_total = totals["packets"] or 0
    compliant = totals["compliant_packets"] or 0
    compliance_rate = round((compliant / packet_total) * 100, 2) if packet_total else 0.0

    return {
        "kpis": {
            "compliance_rate_pct": compliance_rate,
            "packets": packet_total,
            "incident_count": incident_totals["incident_count"] or 0,
            "open_incidents": incident_totals["open_incidents"] or 0,
            "excursions": incident_totals["excursions"] or 0,
            "battery_events": incident_totals["battery_events"] or 0,
            "average_temperature_c": round(totals["avg_temp"], 2) if totals["avg_temp"] else None,
            "average_battery_v": round(totals["avg_battery"], 2) if totals["avg_battery"] else None,
        },
        "facility_performance": facility_performance,
        "recent_points": recent_points,
        "delivery_channels": delivery_channels,
        "transit_locations": list_transit_locations(connection, user=user),
    }


def build_summary_export_rows(connection: sqlite3.Connection, user: dict | None = None) -> list[dict]:
    overview = build_overview(connection, user=user)
    analytics = build_analytics(connection, user=user)
    rows = []
    for label, value in overview["summary"].items():
        rows.append({"section": "overview", "metric": label, "value": value})
    for label, value in analytics["kpis"].items():
        rows.append({"section": "analytics", "metric": label, "value": value})
    return rows


def build_incident_export_rows(connection: sqlite3.Connection, user: dict | None = None) -> list[dict]:
    return [
        {
            "incident_id": i["id"], "facility_id": i["facility_id"], "facility_name": i["facility_name"],
            "device_id": i["device_id"], "batch_id": i["batch_id"], "incident_type": i["incident_type"],
            "severity": i["severity"], "status": i["status"], "reason": i["reason"],
            "opened_at": i["opened_at"], "resolved_at": i["resolved_at"],
            "latest_temperature_c": i["latest_temperature_c"], "battery_voltage": i["battery_voltage"],
        }
        for i in list_incidents(connection, limit=500, user=user)
    ]
