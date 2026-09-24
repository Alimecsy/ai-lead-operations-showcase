from lead_ops.guardrails import guard_answer


def test_guardrails_reject_unsupported_numeric_claim() -> None:
    result = guard_answer(
        "OrbitDesk costs $999 per month.", ["OrbitDesk connects intake and tasks."]
    )

    assert result.safe is False
    assert "unsupported_numeric_claim" in result.reasons
    assert "$999" not in result.answer


def test_guardrails_allows_grounded_text() -> None:
    evidence = ["The demo has 3 adapter boundaries."]

    result = guard_answer("The demo has 3 adapter boundaries.", evidence)

    assert result.safe is True
    assert result.answer == evidence[0]
