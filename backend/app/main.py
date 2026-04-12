from __future__ import annotations
import csv, io
from pathlib import Path
from fastapi import Depends, FastAPI, HTTPException, Query, Request, status
from fastapi.responses import HTMLResponse, PlainTextResponse, Response
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from .auth import (ROLE_ADMIN, ROLE_MANAGER, ROLE_SUPERVISOR, ROLE_VACCINATOR,
                   authenticate_user, create_access_token, fetch_user_by_id,
                   require_roles, seed_default_users)
from .config import settings
from .database import get_connection, get_db_path, init_db
from .schemas import LoginRequest, TelemetryIn
from .services import (build_analytics, build_incident_export_rows, build_overview,
                       build_summary_export_rows, create_audit_entry, insert_telemetry,
                       list_batches, list_dc_events, list_gateways, list_incidents,
                       list_notifications, list_recent_telemetry, list_transit_locations,
                       list_vaccines, now_iso, seed_reference_data)

app = FastAPI(title=settings.app_name, version="0.3.0",
              summary="Distributed vaccine cold chain monitoring platform.")

BASE_DIR = Path(__file__).resolve().parent
templates = Jinja2Templates(directory=str(BASE_DIR / "templates"))
app.mount("/static", StaticFiles(directory=str(BASE_DIR / "static")), name="static")

AUTH_ALL = Depends(require_roles(ROLE_ADMIN, ROLE_MANAGER, ROLE_SUPERVISOR, ROLE_VACCINATOR))
AUTH_MGR  = Depends(require_roles(ROLE_ADMIN, ROLE_MANAGER, ROLE_SUPERVISOR))

def make_csv_response(rows, filename):
    buf = io.StringIO()
    if rows:
        w = csv.DictWriter(buf, fieldnames=list(rows[0].keys()))
        w.writeheader(); w.writerows(rows)
    else:
        buf.write("no_data\n")
    return Response(content=buf.getvalue(), media_type="text/csv",
                    headers={"Content-Disposition": f'attachment; filename="{filename}"'})

@app.on_event("startup")
def startup():
    init_db()
    con = get_connection()
    try:
        seed_reference_data(con)
        seed_default_users(con)
        con.commit()
    finally:
        con.close()

# ── Page routes ────────────────────────────────────────────────
@app.get("/",              response_class=HTMLResponse)
def dashboard(request: Request):
    return templates.TemplateResponse(request=request, name="index.html",
        context={"generated_at": now_iso(), "app_name": settings.app_name, "tagline": settings.tagline})

@app.get("/login",         response_class=HTMLResponse)
def login_page(request: Request):
    return templates.TemplateResponse(request=request, name="login.html",
        context={"app_name": settings.app_name, "tagline": settings.tagline})

@app.get("/operator",      response_class=HTMLResponse)
def operator_page(request: Request):
    return templates.TemplateResponse(request=request, name="operator.html",
        context={"generated_at": now_iso(), "app_name": settings.app_name})

@app.get("/reports/executive", response_class=HTMLResponse)
def report_page(request: Request):
    return templates.TemplateResponse(request=request, name="report.html",
        context={"generated_at": now_iso(), "app_name": settings.app_name})

# ── Public ────────────────────────────────────────────────────
@app.get("/health")
def health():
    return {"status": "ok", "database": str(get_db_path()), "service": settings.app_name}

@app.get("/api/public/config")
def public_config():
    return {"app_name": settings.app_name, "tagline": settings.tagline,
            "auth_provider": settings.auth_provider,
            "mapbox_access_token": settings.mapbox_access_token,
            "mapbox_style": settings.mapbox_style,
            "has_mapbox": settings.has_mapbox, "has_sms": settings.has_sms, "has_email": settings.has_email}

@app.get("/robots.txt", response_class=PlainTextResponse)
def robots(): return "User-agent: *\nDisallow:\n"

# ── Auth ──────────────────────────────────────────────────────
@app.post("/api/auth/login")
def login(payload: LoginRequest):
    con = get_connection()
    try:
        user = authenticate_user(con, payload.email, payload.password)
        if not user:
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid credentials")
        token = create_access_token(user)
        create_audit_entry(con, "auth", user["id"], "login", {"email": user["email"]})
        con.commit()
        return {"access_token": token, "token_type": "bearer",
                "user": {"id": user["id"], "full_name": user["full_name"],
                         "email": user["email"], "role": user["role"],
                         "assigned_facility_id": user["assigned_facility_id"]}}
    finally: con.close()

@app.get("/api/auth/me")
def auth_me(payload: dict = AUTH_ALL):
    con = get_connection()
    try:
        user = fetch_user_by_id(con, payload["sub"])
        if not user: raise HTTPException(status_code=401, detail="User not found")
        return user
    finally: con.close()

# ── Telemetry ingest (called by simulator, no auth required) ──
@app.post("/api/telemetry")
def ingest_telemetry(payload: TelemetryIn):
    con = get_connection()
    try: return insert_telemetry(con, payload)
    finally: con.close()

# ── Data APIs ─────────────────────────────────────────────────
@app.get("/api/overview")
def overview(payload: dict = AUTH_ALL):
    con = get_connection()
    try: return build_overview(con, user=payload)
    finally: con.close()

@app.get("/api/telemetry/recent")
def recent_telemetry(limit: int = Query(default=20, ge=1, le=100), payload: dict = AUTH_ALL):
    con = get_connection()
    try: return list_recent_telemetry(con, limit=limit, user=payload)
    finally: con.close()

@app.get("/api/incidents")
def incidents(limit: int = Query(default=20, ge=1, le=100), payload: dict = AUTH_ALL):
    con = get_connection()
    try: return list_incidents(con, limit=limit, user=payload)
    finally: con.close()

@app.get("/api/notifications")
def notifications(limit: int = Query(default=25, ge=1, le=100), payload: dict = AUTH_ALL):
    con = get_connection()
    try: return list_notifications(con, limit=limit, user=payload)
    finally: con.close()

@app.get("/api/batches")
def batches(payload: dict = AUTH_ALL):
    con = get_connection()
    try: return list_batches(con, user=payload)
    finally: con.close()

@app.get("/api/vaccines")
def vaccines(payload: dict = AUTH_ALL):
    con = get_connection()
    try: return list_vaccines(con)
    finally: con.close()

@app.get("/api/gateways")
def gateways(payload: dict = AUTH_ALL):
    con = get_connection()
    try: return list_gateways(con)
    finally: con.close()

@app.get("/api/transit/latest")
def transit_latest(payload: dict = AUTH_ALL):
    con = get_connection()
    try: return list_transit_locations(con, user=payload)
    finally: con.close()

@app.get("/api/dc-events")
def dc_events(limit: int = Query(default=30, ge=1, le=100), payload: dict = AUTH_ALL):
    con = get_connection()
    try: return list_dc_events(con, limit=limit)
    finally: con.close()

@app.get("/api/reports/analytics")
def report_analytics(payload: dict = AUTH_ALL):
    con = get_connection()
    try: return build_analytics(con, user=payload)
    finally: con.close()

@app.get("/api/reports/export/summary.csv")
def export_summary(payload: dict = AUTH_MGR):
    con = get_connection()
    try: return make_csv_response(build_summary_export_rows(con, user=payload), "coldtrace-summary.csv")
    finally: con.close()

@app.get("/api/reports/export/incidents.csv")
def export_incidents(payload: dict = AUTH_MGR):
    con = get_connection()
    try: return make_csv_response(build_incident_export_rows(con, user=payload), "coldtrace-incidents.csv")
    finally: con.close()
