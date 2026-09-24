from lead_ops.models import Route
from lead_ops.qualification import qualify


def test_strong_aligned_urgent_lead_routes_to_sales() -> None:
    result = qualify(
        fit="strong", urgency="now", budget_alignment="aligned", decision_authority=True
    )

    assert result.route is Route.SALES
    assert result.score == 100


def test_weak_exploring_lead_routes_to_education() -> None:
    result = qualify(
        fit="weak", urgency="exploring", budget_alignment="misaligned", decision_authority=False
    )

    assert result.route is Route.EDUCATE
    assert result.score < 50
