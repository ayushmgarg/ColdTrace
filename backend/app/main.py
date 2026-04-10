from __future__ import annotations

import csv
import io
from pathlib import Path

from fastapi import Depends, FastAPI, HTTPException, Query, Request, status
from fastapi.responses import HTMLResponse, PlainTextResponse, Response
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from .auth import (
    ROLE_ADMIN,
    ROLE_MANAGER,
    ROLE_SUPERVISOR,
    ROLE_VACCINATOR,
    authenticate_user,
    create_access_token,
    fetch_user_by_id,
    require_roles,
    seed_default_users,
)
from .config import settings
from .database import get_connection, get_db_path, init_db
from .schemas import LoginRequest, TelemetryIn
from .services import (
    build_analytics,
    build_incident_export_rows,
    build_overview,
    build_summary_export_rows,
    create_audit_entry,
    insert_telemetry,
    list_batches,
    list_incidents,
    list_notifications,
    list_recent_telemetry,
    list_transit_locations,
    now_iso,
    seed_reference_data,
)


app = FastAPI(
    title=settings.app_name,
    version="0.2.0",
    summary="Distributed vaccine cold chain monitoring platform.",
)

BASE_DIR = Path(__file__).resolve().parent
templates = Jinja2Templates(directory=str(BASE_DIR / "templates"))
app.mount("/static", StaticFiles(directory=str(BASE_DIR / "static")), name="static")


