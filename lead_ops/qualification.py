from __future__ import annotations

from dataclasses import dataclass

from .models import Route

FIT_POINTS = {"strong": 30, "moderate": 18, "weak": 8}
URGENCY_POINTS = {"now": 25, "soon": 18, "exploring": 8}
BUDGET_POINTS = {"aligned": 25, "uncertain": 15, "misaligned": 5}
AUTHORITY_POINTS = {True: 20, False: 8}


@dataclass(frozen=True)
class QualificationResult:
    score: int
    route: Route
    reasons: list[str]

    def as_dict(self) -> dict[str, object]:
        return {"score": self.score, "route": self.route.value, "reasons": self.reasons}


def qualify(
    *, fit: str, urgency: str, budget_alignment: str, decision_authority: bool
) -> QualificationResult:
    """Apply the illustrative portfolio rule set outside the AI layer."""
    fit_points = FIT_POINTS[fit]
    urgency_points = URGENCY_POINTS[urgency]
    budget_points = BUDGET_POINTS[budget_alignment]
    authority_points = AUTHORITY_POINTS[decision_authority]
    score = fit_points + urgency_points + budget_points + authority_points

    if fit == "strong" and urgency in {"now", "soon"} and budget_alignment == "aligned":
        route = Route.SALES
    elif score >= 50:
        route = Route.NURTURE
    else:
        route = Route.EDUCATE

    reasons = [
        f"fit={fit}:{fit_points}",
        f"urgency={urgency}:{urgency_points}",
        f"budget_alignment={budget_alignment}:{budget_points}",
        f"decision_authority={'yes' if decision_authority else 'no'}:{authority_points}",
    ]
    return QualificationResult(score=score, route=route, reasons=reasons)
