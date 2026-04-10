from __future__ import annotations

import json
from typing import Any

import requests

from .config import settings


def send_sms(to: str, body: str) -> dict[str, Any]:
    if not settings.has_sms:
        return {"status": "simulated_sent", "provider": "simulation", "message": "Twilio not configured"}

    response = requests.post(
        f"https://api.twilio.com/2010-04-01/Accounts/{settings.twilio_account_sid}/Messages.json",
        auth=(settings.twilio_account_sid, settings.twilio_auth_token),
        data={"To": to, "From": settings.twilio_from_number, "Body": body},
        timeout=10,
    )
    if response.ok:
        payload = response.json()
        return {
            "status": "sent",
            "provider": "twilio",
            "provider_message_id": payload.get("sid"),
            "message": "SMS sent",
        }
    return {
        "status": "failed",
        "provider": "twilio",
        "message": response.text[:500],
    }


def send_email(to: str, subject: str, html_content: str, text_content: str) -> dict[str, Any]:
    if not settings.has_email:
        return {"status": "simulated_sent", "provider": "simulation", "message": "SendGrid not configured"}

    payload = {
        "personalizations": [{"to": [{"email": to}], "subject": subject}],
        "from": {"email": settings.email_from, "name": settings.email_from_name},
        "content": [
            {"type": "text/plain", "value": text_content},
            {"type": "text/html", "value": html_content},
        ],
    }
    response = requests.post(
        "https://api.sendgrid.com/v3/mail/send",
        headers={
            "Authorization": f"Bearer {settings.sendgrid_api_key}",
            "Content-Type": "application/json",
        },
        data=json.dumps(payload),
        timeout=10,
    )
    if response.status_code in {200, 202}:
        return {
            "status": "sent",
            "provider": "sendgrid",
            "provider_message_id": response.headers.get("X-Message-Id", ""),
            "message": "Email sent",
        }
    return {
        "status": "failed",
        "provider": "sendgrid",
        "message": response.text[:500],
    }
