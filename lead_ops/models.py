from __future__ import annotations

from enum import StrEnum
from typing import Any

from pydantic import BaseModel, EmailStr, Field


class Provenance(StrEnum):
    HUMAN = "human"
    SYNTHETIC = "synthetic"
    SYSTEM = "system"


class IdentityStatus(StrEnum):
    PROVISIONAL = "provisional"
    CREATED = "created"
    MATCHED = "matched"
    CONFLICT = "conflict"


class Route(StrEnum):
    SALES = "sales"
    NURTURE = "nurture"
    EDUCATE = "educate"
    REVIEW = "review"


class JobStatus(StrEnum):
    PENDING = "pending"
    RUNNING = "running"
    SUCCEEDED = "succeeded"
    FAILED = "failed"


class ChatIntake(BaseModel):
    session_id: str = Field(min_length=1, max_length=128)
    message: str = Field(min_length=1, max_length=4000)
    email: EmailStr | None = None
    phone: str | None = Field(default=None, max_length=64)
    full_name: str | None = Field(default=None, max_length=160)


class AssessmentIntake(BaseModel):
    session_id: str = Field(min_length=1, max_length=128)
    email: EmailStr | None = None
    phone: str | None = Field(default=None, max_length=64)
    full_name: str | None = Field(default=None, max_length=160)
    fit: str = Field(pattern="^(strong|moderate|weak)$")
    urgency: str = Field(pattern="^(now|soon|exploring)$")
    budget_alignment: str = Field(pattern="^(aligned|uncertain|misaligned)$")
    decision_authority: bool
    notes: str | None = Field(default=None, max_length=1000)


class RetryResponse(BaseModel):
    lead_id: str
    jobs: list[dict[str, Any]]


class DemoRequest(BaseModel):
    inject_failure: bool = True
