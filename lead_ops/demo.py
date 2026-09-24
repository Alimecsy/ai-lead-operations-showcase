from __future__ import annotations

import json
from typing import Any

from .adapters import MockAdapterSuite
from .models import AssessmentIntake, ChatIntake, Provenance
from .store import LeadStore
from .workflow import FeatureFlags, WorkflowService


def create_demo_service(*, inject_failure: bool = True) -> WorkflowService:
    failures = {"crm"} if inject_failure else set()
    return WorkflowService(
        LeadStore(":memory:"),
        MockAdapterSuite.create(fail_once=failures),
        FeatureFlags(),
    )


def run_demo_suite(service: WorkflowService) -> dict[str, Any]:
    sales = service.assessment(
        AssessmentIntake(
            session_id="demo-sales-session",
            email="ada@portfolio.example",
            phone="+1 555 0101",
            full_name="Ada Example",
            fit="strong",
            urgency="now",
            budget_alignment="aligned",
            decision_authority=True,
        ),
        provenance=Provenance.SYNTHETIC,
    )
    nurture = service.assessment(
        AssessmentIntake(
            session_id="demo-nurture-session",
            email="ben@portfolio.example",
            full_name="Ben Example",
            fit="moderate",
            urgency="soon",
            budget_alignment="uncertain",
            decision_authority=False,
        ),
        provenance=Provenance.SYNTHETIC,
    )
    educate = service.assessment(
        AssessmentIntake(
            session_id="demo-educate-session",
            email="cy@portfolio.example",
            full_name="Cy Example",
            fit="weak",
            urgency="exploring",
            budget_alignment="misaligned",
            decision_authority=False,
        ),
        provenance=Provenance.SYNTHETIC,
    )
    identity_email_lead = service.assessment(
        AssessmentIntake(
            session_id="demo-conflict-a",
            email="review-email@portfolio.example",
            full_name="Riley Example",
            fit="moderate",
            urgency="soon",
            budget_alignment="uncertain",
            decision_authority=False,
        ),
        provenance=Provenance.SYNTHETIC,
    )
    identity_phone_lead = service.assessment(
        AssessmentIntake(
            session_id="demo-conflict-b",
            email="review-phone@portfolio.example",
            phone="+1 555 0199",
            full_name="Jordan Example",
            fit="moderate",
            urgency="soon",
            budget_alignment="uncertain",
            decision_authority=False,
        ),
        provenance=Provenance.SYNTHETIC,
    )
    conflict = service.assessment(
        AssessmentIntake(
            session_id="demo-conflict-c",
            email="review-email@portfolio.example",
            phone="+1 555 0199",
            full_name="Riley Example",
            fit="strong",
            urgency="now",
            budget_alignment="aligned",
            decision_authority=True,
        ),
        provenance=Provenance.SYNTHETIC,
    )
    chat = service.chat(
        ChatIntake(
            session_id="demo-chat-session",
            message="How does the human review path work?",
        ),
        provenance=Provenance.SYNTHETIC,
    )

    before_retry = {
        "sales": sales,
        "nurture": nurture,
        "educate": educate,
        "identity_seed": {"email": identity_email_lead, "phone": identity_phone_lead},
        "identity_conflict": conflict,
        "chat": chat,
    }
    service.retry(sales["lead_id"])
    after_retry = service.lead_view(sales["lead_id"])
    return {
        "description": "Synthetic end-to-end lead operations demo",
        "before_retry": before_retry,
        "sales_after_retry": after_retry,
        "notes": [
            "The first CRM attempt is intentionally failed when failure injection is enabled.",
            (
                "The local lead state remains available and the retry succeeds through the "
                "same adapter boundary."
            ),
        ],
    }


def main() -> None:
    service = create_demo_service(inject_failure=True)
    print(json.dumps(run_demo_suite(service), indent=2, default=str))


if __name__ == "__main__":
    main()
