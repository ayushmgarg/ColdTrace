from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[2]


def load_dotenv() -> None:
    env_path = PROJECT_ROOT / ".env"
    if not env_path.exists():
        return

    for raw_line in env_path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        os.environ.setdefault(key.strip(), value.strip())


load_dotenv()


def env_bool(name: str, default: bool) -> bool:
    return os.getenv(name, str(default)).strip().lower() in {"1", "true", "yes", "on"}


def env_int(name: str, default: int) -> int:
    try:
        return int(os.getenv(name, str(default)))
    except ValueError:
        return default


@dataclass(frozen=True)
class AppConfig:
    app_name: str = os.getenv("APP_NAME", "ColdTrace DC")
    tagline: str = os.getenv("APP_TAGLINE", "Distributed Vaccine Cold Chain Monitoring Platform")
    auth_provider: str = os.getenv("AUTH_PROVIDER", "local").lower()
    jwt_secret: str = os.getenv("JWT_SECRET", "change-this-secret-before-demo")
    token_ttl_minutes: int = env_int("TOKEN_TTL_MINUTES", 720)
    sendgrid_api_key: str = os.getenv("SENDGRID_API_KEY", "")
    email_from: str = os.getenv("EMAIL_FROM", "ayush13garg10@gmail.com")
    email_from_name: str = os.getenv("EMAIL_FROM_NAME", "Ayush Garg")
    twilio_account_sid: str = os.getenv("TWILIO_ACCOUNT_SID", "")
    twilio_auth_token: str = os.getenv("TWILIO_AUTH_TOKEN", "")
    twilio_from_number: str = os.getenv("TWILIO_FROM_NUMBER", "")
    mapbox_access_token: str = os.getenv("MAPBOX_ACCESS_TOKEN", "")
    mapbox_style: str = os.getenv("MAPBOX_STYLE", "mapbox://styles/mapbox/dark-v11")
    auth0_domain: str = os.getenv("AUTH0_DOMAIN", "")
    auth0_audience: str = os.getenv("AUTH0_AUDIENCE", "")
    auth0_client_id: str = os.getenv("AUTH0_CLIENT_ID", "")
    firebase_project_id: str = os.getenv("FIREBASE_PROJECT_ID", "")
    firebase_web_api_key: str = os.getenv("FIREBASE_WEB_API_KEY", "")
    demo_admin_password: str = os.getenv("DEMO_ADMIN_PASSWORD", "Admin@123")
    demo_manager_password: str = os.getenv("DEMO_MANAGER_PASSWORD", "Manager@123")
    demo_supervisor_password: str = os.getenv("DEMO_SUPERVISOR_PASSWORD", "Supervisor@123")
    demo_vaccinator_password: str = os.getenv("DEMO_VACCINATOR_PASSWORD", "Vaccinator@123")

    @property
    def has_sms(self) -> bool:
        return bool(self.twilio_account_sid and self.twilio_auth_token and self.twilio_from_number)

    @property
    def has_email(self) -> bool:
        return bool(self.sendgrid_api_key and self.email_from)

    @property
    def has_mapbox(self) -> bool:
        return bool(self.mapbox_access_token)


settings = AppConfig()

