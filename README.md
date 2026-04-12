# ColdTrace DC — IoT Vaccine Cold Chain Monitoring

**Semester Project · Distributed Computing · B116 / B143 / B146**

A full-stack simulation of a 4-layer IoT cold chain management system for vaccines.  
No real hardware needed — every physical component is simulated in software.

---

## Architecture

```
Layer 1 — Sensors     LTAT-* devices (simulated in run_gateway.py)
               ↕  MQTT / HTTP POST (store-and-forward)
Layer 2 — Gateways    IGD-* gateway nodes (SQLite buffer in gateway_buffer.db)
               ↕  4G Cat.1 / HTTP POST
Layer 3 — Cloud       FastAPI + SQLite (backend/app/)
               ↕  REST API + polling
Layer 4 — App         Web Dashboard  /  Field View  /  Executive Report
```

---

## Quick Start

### 1 — Install dependencies
```bash
pip install -r requirements.txt
```

### 2 — Start the backend (Terminal 1)
```bash
cd backend
uvicorn app.main:app --reload --port 8000
```

### 3 — Start the simulator (Terminal 2)
```bash
cd simulator
python run_gateway.py
```

### 4 — Open the UI
```
http://localhost:8000/login
```

| Role        | Email                        | Password       |
|-------------|------------------------------|----------------|
| Admin       | admin@coldtrace.local        | Admin@123      |
| Manager     | manager@coldtrace.local      | Manager@123    |
| Supervisor  | supervisor@coldtrace.local   | Supervisor@123 |
| Field       | vaccinator@coldtrace.local   | Vaccinator@123 |

---

## Pages

| URL                   | Purpose                                              |
|-----------------------|------------------------------------------------------|
| `/`                   | Main operations dashboard (charts, DC architecture) |
| `/operator`           | Mobile field view (sensor readings, gateway status)  |
| `/reports/executive`  | Viva/print report with charts and DC concept grid    |
| `/login`              | Authentication                                       |

---

## DC Concepts → Code Locations

| Concept             | Where                                                       |
|---------------------|-------------------------------------------------------------|
| Hybrid architecture | `simulator/run_gateway.py` buffer + `backend/app/services.py` cloud |
| Client-server       | LTAT→IGD→Cloud→Browser hierarchy throughout                |
| Store-and-forward   | `gateway_buffer.db` SQLite buffer in simulator              |
| Fault tolerance     | `maybe_fail()` in simulator, 5 sensors per LTAT             |
| Message persistence | `buffered_packets` table, flush on reconnect                |
| Clock sync          | `utc_now()` UTC timestamp on every packet                   |
| Reliable multicast  | `create_notifications()` in `services.py` — SMS + email     |
| Naming              | Structured IDs: LTAT-*, IGD-*, FAC-*, BATCH-*, INC-*       |
| Audit chain         | SHA-256 hash-linked `audit_log` table in `services.py`      |

---

## Environment Variables (.env)

Copy `.env.example` to `.env` and fill in only what you need:

```
# Leave Twilio/SendGrid blank → simulation mode (still logs notifications)
TWILIO_ACCOUNT_SID=
TWILIO_AUTH_TOKEN=
SENDGRID_API_KEY=

# Leave blank → SVG fallback map is shown instead of Mapbox
MAPBOX_ACCESS_TOKEN=
```

**Never commit real API keys to version control.**

---

## Simulated Excursion Scenarios

The simulator automatically creates incidents:

| Device              | Excursion type                | Cycle pattern |
|---------------------|-------------------------------|---------------|
| LTAT-PUNE-TRUCK-01  | High temp (door left open)    | Steps 4,5,6 of every 12 |
| LTAT-NASHIK-01      | Low temp (power outage)       | Steps 7,8 of every 16   |
| LTAT-KOL-01         | High temp (older equipment)   | Steps 10,11 of every 20 |

These trigger: incident creation → notification dispatch → alert multicast log.

---

## Database Tables

| Table             | Purpose                                    |
|-------------------|--------------------------------------------|
| `facilities`      | 6 facilities across Maharashtra            |
| `gateways`        | 6 IGD gateway nodes                        |
| `devices`         | 7 LTAT sensor devices                      |
| `vaccines`        | 5 vaccine types with storage requirements  |
| `batches`         | 5 vaccine batches with lot numbers         |
| `telemetry`       | All sensor readings (grows continuously)   |
| `incidents`       | Auto-created on threshold breach           |
| `notifications`   | SMS/email multicast log                    |
| `audit_log`       | SHA-256 hash-linked immutable audit chain  |
| `dc_events`       | DC system events feed for dashboard        |
| `users`           | 4 demo users with role-based access        |
