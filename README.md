# ColdTrace 

ColdTrace is a software-only implementation of a distributed vaccine cold chain monitoring platform based on the architecture described in the project PDFs.

It simulates LTAT sensor nodes, an IGD-style gateway, a cloud analytics layer, role-based dashboards, report exports, mobile operator workflows, and optional real integrations for SMS, email, and transport maps.

## Architecture

The repo follows the same four-layer design from your semester documents:

1. Sensor / Perception Layer
   Simulated LTAT devices generate temperature, humidity, battery, and optional GPS telemetry.
2. Gateway Layer
   A software gateway buffers packets locally and flushes them when connectivity returns.
3. Cloud Layer
   FastAPI + SQLite ingest telemetry, detect excursions, trigger alerts, compute analytics, and maintain audit logs.
4. Application Layer
   Web operations console, executive report view, and mobile operator surface.

## Implemented Features

- Sensor simulation for storage, transit, and field devices
- Gateway buffering with store-and-forward fault tolerance
- Cloud telemetry ingestion and persistence
- Temperature excursion detection
- Low-battery detection
- Hash-chained audit trail for tamper-evident records
- Role-based authentication
- User roles: admin, vaccine manager, supervisor, vaccinator
- Operations dashboard
- Mobile operator view
- Executive report page
- CSV export for summary and incident reports
- Twilio-ready SMS delivery
- SendGrid-ready email delivery
- Mapbox-ready transport map
- Google Stitch-ready frontend/API separation

## Tech Stack

- Backend: FastAPI
- Storage: SQLite
- Simulation: Python
- Frontend: HTML, CSS, vanilla JS
- Optional messaging: Twilio, SendGrid
- Optional map layer: Mapbox
- Optional external auth placeholders: Auth0, Firebase

## Screens And Roles

- `/login`
  Role-based login screen
- `/`
  Main operations dashboard for admin, manager, supervisor
- `/operator`
  Mobile-friendly operator surface for vaccinators and field staff
- `/reports/executive`
  Presentation-ready analytics and print/save-as-PDF report

Role matrix is documented in [docs/role-matrix.md](docs/role-matrix.md).

## Project Structure

```text
ColdChainDC/
├─ backend/
│  └─ app/
│     ├─ auth.py
│     ├─ config.py
│     ├─ database.py
│     ├─ integrations.py
│     ├─ main.py
│     ├─ schemas.py
│     ├─ services.py
│     ├─ static/
│     └─ templates/
├─ docs/
│  ├─ architecture-mapping.md
│  ├─ role-matrix.md
│  └─ stitch-ui-brief.md
├─ scripts/
├─ simulator/
├─ .env
├─ .env.example
└─ requirements.txt
```

## Setup

### 1. Install dependencies

```powershell
python -m pip install -r requirements.txt
```

### 2. Configure environment

Copy `.env.example` to `.env` if needed. A ready-to-edit `.env` file is already included in this workspace.

Important fields:

```env
APP_NAME=ColdTrace DC
JWT_SECRET=change-this-secret-before-demo
EMAIL_FROM=ayush13garg10@gmail.com
TWILIO_ACCOUNT_SID=
TWILIO_AUTH_TOKEN=
TWILIO_FROM_NUMBER=
SENDGRID_API_KEY=
MAPBOX_ACCESS_TOKEN=
```

Notes:

- Email sender is already set to `ayush13garg10@gmail.com`
- Twilio and SendGrid stay in simulated mode until you add real keys
- Mapbox transport map activates only after you paste a token

### 3. Start the backend

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\run_backend.ps1
```

### 4. Start the simulator

Open another terminal and run:

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\run_gateway_sim.ps1
```

### 5. Open the app

Visit:

- [http://127.0.0.1:8000/login](http://127.0.0.1:8000/login)

## Default Demo Logins

- `admin@coldtrace.local` / `Admin@123`
- `manager@coldtrace.local` / `Manager@123`
- `supervisor@coldtrace.local` / `Supervisor@123`
- `vaccinator@coldtrace.local` / `Vaccinator@123`

You can change these in `.env`:

- `DEMO_ADMIN_PASSWORD`
- `DEMO_MANAGER_PASSWORD`
- `DEMO_SUPERVISOR_PASSWORD`
- `DEMO_VACCINATOR_PASSWORD`

## Integrations

### Twilio SMS

Add these values in `.env`:

```env
TWILIO_ACCOUNT_SID=your_sid
TWILIO_AUTH_TOKEN=your_auth_token
TWILIO_FROM_NUMBER=your_twilio_number
```

If not configured, SMS stays simulated and still gets logged in the notification table.

### SendGrid Email

Add this in `.env`:

```env
SENDGRID_API_KEY=your_sendgrid_key
EMAIL_FROM=ayush13garg10@gmail.com
EMAIL_FROM_NAME=Ayush Garg
```

Important:

- the sender email must be verified in your SendGrid setup
- if not configured, email stays simulated and still gets logged

### Mapbox

Add this in `.env`:

```env
MAPBOX_ACCESS_TOKEN=your_mapbox_token
MAPBOX_STYLE=mapbox://styles/mapbox/dark-v11
```

Then the operations dashboard shows live transit points on a map.

## Authentication

Current implementation uses local JWT-based authentication with seeded users and roles.

Why this choice:

- it works fully offline for a semester demo
- it avoids blocking the core system on external identity setup
- it keeps the project functional even before you add third-party credentials

Placeholders for future external auth are already included in `.env`:

- `AUTH0_DOMAIN`
- `AUTH0_AUDIENCE`
- `AUTH0_CLIENT_ID`
- `FIREBASE_PROJECT_ID`
- `FIREBASE_WEB_API_KEY`

## APIs

Public:

- `GET /health`
- `GET /api/public/config`
- `POST /api/auth/login`
- `POST /api/telemetry`

Protected:

- `GET /api/auth/me`
- `GET /api/overview`
- `GET /api/telemetry/recent`
- `GET /api/incidents`
- `GET /api/notifications`
- `GET /api/batches`
- `GET /api/transit/latest`
- `GET /api/reports/analytics`
- `GET /api/reports/export/summary.csv`
- `GET /api/reports/export/incidents.csv`


## Future Upgrades

- PDF report generation beyond print/save-as-PDF
- live WebSocket streaming
- QR or barcode scan workflow for batch movement
- vaccine route replay on maps
- fully externalized auth with Auth0 or Firebase
- richer device assignment and field-team workflows

