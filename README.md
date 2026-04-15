# ColdTrace DC — IoT Vaccine Cold Chain Monitoring

**Team:** Vallari Sharma (B116) · Ayush Garg (B143) · Urja Singhi (B146)  
**Course:** Distributed Computing · Sem 6 · BTech CE · MPSTME

Full-stack simulation of a 4-layer IoT distributed system for vaccine cold chain management.  
No real hardware required — every physical component is simulated in software.

---

## Architecture — 4 Layers

```
┌─────────────────────────────────────────────────────────────────┐
│  LAYER 01 — Sensor / Perception                                 │
│  TMP112 temperature sensors (×5 per LTAT, accuracy <0.3°C)     │
│  LTAT device: CH583M microcontroller, 1-min sampling, sleep mode│
└───────────────────────┬─────────────────────────────────────────┘
                        │ 2.4 GHz wireless · low-power
┌───────────────────────▼─────────────────────────────────────────┐
│  LAYER 02 — Gateway                                             │
│  ┌─────────────────────┐ ┌──────────────────┐ ┌─────────────┐  │
│  │ IGD (Intelligent    │ │ CCVE (Cold-Chain │ │ CCIE (Cold- │  │
│  │  Gateway Device)    │ │  Vehicle Equip.) │ │  Chain      │  │
│  │ Local MySQL buffer  │ │ GPS/Beidou track │ │  Incubator  │  │
│  │ 7" touchscreen      │ │ Transit monitor  │ │  Equipment) │  │
│  └─────────────────────┘ └──────────────────┘ └─────────────┘  │
└───────────────────────┬─────────────────────────────────────────┘
                        │ 4G Cat.1 (EC200U) · HTTP POST
                        │ store-and-forward · <2% packet loss
┌───────────────────────▼─────────────────────────────────────────┐
│  LAYER 03 — Cloud                                               │
│  ┌──────────────────┐  ┌───────────────────────────────────┐    │
│  │  Cloud Platform  │  │  Alert Engine  [runs 24/7]        │    │
│  │  FastAPI+SQLite  │  │  Rolling avg (30-min windows)     │    │
│  │  Checksum valid. │  │  Linear regression trend detect.  │    │
│  │  Audit chain     │  │  SMS + Email multicast on breach  │    │
│  └──────────────────┘  └───────────────────────────────────┘    │
└───────────────────────┬─────────────────────────────────────────┘
                        │ REST API · JWT (HS256) · 5s polling
┌───────────────────────▼─────────────────────────────────────────┐
│  LAYER 04 — Application                                         │
│  Web Dashboard (Admin/Manager/Supervisor)                       │
│  Mobile / Field View (Vaccinator)                               │
└─────────────────────────────────────────────────────────────────┘
```

**Safe temperature range:** 2°C – 8°C  
**Simulated facilities:** 6 across Maharashtra (Mumbai, Pune, Nashik, Aurangabad, Nagpur, Kolhapur)  
**Simulated devices:** 7 LTAT sensors (2× storage, 2× vehicle/CCVE, 1× portable/CCIE, 2× cold room)

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

### 3 — Start the gateway simulator (Terminal 2)
```bash
cd simulator
python run_gateway.py
```

### 4 — Open the browser
```
http://localhost:8000/login
```

| Role       | Email                       | Password        |
|------------|-----------------------------|-----------------|
| Admin      | admin@coldtrace.local       | Admin@123       |
| Manager    | manager@coldtrace.local     | Manager@123     |
| Supervisor | supervisor@coldtrace.local  | Supervisor@123  |
| Field      | vaccinator@coldtrace.local  | Vaccinator@123  |

---

## Pages

| URL                    | Purpose                                               |
|------------------------|-------------------------------------------------------|
| `/login`               | Authentication                                        |
| `/`                    | Main dashboard — 4-layer arch, telemetry, incidents   |
| `/operator`            | Mobile field view — sensor readings, battery, alerts  |
| `/reports/executive`   | Print-ready report — DC concepts, audit chain, charts |

---

## DC Concepts → Code

