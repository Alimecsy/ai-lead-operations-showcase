from __future__ import annotations

from dataclasses import dataclass

from .guardrails import guard_answer
from .knowledge import KnowledgeDocument, retrieve


@dataclass(frozen=True)
class AssistantDraft:
    answer: str
    sources: list[KnowledgeDocument]
    safe: bool
    guardrail_reasons: list[str]


class GroundedAssistant:
    """Local stand-in for a model-backed assistant with retrieval and guardrails."""

    def draft(self, message: str) -> AssistantDraft:
        documents = retrieve(message)
        if documents:
            answer = (
                f"{documents[0].text} "
                "I can explain the workflow or pass a specific case to a human operator."
            )
            evidence = [document.text for document in documents]
        else:
            answer = (
                "I can help explain the fictional product workflow. For a case-specific decision, "
                "the operator review path is the safe next step."
            )
            evidence = []
        guarded = guard_answer(answer, evidence)
        return AssistantDraft(
            answer=guarded.answer,
            sources=documents,
            safe=guarded.safe,
            guardrail_reasons=guarded.reasons,
        )
