from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Any

from .adapters import AdapterError, MockAdapterSuite
from .assistant import GroundedAssistant
from .identity import IdentityResolution, lead_ref, normalize_email, normalize_phone
from .models import AssessmentIntake, ChatIntake, IdentityStatus, JobStatus, Provenance, Route
from .qualification import QualificationResult, qualify
from .store import LeadStore


@dataclass(frozen=True)
class FeatureFlags:
    crm_enabled: bool = True
    booking_enabled: bool = True
    follow_up_enabled: bool = True
    human_review_enabled: bool = True

    @classmethod
    def from_env(cls) -> FeatureFlags:
        def enabled(name: str, default: bool) -> bool:
            value = os.getenv(name)
            return default if value is None else value.lower() in {"1", "true", "yes", "on"}

        return cls(
            crm_enabled=enabled("SHOWCASE_CRM_ENABLED", True),
            booking_enabled=enabled("SHOWCASE_BOOKING_ENABLED", True),
            follow_up_enabled=enabled("SHOWCASE_FOLLOW_UP_ENABLED", True),
            human_review_enabled=enabled("SHOWCASE_HUMAN_REVIEW_ENABLED", True),
        )

    def as_dict(self) -> dict[str, bool]:
        return {
            "crm_enabled": self.crm_enabled,
            "booking_enabled": self.booking_enabled,
            "follow_up_enabled": self.follow_up_enabled,
            "human_review_enabled": self.human_review_enabled,
        }


