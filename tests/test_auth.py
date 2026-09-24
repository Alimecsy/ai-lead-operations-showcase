from fastapi.testclient import TestClient

from lead_ops.main import create_app
from lead_ops.store import LeadStore


def test_operator_routes_can_be_protected(monkeypatch) -> None:
    monkeypatch.setenv("SHOWCASE_OPERATOR_TOKEN", "local-operator-token")
    client = TestClient(create_app(store=LeadStore(":memory:")))

    without_token = client.get("/leads/not-a-real-lead")
    with_token = client.get(
        "/leads/not-a-real-lead", headers={"x-operator-token": "local-operator-token"}
    )

    assert without_token.status_code == 401
    assert with_token.status_code == 404
