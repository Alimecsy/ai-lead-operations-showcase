from lead_ops.adapters import MockAdapterSuite
from lead_ops.models import AssessmentIntake, ChatIntake, Provenance, Route
from lead_ops.store import LeadStore
from lead_ops.workflow import FeatureFlags, WorkflowService


def assessment(**overrides: object) -> AssessmentIntake:
    values: dict[str, object] = {
        "session_id": "session-1",
        "email": "person@portfolio.example",
        "full_name": "Person Example",
        "fit": "strong",
        "urgency": "now",
        "budget_alignment": "aligned",
        "decision_authority": True,
    }
    values.update(overrides)
    return AssessmentIntake(**values)


def test_assessment_persists_route_and_executes_mock_adapters(service: WorkflowService) -> None:
    result = service.assessment(assessment(), provenance=Provenance.SYNTHETIC)

    assert result["provenance"] == "synthetic"
    assert result["route"] == Route.SALES.value
    assert result["qualification"]["score"] == 100
    assert {job["adapter"] for job in result["jobs"]} == {"crm", "booking"}
    assert all(job["status"] == "succeeded" for job in result["jobs"])
    assert any(event["event_type"] == "route_selected" for event in result["events"])


def test_identity_conflict_creates_human_review_job(service: WorkflowService) -> None:
    service.assessment(
        assessment(session_id="email-session", email="one@portfolio.example", phone=None),
        provenance=Provenance.SYNTHETIC,
    )
    service.assessment(
        assessment(session_id="phone-session", email="two@portfolio.example", phone="+1 555 0102"),
        provenance=Provenance.SYNTHETIC,
    )

    result = service.assessment(
        assessment(
            session_id="conflict-session", email="one@portfolio.example", phone="+1 555 0102"
        ),
        provenance=Provenance.SYNTHETIC,
    )

    assert result["identity_status"] == "conflict"
    assert result["route"] == Route.REVIEW.value
    assert result["review_required"] is True
    assert result["jobs"][0]["adapter"] == "human_review"
    assert result["jobs"][0]["status"] == "succeeded"


def test_failed_downstream_job_keeps_local_truth_and_retry_recovers() -> None:
    store = LeadStore(":memory:")
    adapters = MockAdapterSuite.create(fail_once={"crm"})
    service = WorkflowService(store, adapters, FeatureFlags())
    try:
        first = service.assessment(assessment(), provenance=Provenance.SYNTHETIC)
        crm_job = next(job for job in first["jobs"] if job["adapter"] == "crm")

        assert first["route"] == Route.SALES.value
        assert crm_job["status"] == "failed"
        assert first["qualification"]["score"] == 100

        recovered = service.retry(first["lead_id"])
        recovered_crm = next(job for job in recovered["jobs"] if job["adapter"] == "crm")
        assert recovered_crm["status"] == "succeeded"
        assert any(
            event["event_type"] == "integration_failed"
            for event in service.lead_view(first["lead_id"])["events"]
        )
    finally:
        store.close()


def test_chat_returns_retrieval_sources_and_provenance(service: WorkflowService) -> None:
    result = service.chat(
        ChatIntake(session_id="chat-1", message="How does the human review path work?"),
        provenance=Provenance.SYNTHETIC,
    )

    assert result["provenance"] == "synthetic"
    assert result["sources"]
    assert "human" in result["answer"].lower()
