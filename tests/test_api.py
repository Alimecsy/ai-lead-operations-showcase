from fastapi.testclient import TestClient

from lead_ops.adapters import MockAdapterSuite
from lead_ops.main import create_app
from lead_ops.store import LeadStore
from lead_ops.workflow import FeatureFlags, WorkflowService


def test_api_exposes_chat_assessment_and_retry() -> None:
    store = LeadStore(":memory:")
    service = WorkflowService(store, MockAdapterSuite.create(), FeatureFlags())
    client = TestClient(create_app(store=store, service=service))

    assessment = client.post(
        "/assessment",
        json={
            "session_id": "api-session",
            "email": "api@portfolio.example",
            "fit": "moderate",
            "urgency": "soon",
            "budget_alignment": "uncertain",
            "decision_authority": False,
        },
    )
    assert assessment.status_code == 200
    lead = assessment.json()
    assert lead["route"] == "nurture"

    chat = client.post(
        "/chat",
        json={"session_id": "api-chat", "message": "What does the workflow connect?"},
    )
    assert chat.status_code == 200
    assert chat.json()["sources"]

    retry = client.post(f"/leads/{lead['lead_id']}/retry")
    assert retry.status_code == 200
    assert retry.json()["lead_id"] == lead["lead_id"]

    store.close()


def test_demo_endpoint_exercises_failure_and_recovery() -> None:
    client = TestClient(create_app(store=LeadStore(":memory:")))

    response = client.post("/demo/run", json={"inject_failure": True})

    assert response.status_code == 200
    body = response.json()
    assert body["sales_after_retry"]["route"] == "sales"
    assert any(
        event["event_type"] == "integration_failed" for event in body["sales_after_retry"]["events"]
    )
    assert body["before_retry"]["identity_conflict"]["route"] == "review"
