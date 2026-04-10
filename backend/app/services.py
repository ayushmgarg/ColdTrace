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


def seed_reference_data(connection: sqlite3.Connection) -> None:
    facility_count = connection.execute("SELECT COUNT(*) FROM facilities").fetchone()[0]
    if facility_count:
        return

    facilities = [
        ("FAC-MUM-HUB", "Mumbai Regional Cold Hub", "regional_hub", "Mumbai", "healthy"),
        ("FAC-PUNE-TRANSIT", "Pune Transit Vehicle Dock", "transit", "Pune", "healthy"),
        ("FAC-NASHIK-CLINIC", "Nashik Outreach Clinic", "clinic", "Nashik", "watch"),
    ]
    devices = [
        ("LTAT-MUM-01", "FAC-MUM-HUB", "IGD-MUM-01", "cold_room", "active", 2.0, 8.0, None),
        ("LTAT-PUNE-TRUCK-01", "FAC-PUNE-TRANSIT", "IGD-PUNE-01", "vehicle", "active", 2.0, 8.0, None),
        ("LTAT-NASHIK-01", "FAC-NASHIK-CLINIC", "IGD-NASHIK-01", "portable_carrier", "active", 2.0, 8.0, None),
    ]
    batches = [
        ("BATCH-CVX-001", "Covishield", "SII", "FAC-MUM-HUB", "FAC-NASHIK-CLINIC", "in_transit", 1200),
        ("BATCH-CVX-002", "Covaxin", "Bharat Biotech", "FAC-MUM-HUB", "FAC-PUNE-TRANSIT", "stored", 800),
    ]

    connection.executemany(
        "INSERT INTO facilities (id, name, facility_type, region, status) VALUES (?, ?, ?, ?, ?)",
        facilities,
    )
    connection.executemany(
        """
        INSERT INTO devices (
            id, facility_id, gateway_id, device_type, status, min_temp_c, max_temp_c, last_seen_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """,
        devices,
    )
    connection.executemany(
        """
        INSERT INTO batches (
            id, vaccine_name, manufacturer, origin_facility_id, destination_facility_id, status, doses_total
        ) VALUES (?, ?, ?, ?, ?, ?, ?)
        """,
        batches,
    )
    create_audit_entry(
        connection,
        "system",
        "bootstrap",
        "seed_reference_data",
        {"facilities": len(facilities), "devices": len(devices), "batches": len(batches)},
    )


def compute_trend_slope(values: list[float]) -> float:
    n = len(values)
    xs = list(range(n))
    x_mean = sum(xs) / n
    y_mean = sum(values) / n
    numerator = sum((x - x_mean) * (y - y_mean) for x, y in zip(xs, values, strict=False))
    denominator = sum((x - x_mean) ** 2 for x in xs) or 1
    return numerator / denominator


def close_open_incidents(
    connection: sqlite3.Connection,
    device_id: str,
    batch_id: str,
    resolved_at: str,
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
    connection: sqlite3.Connection,
    incident_id: str,
    reading: TelemetryIn,
    issue: dict,
) -> list[dict]:
    recipients = get_notification_targets(connection, reading.facility_id)
    created = []
    sms_text = (
        f"[{settings.app_name}] {issue['incident_type']} at {reading.facility_id} "
        f"for {reading.device_id}: {issue['reason']} at {reading.recorded_at}"
    )
    email_subject = f"{settings.app_name}: {issue['incident_type'].replace('_', ' ').title()}"
    email_text = (
        f"Facility: {reading.facility_id}\n"
        f"Device: {reading.device_id}\n"
        f"Batch: {reading.batch_id}\n"
        f"Temperature: {reading.temperature_c:.2f} C\n"
        f"Battery: {reading.battery_voltage:.2f} V\n"
        f"Reason: {issue['reason']}\n"
        f"Recorded at: {reading.recorded_at}\n"
    )
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
            notification_id = f"NTF-{uuid.uuid4().hex[:8].upper()}"
            connection.execute(
                """
                INSERT INTO notifications (
                    id, incident_id, channel, recipient, payload, status, sent_at, provider,
                    provider_message_id, error_message
                ) VALUES (?, ?, 'sms', ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    notification_id,
                    incident_id,
                    recipient["phone_number"],
                    json.dumps({"user_id": recipient["id"], "body": sms_text}, sort_keys=True),
                    sms_result["status"],
                    now_iso(),
                    sms_result.get("provider", "simulation"),
                    sms_result.get("provider_message_id", ""),
                    "" if sms_result["status"] != "failed" else sms_result.get("message", ""),
                ),
            )
            created.append(
                {
                    "notification_id": notification_id,
                    "channel": "sms",
                    "recipient": recipient["phone_number"],
                    "status": sms_result["status"],
                }
            )

        if recipient.get("email"):
            email_result = send_email(recipient["email"], email_subject, email_html, email_text)
            notification_id = f"NTF-{uuid.uuid4().hex[:8].upper()}"
            connection.execute(
                """
                INSERT INTO notifications (
                    id, incident_id, channel, recipient, payload, status, sent_at, provider,
                    provider_message_id, error_message
                ) VALUES (?, ?, 'email', ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    notification_id,
                    incident_id,
                    recipient["email"],
                    json.dumps({"user_id": recipient["id"], "subject": email_subject}, sort_keys=True),
                    email_result["status"],
                    now_iso(),
                    email_result.get("provider", "simulation"),
                    email_result.get("provider_message_id", ""),
                    "" if email_result["status"] != "failed" else email_result.get("message", ""),
                ),
            )
            created.append(
                {
                    "notification_id": notification_id,
                    "channel": "email",
                    "recipient": recipient["email"],
                    "status": email_result["status"],
                }
            )

    return created


