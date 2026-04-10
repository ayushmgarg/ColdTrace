from __future__ import annotations

from pydantic import BaseModel, Field


class TelemetryIn(BaseModel):
    packet_id: str = Field(min_length=6)
    device_id: str
    gateway_id: str
    facility_id: str
    batch_id: str
    recorded_at: str
    temperature_c: float
    humidity_pct: float
    battery_voltage: float
    latitude: float | None = None
    longitude: float | None = None
    transport_mode: str = "storage"


class LoginRequest(BaseModel):
    email: str
    password: str
