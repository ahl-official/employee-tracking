"""
WAHA (WhatsApp HTTP API) Client for DeskTrack.
Handles sending movement/task approval requests to Leads via interactive buttons/polls (no links) and webhooks.
"""

from __future__ import annotations

import hashlib
import hmac
import logging
import re
import threading
from datetime import datetime
from typing import Any

import requests

import analytics
import config

logger = logging.getLogger("uvicorn.error")


def clean_phone_number(raw: str) -> str:
    """Normalize phone number to international format without + or spaces."""
    digits = re.sub(r"\D", "", str(raw or ""))
    # If 10 digits (standard Indian mobile without country code), prepend 91
    if len(digits) == 10:
        return f"91{digits}"
    return digits


def create_task_token(task_id: int, action: str) -> str:
    """Generate a tamper-proof HMAC token for 1-click WhatsApp approval links."""
    secret = config.SECRET_KEY or "desktrack-secret-key"
    payload = f"{task_id}:{action}:{secret}"
    return hmac.new(secret.encode("utf-8"), payload.encode("utf-8"), hashlib.sha256).hexdigest()[:24]


def verify_task_token(task_id: int, action: str, token: str) -> bool:
    """Verify the 1-click action token."""
    expected = create_task_token(task_id, action)
    return hmac.compare_digest(expected, str(token or "").strip())


def is_waha_configured() -> bool:
    """Check if WAHA URL and Lead phone number are configured."""
    return bool(config.WAHA_API_URL and config.LEAD_WHATSAPP_PHONE)


def send_whatsapp_message(phone: str, text: str) -> dict[str, Any]:
    """Send text message to a WhatsApp recipient via WAHA REST API."""
    if not config.WAHA_API_URL:
        return {"ok": False, "error": "WAHA_API_URL not configured"}

    normalized_phone = clean_phone_number(phone)
    if not normalized_phone:
        return {"ok": False, "error": "Invalid recipient phone number"}

    chat_id = f"{normalized_phone}@c.us"
    session_name = config.WAHA_SESSION or "default"
    url = f"{config.WAHA_API_URL}/api/sendText"

    headers = {"Content-Type": "application/json"}
    if config.WAHA_API_KEY:
        headers["X-Api-Key"] = config.WAHA_API_KEY

    payload = {
        "session": session_name,
        "chatId": chat_id,
        "text": text,
    }

    try:
        res = requests.post(url, json=payload, headers=headers, timeout=10)
        if res.status_code in (200, 201):
            return {"ok": True, "data": res.json() if res.content else {}}
        logger.warning(f"WAHA sendText returned status {res.status_code}: {res.text[:200]}")
        return {"ok": False, "status": res.status_code, "error": res.text}
    except Exception as exc:
        logger.error(f"Failed to send WhatsApp message via WAHA: {exc}")
        return {"ok": False, "error": str(exc)}


def send_task_approval_poll(
    task_id: int,
    employee_name: str,
    department: str,
    reason: str,
    location: str,
    expected_minutes: int,
    requested_at: datetime,
    lead_phone: str | None = None,
) -> dict[str, Any]:
    """
    Send a single clean interactive WhatsApp message stating all details with two buttons:
    [ ✅ Approve ] and [ ❌ Decline ] (Zero links).
    """
    target_phone = lead_phone or config.LEAD_WHATSAPP_PHONE
    if not target_phone or not config.WAHA_API_URL:
        return {"ok": False, "error": "WAHA not configured"}

    normalized_phone = clean_phone_number(target_phone)
    if not normalized_phone:
        return {"ok": False, "error": "Invalid phone number"}

    chat_id = f"{normalized_phone}@c.us"
    session_name = config.WAHA_SESSION or "default"

    # Format time in local office timezone (e.g. Asia/Kolkata IST)
    dt = analytics.as_dt(requested_at)
    if dt:
        dt_local = dt.astimezone(config.TIMEZONE)
        time_str = dt_local.strftime("%I:%M %p")
    else:
        time_str = "Just now"

    dept_str = f" ({department})" if department else ""
    loc_str = location if location else "Other room"

    poll_text = (
        f"📋 DeskTrack Movement Request\n\n"
        f"👤 Employee: {employee_name}{dept_str}\n"
        f"📍 Location: {loc_str}\n"
        f"🎯 Reason: {reason}\n"
        f"⏳ Duration: {expected_minutes} mins\n"
        f"⏰ Requested At: {time_str}"
    )

    url = f"{config.WAHA_API_URL}/api/sendPoll"
    headers = {"Content-Type": "application/json"}
    if config.WAHA_API_KEY:
        headers["X-Api-Key"] = config.WAHA_API_KEY

    payload = {
        "session": session_name,
        "chatId": chat_id,
        "poll": {
            "name": poll_text,
            "options": ["✅ Approve", "❌ Decline"],
            "multipleAnswers": False,
        },
    }

    try:
        res = requests.post(url, json=payload, headers=headers, timeout=12)
        if res.status_code in (200, 201):
            return {"ok": True, "data": res.json() if res.content else {}}
        logger.warning(f"WAHA sendPoll returned status {res.status_code}: {res.text[:200]}")
        # Fallback to plain text if poll is rejected
        return send_whatsapp_message(target_phone, poll_text + "\n\nReply with *APPROVE* or *REJECT*")
    except Exception as exc:
        logger.error(f"Failed to send WhatsApp poll via WAHA: {exc}")
        return {"ok": False, "error": str(exc)}


def notify_lead_task_request_async(
    task_id: int,
    employee_name: str,
    department: str,
    reason: str,
    location: str,
    expected_minutes: int,
    requested_at: datetime,
    lead_phone: str | None = None,
) -> None:
    """Dispatch single WhatsApp interactive button poll to lead in background thread."""
    def _worker():
        send_task_approval_poll(
            task_id=task_id,
            employee_name=employee_name,
            department=department,
            reason=reason,
            location=location,
            expected_minutes=expected_minutes,
            requested_at=requested_at,
            lead_phone=lead_phone,
        )

    threading.Thread(target=_worker, daemon=True).start()


def notify_task_resolution_async(
    task_id: int,
    employee_name: str,
    status: str,  # approved or rejected
    lead_phone: str | None = None,
) -> None:
    """No-op: user requested a single message without follow-up messages."""
    pass