def open_or_update_incident(connection: sqlite3.Connection, reading: TelemetryIn, issue: dict) -> dict:
    open_incident = connection.execute(
        """
        SELECT * FROM incidents
        WHERE device_id = ? AND batch_id = ? AND incident_type = ? AND status = 'open'
        ORDER BY opened_at DESC
        LIMIT 1
        """,
        (reading.device_id, reading.batch_id, issue["incident_type"]),
    ).fetchone()

    if open_incident:
        connection.execute(
            """
            UPDATE incidents
            SET latest_temperature_c = ?, battery_voltage = ?,
                min_temperature_c = MIN(min_temperature_c, ?),
                max_temperature_c = MAX(max_temperature_c, ?),
                severity = ?
            WHERE id = ?
            """,
            (
                reading.temperature_c,
                reading.battery_voltage,
                reading.temperature_c,
                reading.temperature_c,
                issue["severity"],
                open_incident["id"],
            ),
        )
        create_audit_entry(
            connection,
            "incident",
            open_incident["id"],
            "updated",
            {"packet_id": reading.packet_id, "severity": issue["severity"], "reason": issue["reason"]},
        )
        return {"incident_id": open_incident["id"], "status": "updated", **issue}

    incident_id = f"INC-{uuid.uuid4().hex[:8].upper()}"
    connection.execute(
        """
        INSERT INTO incidents (
            id, device_id, batch_id, facility_id, incident_type, severity, status, reason, opened_at,
            resolved_at, latest_temperature_c, min_temperature_c, max_temperature_c, battery_voltage
        ) VALUES (?, ?, ?, ?, ?, ?, 'open', ?, ?, NULL, ?, ?, ?, ?)
        """,
        (
            incident_id,
            reading.device_id,
            reading.batch_id,
            reading.facility_id,
            issue["incident_type"],
            issue["severity"],
            issue["reason"],
            reading.recorded_at,
            reading.temperature_c,
            reading.temperature_c,
            reading.temperature_c,
            reading.battery_voltage,
        ),
    )
    notifications = create_notifications(connection, incident_id, reading, issue)
    create_audit_entry(
        connection,
        "incident",
        incident_id,
        "opened",
        {"packet_id": reading.packet_id, "issue": issue, "notifications_created": len(notifications)},
    )
    return {"incident_id": incident_id, "status": "opened", "notifications": notifications, **issue}


