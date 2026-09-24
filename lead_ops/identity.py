from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass

from .models import IdentityStatus

PHONE_RE = re.compile(r"[^\d+]")


def normalize_email(value: str | None) -> str | None:
    if not value:
        return None
    normalized = value.strip().lower()
    return normalized or None


def normalize_phone(value: str | None) -> str | None:
    if not value:
        return None
    normalized = PHONE_RE.sub("", value.strip())
    return normalized or None


def lead_ref(*, session_id: str | None, email: str | None, phone: str | None) -> str:
    identity = normalize_email(email) or normalize_phone(phone) or session_id or "anonymous"
    digest = hashlib.sha256(identity.encode("utf-8")).hexdigest()[:10].upper()
    return f"DEMO-{digest}"


@dataclass(frozen=True)
class IdentityResolution:
    status: IdentityStatus
    lead_id: str | None = None
    conflicting_lead_ids: tuple[str, ...] = ()
    reason: str | None = None
