from __future__ import annotations

import re
from dataclasses import dataclass

UNSUPPORTED_GUARANTEE_RE = re.compile(
    r"\b(guaranteed|guarantee|risk[- ]free|always works|certain to succeed)\b", re.IGNORECASE
)
NUMBER_RE = re.compile(r"(?<![A-Za-z])(?:[$€£]\s*)?\d+(?:[.,]\d+)?%?(?![A-Za-z])")
SAFE_FALLBACK = (
    "I can explain the workflow at a high level, but I should not invent a promise or "
    "unsupported figure. A human operator can review the specific case."
)


@dataclass(frozen=True)
class GuardrailResult:
    answer: str
    safe: bool
    reasons: list[str]


def guard_answer(answer: str, evidence: list[str]) -> GuardrailResult:
    reasons: list[str] = []
    if UNSUPPORTED_GUARANTEE_RE.search(answer):
        reasons.append("prohibited_guarantee_language")

    evidence_numbers = set(NUMBER_RE.findall(" ".join(evidence)))
    answer_numbers = set(NUMBER_RE.findall(answer))
    unsupported_numbers = answer_numbers - evidence_numbers
    if unsupported_numbers:
        reasons.append("unsupported_numeric_claim")

    if reasons:
        return GuardrailResult(answer=SAFE_FALLBACK, safe=False, reasons=reasons)
    return GuardrailResult(answer=answer, safe=True, reasons=[])