| Concept               | Implementation                                                      |
|-----------------------|---------------------------------------------------------------------|
| Hybrid architecture   | Gateway stores locally (SQLite buffer) when cloud unreachable       |
| Client-server         | LTAT → IGD/CCVE/CCIE → Cloud → Browser hierarchy                   |
| Store-and-forward     | `gateway_buffer.db` SQLite buffer in `simulator/run_gateway.py`     |
| Fault tolerance       | 5 redundant TMP112 sensors per LTAT; simulated gateway outages      |
| Message persistence   | `buffered_packets` table flushed on reconnect                       |
| Clock synchronisation | UTC timestamp on every packet (`utc_now()` at acquisition time)     |
| Reliable multicast    | `create_notifications()` in `services.py` — SMS + email dispatch    |
| Naming / identifiers  | Structured IDs: LTAT-*, IGD-*, CCVE-*, CCIE-*, FAC-*, BATCH-*, INC-* |
| Audit chain           | SHA-256 hash-linked `audit_log` table — tamper-evident immutable log|

---

## Simulated Excursion Scenarios

The simulator auto-creates incidents every few cycles:

| Device              | Excursion                       | Pattern                   |
|---------------------|---------------------------------|---------------------------|
| LTAT-PUNE-TRUCK-01  | High temp spike (door open)     | Steps 4,5,6 of every 12   |
| LTAT-NASHIK-01      | Low temp dip (power outage)     | Steps 7,8 of every 16     |
| LTAT-KOL-01         | Mild high drift (old equipment) | Steps 10,11 of every 20   |

Each excursion triggers: incident creation → alert multicast (SMS + email) → audit log entry.

---

## API Endpoints

| Method | Path                              | Auth      | Purpose                        |
|--------|-----------------------------------|-----------|--------------------------------|
| POST   | `/api/auth/login`                 | None      | Authenticate, get JWT          |
| GET    | `/api/auth/me`                    | Any role  | Current user info              |
| POST   | `/api/telemetry`                  | None      | Ingest sensor packet           |
| GET    | `/api/overview`                   | Any role  | KPIs + facility health         |
| GET    | `/api/telemetry/recent`           | Any role  | Latest telemetry packets       |
| GET    | `/api/incidents`                  | Any role  | Incident list                  |
| GET    | `/api/notifications`              | Any role  | Alert dispatch log             |
| GET    | `/api/gateways`                   | Any role  | IGD/CCVE/CCIE status           |
| GET    | `/api/batches`                    | Any role  | Vaccine batch traceability     |
| GET    | `/api/transit/latest`             | Any role  | Live GPS positions (CCVE)      |
| GET    | `/api/dc-events`                  | Any role  | System event feed              |
| GET    | `/api/audit-log`                  | Mgr+      | SHA-256 hash-linked audit log  |
| GET    | `/api/reports/analytics`          | Any role  | Compliance + facility metrics  |
| GET    | `/api/reports/export/summary.csv` | Mgr+      | Summary CSV export             |
| GET    | `/api/reports/export/incidents.csv`| Mgr+     | Incidents CSV export           |

---

## Database Tables

| Table           | Purpose                                         |
|-----------------|-------------------------------------------------|
| `facilities`    | 6 facilities (hub, transit, clinic, cold store) |
| `gateways`      | 6 IGD/CCVE/CCIE gateway nodes                   |
| `devices`       | 7 LTAT sensor devices                           |
| `vaccines`      | 5 vaccine types with storage requirements       |
| `batches`       | 5 vaccine batches with LOT numbers + traceability|
| `telemetry`     | All sensor readings (grows continuously)        |
| `incidents`     | Auto-created on threshold breach                |
| `notifications` | SMS/email multicast dispatch log                |
| `audit_log`     | SHA-256 hash-linked immutable audit chain       |
| `dc_events`     | System event feed for dashboard                 |
| `users`         | 4 demo users with role-based access             |

---

## Environment Variables (.env)

Copy `.env.example` → `.env`. All external integrations are optional:

```
# SMS alerts (leave blank = simulation mode, notifications still logged)
TWILIO_ACCOUNT_SID=
TWILIO_AUTH_TOKEN=
TWILIO_FROM_NUMBER=

# Email alerts (leave blank = simulation mode)
SENDGRID_API_KEY=

# Live map (leave blank = SVG fallback shown)
MAPBOX_ACCESS_TOKEN=
```

Never commit real API keys to version control.