def evaluate_reading(connection: sqlite3.Connection, reading: TelemetryIn) -> dict:
    device = connection.execute(
        "SELECT min_temp_c, max_temp_c FROM devices WHERE id = ?",
        (reading.device_id,),
    ).fetchone()
    window_start = (parse_iso(reading.recorded_at) - timedelta(minutes=30)).isoformat()
    history = connection.execute(
        """
        SELECT recorded_at, temperature_c
        FROM telemetry
        WHERE device_id = ? AND recorded_at >= ?
        ORDER BY recorded_at ASC
        """,
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
        existing = connection.execute(
            "SELECT id FROM telemetry WHERE packet_id = ?",
            (reading.packet_id,),
        ).fetchone()
        if existing:
            return {"status": "duplicate", "packet_id": reading.packet_id}

        connection.execute(
            """
            INSERT INTO telemetry (
                packet_id, device_id, gateway_id, facility_id, batch_id, recorded_at, temperature_c,
                humidity_pct, battery_voltage, latitude, longitude, transport_mode, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                reading.packet_id,
                reading.device_id,
                reading.gateway_id,
                reading.facility_id,
                reading.batch_id,
                reading.recorded_at,
                reading.temperature_c,
                reading.humidity_pct,
                reading.battery_voltage,
                reading.latitude,
                reading.longitude,
                reading.transport_mode,
                now_iso(),
            ),
        )
        connection.execute(
            "UPDATE devices SET last_seen_at = ?, status = 'active' WHERE id = ?",
            (reading.recorded_at, reading.device_id),
        )
        create_audit_entry(connection, "telemetry", reading.packet_id, "ingested", reading.model_dump())
        incident = evaluate_reading(connection, reading)
        connection.commit()
        return {"status": "ingested", "packet_id": reading.packet_id, "incident": incident}


def build_overview(connection: sqlite3.Connection, user: dict | None = None) -> dict:
    scoped_facility = facility_scope_for_user(user)
    params: list[str] = []
    telemetry_filter = ""
    incident_filter = ""
    if scoped_facility:
        telemetry_filter = " WHERE facility_id = ?"
        incident_filter = " WHERE facility_id = ?"
        params = [scoped_facility]

    active_incidents = connection.execute(
        f"SELECT COUNT(*) FROM incidents{incident_filter} AND status = 'open'" if incident_filter else
        "SELECT COUNT(*) FROM incidents WHERE status = 'open'",
        params,
    ).fetchone()[0]
    telemetry_total = connection.execute(
        f"SELECT COUNT(*) FROM telemetry{telemetry_filter}",
        params,
    ).fetchone()[0]
    low_battery_sql = """
        SELECT COUNT(*) FROM (
            SELECT device_id, MAX(recorded_at) AS latest_at
            FROM telemetry
            {where_clause}
            GROUP BY device_id
        ) latest
        JOIN telemetry t ON t.device_id = latest.device_id AND t.recorded_at = latest.latest_at
        WHERE t.battery_voltage < 2.1
    """
    where_clause = "WHERE facility_id = ?" if scoped_facility else ""
    low_battery_nodes = connection.execute(
        low_battery_sql.format(where_clause=where_clause),
        params,
    ).fetchone()[0]

    facilities_sql = (
        "SELECT COUNT(DISTINCT facility_id) FROM telemetry WHERE facility_id = ?"
        if scoped_facility else
        "SELECT COUNT(*) FROM facilities"
    )
    facilities = connection.execute(facilities_sql, params).fetchone()[0]

    latest_temp_sql = """
        SELECT device_id, temperature_c
        FROM telemetry
        WHERE id IN (SELECT MAX(id) FROM telemetry GROUP BY device_id)
    """
    latest_params: list[str] = []
    if scoped_facility:
        latest_temp_sql = """
            SELECT device_id, temperature_c
            FROM telemetry
            WHERE facility_id = ? AND id IN (
                SELECT MAX(id) FROM telemetry WHERE facility_id = ? GROUP BY device_id
            )
        """
        latest_params = [scoped_facility, scoped_facility]
    latest_temps = [row["temperature_c"] for row in connection.execute(latest_temp_sql, latest_params).fetchall()]
    average_temp = round(sum(latest_temps) / len(latest_temps), 2) if latest_temps else None

    facility_health_sql = """
        SELECT f.id, f.name, f.status, f.region, COUNT(d.id) AS device_count
        FROM facilities f
        LEFT JOIN devices d ON d.facility_id = f.id
        {where_clause}
        GROUP BY f.id, f.name, f.status, f.region
        ORDER BY f.name
    """
    facility_where = "WHERE f.id = ?" if scoped_facility else ""
    facility_health = [
        dict(row)
        for row in connection.execute(facility_health_sql.format(where_clause=facility_where), params).fetchall()
    ]

    incident_mix_sql = "SELECT incident_type FROM incidents WHERE status = 'open'"
    incident_params: list[str] = []
    if scoped_facility:
        incident_mix_sql += " AND facility_id = ?"
        incident_params = [scoped_facility]
    incident_mix = Counter(row["incident_type"] for row in connection.execute(incident_mix_sql, incident_params).fetchall())

    transit_assets = connection.execute(
        """
        SELECT COUNT(DISTINCT device_id)
        FROM telemetry
        WHERE transport_mode = 'transit'
        """ + (" AND facility_id = ?" if scoped_facility else ""),
        [scoped_facility] if scoped_facility else [],
    ).fetchone()[0]

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
        "incident_mix": incident_mix,
    }


def list_recent_telemetry(
    connection: sqlite3.Connection,
    limit: int = 20,
    user: dict | None = None,
) -> list[dict]:
    scoped_facility = facility_scope_for_user(user)
    sql = """
        SELECT t.packet_id, t.device_id, t.gateway_id, t.facility_id, t.batch_id, t.recorded_at,
               t.temperature_c, t.humidity_pct, t.battery_voltage, t.latitude, t.longitude,
               t.transport_mode, d.min_temp_c, d.max_temp_c
        FROM telemetry t
        JOIN devices d ON d.id = t.device_id
    """
    params: list[object] = []
    if scoped_facility:
        sql += " WHERE t.facility_id = ?"
        params.append(scoped_facility)
    sql += " ORDER BY t.recorded_at DESC, t.id DESC LIMIT ?"
    params.append(limit)
    return [dict(row) for row in connection.execute(sql, params).fetchall()]


def list_incidents(
    connection: sqlite3.Connection,
    limit: int = 20,
    user: dict | None = None,
) -> list[dict]:
    scoped_facility = facility_scope_for_user(user)
    sql = """
        SELECT i.*, f.name AS facility_name
        FROM incidents i
        JOIN facilities f ON f.id = i.facility_id
    """
    params: list[object] = []
    if scoped_facility:
        sql += " WHERE i.facility_id = ?"
        params.append(scoped_facility)
    sql += " ORDER BY i.opened_at DESC LIMIT ?"
    params.append(limit)
    return [dict(row) for row in connection.execute(sql, params).fetchall()]


def list_notifications(
    connection: sqlite3.Connection,
    limit: int = 25,
    user: dict | None = None,
) -> list[dict]:
    scoped_facility = facility_scope_for_user(user)
    sql = """
        SELECT n.*, i.incident_type, i.severity, i.facility_id
        FROM notifications n
        JOIN incidents i ON i.id = n.incident_id
    """
    params: list[object] = []
    if scoped_facility:
        sql += " WHERE i.facility_id = ?"
        params.append(scoped_facility)
    sql += " ORDER BY n.sent_at DESC LIMIT ?"
    params.append(limit)
    return [dict(row) for row in connection.execute(sql, params).fetchall()]


def list_batches(connection: sqlite3.Connection, user: dict | None = None) -> list[dict]:
    scoped_facility = facility_scope_for_user(user)
    sql = """
        SELECT b.*,
               origin.name AS origin_name,
               destination.name AS destination_name
        FROM batches b
        JOIN facilities origin ON origin.id = b.origin_facility_id
        JOIN facilities destination ON destination.id = b.destination_facility_id
    """
    params: list[object] = []
    if scoped_facility:
        sql += " WHERE b.origin_facility_id = ? OR b.destination_facility_id = ?"
        params.extend([scoped_facility, scoped_facility])
    sql += " ORDER BY b.id"
    return [dict(row) for row in connection.execute(sql, params).fetchall()]


def list_transit_locations(connection: sqlite3.Connection, user: dict | None = None) -> list[dict]:
    scoped_facility = facility_scope_for_user(user)
    sql = """
        SELECT t.device_id, t.facility_id, t.batch_id, t.recorded_at, t.temperature_c,
               t.latitude, t.longitude, t.transport_mode
        FROM telemetry t
        WHERE t.transport_mode = 'transit'
          AND t.id IN (
              SELECT MAX(id) FROM telemetry WHERE transport_mode = 'transit' GROUP BY device_id
          )
    """
    params: list[object] = []
    if scoped_facility:
        sql += " AND t.facility_id = ?"
        params.append(scoped_facility)
    sql += " ORDER BY t.recorded_at DESC"
    return [dict(row) for row in connection.execute(sql, params).fetchall()]


def build_analytics(connection: sqlite3.Connection, user: dict | None = None) -> dict:
    scoped_facility = facility_scope_for_user(user)
    telemetry_where = "WHERE facility_id = ?" if scoped_facility else ""
    incident_where = "WHERE facility_id = ?" if scoped_facility else ""
    params = [scoped_facility] if scoped_facility else []

    totals = connection.execute(
        f"""
        SELECT
            COUNT(*) AS packets,
            SUM(CASE WHEN temperature_c BETWEEN 2 AND 8 THEN 1 ELSE 0 END) AS compliant_packets,
            AVG(temperature_c) AS avg_temp,
            AVG(battery_voltage) AS avg_battery
        FROM telemetry
        {telemetry_where}
        """,
        params,
    ).fetchone()

    incident_totals = connection.execute(
        f"""
        SELECT
            COUNT(*) AS incident_count,
            SUM(CASE WHEN status = 'open' THEN 1 ELSE 0 END) AS open_incidents,
            SUM(CASE WHEN incident_type = 'temperature_excursion' THEN 1 ELSE 0 END) AS excursions,
            SUM(CASE WHEN incident_type = 'low_battery' THEN 1 ELSE 0 END) AS battery_events
        FROM incidents
        {incident_where}
        """,
        params,
    ).fetchone()

    facility_sql = """
        SELECT t.facility_id,
               f.name AS facility_name,
               ROUND(AVG(t.temperature_c), 2) AS avg_temp_c,
               ROUND(MIN(t.battery_voltage), 2) AS lowest_battery_v,
               SUM(CASE WHEN t.temperature_c < 2 OR t.temperature_c > 8 THEN 1 ELSE 0 END) AS excursions
        FROM telemetry t
        JOIN facilities f ON f.id = t.facility_id
    """
    facility_params: list[object] = []
    if scoped_facility:
        facility_sql += " WHERE t.facility_id = ?"
        facility_params.append(scoped_facility)
    facility_sql += " GROUP BY t.facility_id, f.name ORDER BY excursions DESC, avg_temp_c DESC"
    facility_performance = [dict(row) for row in connection.execute(facility_sql, facility_params).fetchall()]

    recent_points_sql = """
        SELECT device_id, recorded_at, temperature_c, battery_voltage
        FROM telemetry
    """
    recent_params: list[object] = []
    if scoped_facility:
        recent_points_sql += " WHERE facility_id = ?"
        recent_params.append(scoped_facility)
    recent_points_sql += " ORDER BY recorded_at DESC LIMIT 20"
    recent_points = [dict(row) for row in connection.execute(recent_points_sql, recent_params).fetchall()]

    delivery_sql = """
        SELECT n.channel, n.status, n.provider, COUNT(*) AS total
        FROM notifications n
        JOIN incidents i ON i.id = n.incident_id
    """
    delivery_params: list[object] = []
    if scoped_facility:
        delivery_sql += " WHERE i.facility_id = ?"
        delivery_params.append(scoped_facility)
    delivery_sql += " GROUP BY n.channel, n.status, n.provider ORDER BY total DESC"
    delivery_channels = [dict(row) for row in connection.execute(delivery_sql, delivery_params).fetchall()]

    compliant_packets = totals["compliant_packets"] or 0
    packet_total = totals["packets"] or 0
    compliance_rate = round((compliant_packets / packet_total) * 100, 2) if packet_total else 0.0

    return {
        "kpis": {
            "compliance_rate_pct": compliance_rate,
            "packets": packet_total,
            "incident_count": incident_totals["incident_count"] or 0,
            "open_incidents": incident_totals["open_incidents"] or 0,
            "excursions": incident_totals["excursions"] or 0,
            "battery_events": incident_totals["battery_events"] or 0,
            "average_temperature_c": round(totals["avg_temp"], 2) if totals["avg_temp"] is not None else None,
            "average_battery_v": round(totals["avg_battery"], 2) if totals["avg_battery"] is not None else None,
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
    incidents = list_incidents(connection, limit=500, user=user)
    return [
        {
            "incident_id": item["id"],
            "facility_id": item["facility_id"],
            "facility_name": item["facility_name"],
            "device_id": item["device_id"],
            "batch_id": item["batch_id"],
            "incident_type": item["incident_type"],
            "severity": item["severity"],
            "status": item["status"],
            "reason": item["reason"],
            "opened_at": item["opened_at"],
            "resolved_at": item["resolved_at"],
            "latest_temperature_c": item["latest_temperature_c"],
            "battery_voltage": item["battery_voltage"],
        }
        for item in incidents
    ]