class WorkflowService:
    def __init__(
        self,
        store: LeadStore,
        adapters: MockAdapterSuite,
        flags: FeatureFlags | None = None,
        assistant: GroundedAssistant | None = None,
    ) -> None:
        self.store = store
        self.adapters = adapters
        self.flags = flags or FeatureFlags()
        self.assistant = assistant or GroundedAssistant()

    def chat(
        self, payload: ChatIntake, *, provenance: Provenance = Provenance.HUMAN
    ) -> dict[str, Any]:
        lead, resolution = self._resolve_or_create(
            session_id=payload.session_id,
            email=str(payload.email) if payload.email else None,
            phone=payload.phone,
            full_name=payload.full_name,
            provenance=provenance,
        )
        self.store.append_event(
            lead["lead_id"],
            "chat_received",
            {"message": payload.message, "provenance": provenance.value},
        )

        if resolution.status is IdentityStatus.CONFLICT:
            answer = (
                "A team member needs to review the identity details before this conversation "
                "can continue."
            )
            self.store.update_lead(
                lead["lead_id"],
                route=Route.REVIEW.value,
                review_required=True,
                human_action="resolve_identity",
            )
            self.store.append_event(
                lead["lead_id"], "human_review_required", {"reason": resolution.reason}
            )
            if self.flags.human_review_enabled:
                self._enqueue(
                    lead,
                    "human_review",
                    "resolve_identity",
                    {"lead_id": lead["lead_id"], "lead_ref": lead["lead_ref"]},
                )
                self.process_jobs(lead_id=lead["lead_id"])
            return self._chat_response(lead, resolution, answer, [], provenance)

        draft = self.assistant.draft(payload.message)
        self.store.append_event(
            lead["lead_id"],
            "answer_generated",
            {"safe": draft.safe, "guardrail_reasons": draft.guardrail_reasons},
        )
        return self._chat_response(lead, resolution, draft.answer, draft.sources, provenance)

    def assessment(
        self, payload: AssessmentIntake, *, provenance: Provenance = Provenance.HUMAN
    ) -> dict[str, Any]:
        lead, resolution = self._resolve_or_create(
            session_id=payload.session_id,
            email=str(payload.email) if payload.email else None,
            phone=payload.phone,
            full_name=payload.full_name,
            provenance=provenance,
        )
        if resolution.status is IdentityStatus.CONFLICT:
            self.store.update_lead(
                lead["lead_id"],
                route=Route.REVIEW.value,
                review_required=True,
                human_action="resolve_identity",
            )
            self.store.append_event(
                lead["lead_id"],
                "identity_conflict",
                {"conflicting_lead_ids": list(resolution.conflicting_lead_ids)},
            )
            if self.flags.human_review_enabled:
                self._enqueue(
                    lead,
                    "human_review",
                    "resolve_identity",
                    {
                        "lead_id": lead["lead_id"],
                        "lead_ref": lead["lead_ref"],
                        "conflicting_lead_ids": list(resolution.conflicting_lead_ids),
                    },
                )
                self.process_jobs(lead_id=lead["lead_id"])
            else:
                self._skip(lead, "human_review", "feature_disabled")
            return self.lead_view(lead["lead_id"])

        result = qualify(
            fit=payload.fit,
            urgency=payload.urgency,
            budget_alignment=payload.budget_alignment,
            decision_authority=payload.decision_authority,
        )
        lead = self.store.update_lead(
            lead["lead_id"],
            identity_status=resolution.status.value,
            route=result.route.value,
            qualification=result.as_dict(),
        )
        self.store.append_event(
            lead["lead_id"],
            "assessment_received",
            {"inputs": payload.model_dump(exclude={"email", "phone", "full_name"})},
        )
        self.store.append_event(lead["lead_id"], "route_selected", result.as_dict())
        self._queue_route_jobs(lead, result, payload)
        self.process_jobs(lead_id=lead["lead_id"])
        return self.lead_view(lead["lead_id"])

    def retry(self, lead_id: str) -> dict[str, Any]:
        self.process_jobs(lead_id=lead_id)
        return {"lead_id": lead_id, "jobs": self.store.list_jobs(lead_id)}

    def lead_view(self, lead_id: str) -> dict[str, Any]:
        lead = self.store.get_lead(lead_id)
        if lead is None:
            raise KeyError(lead_id)
        return {
            **lead,
            "events": self.store.list_events(lead_id),
            "jobs": self.store.list_jobs(lead_id),
        }

    def process_jobs(self, *, lead_id: str | None = None) -> None:
        for job in self.store.list_jobs(lead_id):
            if job["status"] not in {JobStatus.PENDING.value, JobStatus.FAILED.value}:
                continue
            claimed = self.store.claim_job(job["job_id"])
            adapter = self.adapters.for_name(claimed["adapter"])
            try:
                result = adapter.execute(claimed["payload"])
            except AdapterError as exc:
                failed = self.store.finish_job(
                    claimed["job_id"], status=JobStatus.FAILED, error=str(exc)
                )
                self.store.append_event(
                    claimed["lead_id"],
                    "integration_failed",
                    {"job_id": claimed["job_id"], "adapter": claimed["adapter"], "error": str(exc)},
                )
                if failed["attempts"] >= 3:
                    self.store.append_event(
                        claimed["lead_id"],
                        "operator_attention_required",
                        {"job_id": claimed["job_id"], "reason": "repeated_integration_failure"},
                    )
            else:
                self.store.finish_job(claimed["job_id"], status=JobStatus.SUCCEEDED, result=result)
                self.store.append_event(
                    claimed["lead_id"],
                    "integration_succeeded",
                    {"job_id": claimed["job_id"], "adapter": claimed["adapter"]},
                )

    def _resolve_or_create(
        self,
        *,
        session_id: str,
        email: str | None,
        phone: str | None,
        full_name: str | None,
        provenance: Provenance,
    ) -> tuple[dict[str, Any], IdentityResolution]:
        matches = self.store.find_identity_matches(email=email, phone=phone, session_id=session_id)
        email_normalized = normalize_email(email)
        phone_normalized = normalize_phone(phone)
        email_match = next(
            (match for match in matches if email_normalized and match["email"] == email_normalized),
            None,
        )
        phone_match = next(
            (match for match in matches if phone_normalized and match["phone"] == phone_normalized),
            None,
        )
        session_match = next(
            (match for match in matches if match["session_id"] == session_id), None
        )

        if email_match and phone_match and email_match["lead_id"] != phone_match["lead_id"]:
            resolution = IdentityResolution(
                status=IdentityStatus.CONFLICT,
                conflicting_lead_ids=(email_match["lead_id"], phone_match["lead_id"]),
                reason="email_and_phone_match_different_leads",
            )
            lead = self.store.insert_lead(
                {
                    # A conflict is a separate review record, so its reference
                    # must not collide with either canonical identity record.
                    "lead_ref": lead_ref(session_id=session_id, email=None, phone=None),
                    "session_id": session_id,
                    "email": email,
                    "phone": phone,
                    "full_name": full_name,
                    "identity_status": IdentityStatus.CONFLICT.value,
                    "provenance": provenance.value,
                    "route": Route.REVIEW.value,
                    "review_required": True,
                    "human_action": "resolve_identity",
                }
            )
            return lead, resolution

        matched = email_match or phone_match or session_match
        if matched:
            resolution = IdentityResolution(
                status=IdentityStatus.MATCHED, lead_id=matched["lead_id"]
            )
            lead = self.store.update_lead(
                matched["lead_id"],
                session_id=session_id,
                email=email or matched["email"],
                phone=phone or matched["phone"],
                full_name=full_name or matched["full_name"],
                provenance=provenance.value,
                identity_status=IdentityStatus.MATCHED.value,
            )
            return lead, resolution

        status = (
            IdentityStatus.CREATED
            if email_normalized or phone_normalized
            else IdentityStatus.PROVISIONAL
        )
        resolution = IdentityResolution(status=status)
        lead = self.store.insert_lead(
            {
                "lead_ref": lead_ref(session_id=session_id, email=email, phone=phone),
                "session_id": session_id,
                "email": email,
                "phone": phone,
                "full_name": full_name,
                "identity_status": status.value,
                "provenance": provenance.value,
            }
        )
        return lead, resolution

    def _queue_route_jobs(
        self, lead: dict[str, Any], result: QualificationResult, payload: AssessmentIntake
    ) -> None:
        route = result.route
        base_payload = {
            "lead_id": lead["lead_id"],
            "lead_ref": lead["lead_ref"],
            "route": route.value,
            "provenance": lead["provenance"],
        }
        if self.flags.crm_enabled:
            self._enqueue(
                lead, "crm", "create_task", {**base_payload, "task": f"Review {route.value} route"}
            )
        else:
            self._skip(lead, "crm", "feature_disabled")

        if route is Route.SALES:
            if self.flags.booking_enabled:
                self._enqueue(
                    lead, "booking", "create_handoff", {**base_payload, "next_step": "consultation"}
                )
            else:
                self._skip(lead, "booking", "feature_disabled")
        elif self.flags.follow_up_enabled:
            self._enqueue(
                lead,
                "follow_up",
                "send_next_step",
                {**base_payload, "next_step": "education" if route is Route.EDUCATE else "nurture"},
            )
        else:
            self._skip(lead, "follow_up", "feature_disabled")

    def _enqueue(
        self, lead: dict[str, Any], adapter: str, action: str, payload: dict[str, Any]
    ) -> None:
        self.store.enqueue_job(
            lead_id=lead["lead_id"], adapter=adapter, action=action, payload=payload
        )
        self.store.append_event(
            lead["lead_id"], "integration_queued", {"adapter": adapter, "action": action}
        )

    def _skip(self, lead: dict[str, Any], adapter: str, reason: str) -> None:
        self.store.append_event(
            lead["lead_id"], "integration_skipped", {"adapter": adapter, "reason": reason}
        )

    @staticmethod
    def _chat_response(
        lead: dict[str, Any],
        resolution: IdentityResolution,
        answer: str,
        documents: list[Any],
        provenance: Provenance,
    ) -> dict[str, Any]:
        return {
            "lead_id": lead["lead_id"],
            "lead_ref": lead["lead_ref"],
            "identity_status": resolution.status.value,
            "route": lead.get("route"),
            "review_required": lead["review_required"],
            "provenance": provenance.value,
            "answer": answer,
            "sources": [
                {"document_id": document.document_id, "title": document.title}
                for document in documents
            ],
        }