def make_csv_response(rows: list[dict], filename: str) -> Response:
    buffer = io.StringIO()
    if rows:
        writer = csv.DictWriter(buffer, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        writer.writerows(rows)
    else:
        buffer.write("no_data\n")
    return Response(
        content=buffer.getvalue(),
        media_type="text/csv",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@app.on_event("startup")
def startup() -> None:
    init_db()
    connection = get_connection()
    try:
        seed_reference_data(connection)
        seed_default_users(connection)
        connection.commit()
    finally:
        connection.close()


@app.get("/", response_class=HTMLResponse)
def dashboard(request: Request) -> HTMLResponse:
    return templates.TemplateResponse(
        request=request,
        name="index.html",
        context={"generated_at": now_iso(), "app_name": settings.app_name, "tagline": settings.tagline},
    )


@app.get("/login", response_class=HTMLResponse)
def login_page(request: Request) -> HTMLResponse:
    return templates.TemplateResponse(
        request=request,
        name="login.html",
        context={"app_name": settings.app_name, "tagline": settings.tagline},
    )


@app.get("/operator", response_class=HTMLResponse)
def operator_page(request: Request) -> HTMLResponse:
    return templates.TemplateResponse(
        request=request,
        name="operator.html",
        context={"generated_at": now_iso(), "app_name": settings.app_name},
    )


@app.get("/reports/executive", response_class=HTMLResponse)
def executive_report_page(request: Request) -> HTMLResponse:
    return templates.TemplateResponse(
        request=request,
        name="report.html",
        context={"generated_at": now_iso(), "app_name": settings.app_name},
    )


@app.get("/health")
def health() -> dict:
    return {"status": "ok", "database": str(get_db_path()), "service": settings.app_name}


@app.get("/api/public/config")
def public_config() -> dict:
    return {
        "app_name": settings.app_name,
        "tagline": settings.tagline,
        "auth_provider": settings.auth_provider,
        "mapbox_access_token": settings.mapbox_access_token,
        "mapbox_style": settings.mapbox_style,
        "has_mapbox": settings.has_mapbox,
        "has_sms": settings.has_sms,
        "has_email": settings.has_email,
    }


@app.post("/api/auth/login")
def login(payload: LoginRequest) -> dict:
    connection = get_connection()
    try:
        user = authenticate_user(connection, payload.email, payload.password)
        if not user:
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid credentials")
        access_token = create_access_token(user)
        create_audit_entry(connection, "auth", user["id"], "login", {"email": user["email"]})
        connection.commit()
        return {
            "access_token": access_token,
            "token_type": "bearer",
            "user": {
                "id": user["id"],
                "full_name": user["full_name"],
                "email": user["email"],
                "role": user["role"],
                "assigned_facility_id": user["assigned_facility_id"],
            },
        }
    finally:
        connection.close()


@app.get("/api/auth/me")
def auth_me(payload: dict = Depends(require_roles(ROLE_ADMIN, ROLE_MANAGER, ROLE_SUPERVISOR, ROLE_VACCINATOR))) -> dict:
    connection = get_connection()
    try:
        user = fetch_user_by_id(connection, payload["sub"])
        if not user:
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="User not found")
        return user
    finally:
        connection.close()


@app.post("/api/telemetry")
def ingest_telemetry(payload: TelemetryIn) -> dict:
    connection = get_connection()
    try:
        return insert_telemetry(connection, payload)
    finally:
        connection.close()


@app.get("/api/overview")
def overview(payload: dict = Depends(require_roles(ROLE_ADMIN, ROLE_MANAGER, ROLE_SUPERVISOR, ROLE_VACCINATOR))) -> dict:
    connection = get_connection()
    try:
        return build_overview(connection, user=payload)
    finally:
        connection.close()


@app.get("/api/telemetry/recent")
def recent_telemetry(
    limit: int = Query(default=20, ge=1, le=100),
    payload: dict = Depends(require_roles(ROLE_ADMIN, ROLE_MANAGER, ROLE_SUPERVISOR, ROLE_VACCINATOR)),
) -> list[dict]:
    connection = get_connection()
    try:
        return list_recent_telemetry(connection, limit=limit, user=payload)
    finally:
        connection.close()


@app.get("/api/incidents")
def incidents(
    limit: int = Query(default=20, ge=1, le=100),
    payload: dict = Depends(require_roles(ROLE_ADMIN, ROLE_MANAGER, ROLE_SUPERVISOR, ROLE_VACCINATOR)),
) -> list[dict]:
    connection = get_connection()
    try:
        return list_incidents(connection, limit=limit, user=payload)
    finally:
        connection.close()


@app.get("/api/notifications")
def notifications(
    limit: int = Query(default=25, ge=1, le=100),
    payload: dict = Depends(require_roles(ROLE_ADMIN, ROLE_MANAGER, ROLE_SUPERVISOR, ROLE_VACCINATOR)),
) -> list[dict]:
    connection = get_connection()
    try:
        return list_notifications(connection, limit=limit, user=payload)
    finally:
        connection.close()


@app.get("/api/batches")
def batches(payload: dict = Depends(require_roles(ROLE_ADMIN, ROLE_MANAGER, ROLE_SUPERVISOR, ROLE_VACCINATOR))) -> list[dict]:
    connection = get_connection()
    try:
        return list_batches(connection, user=payload)
    finally:
        connection.close()


@app.get("/api/transit/latest")
def transit_latest(payload: dict = Depends(require_roles(ROLE_ADMIN, ROLE_MANAGER, ROLE_SUPERVISOR, ROLE_VACCINATOR))) -> list[dict]:
    connection = get_connection()
    try:
        return list_transit_locations(connection, user=payload)
    finally:
        connection.close()


@app.get("/api/reports/analytics")
def report_analytics(payload: dict = Depends(require_roles(ROLE_ADMIN, ROLE_MANAGER, ROLE_SUPERVISOR, ROLE_VACCINATOR))) -> dict:
    connection = get_connection()
    try:
        return build_analytics(connection, user=payload)
    finally:
        connection.close()


@app.get("/api/reports/export/summary.csv")
def export_summary_csv(payload: dict = Depends(require_roles(ROLE_ADMIN, ROLE_MANAGER, ROLE_SUPERVISOR))) -> Response:
    connection = get_connection()
    try:
        rows = build_summary_export_rows(connection, user=payload)
        return make_csv_response(rows, "coldtrace-summary.csv")
    finally:
        connection.close()


@app.get("/api/reports/export/incidents.csv")
def export_incidents_csv(payload: dict = Depends(require_roles(ROLE_ADMIN, ROLE_MANAGER, ROLE_SUPERVISOR))) -> Response:
    connection = get_connection()
    try:
        rows = build_incident_export_rows(connection, user=payload)
        return make_csv_response(rows, "coldtrace-incidents.csv")
    finally:
        connection.close()


@app.get("/robots.txt", response_class=PlainTextResponse)
def robots() -> str:
    return "User-agent: *\nDisallow:\n"
