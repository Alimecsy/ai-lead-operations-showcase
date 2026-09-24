from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class KnowledgeDocument:
    document_id: str
    title: str
    text: str
    tags: tuple[str, ...]


KNOWLEDGE_BASE = (
    KnowledgeDocument(
        document_id="orbitdesk-overview",
        title="OrbitDesk overview",
        text=(
            "OrbitDesk is a fictional workflow hub for boutique service teams. "
            "It connects intake forms, guided conversations, qualification signals, "
            "operator tasks, scheduling, and follow-up in one traceable workflow."
        ),
        tags=("orbitdesk", "workflow", "overview", "intake"),
    ),
    KnowledgeDocument(
        document_id="orbitdesk-human-control",
        title="Human control model",
        text=(
            "The assistant can explain the product and summarize a lead, but it does not "
            "decide commercial eligibility or make promises. Deterministic rules select a "
            "next route, while ambiguous identity and exceptions go to a human operator."
        ),
        tags=("human", "guardrails", "review", "deterministic"),
    ),
    KnowledgeDocument(
        document_id="orbitdesk-integrations",
        title="Integration boundaries",
        text=(
            "CRM, scheduling, and follow-up systems are adapters behind explicit interfaces. "
            "The local lead record and event trail are written first. If an adapter fails, "
            "the workflow keeps its local truth and records a retryable job."
        ),
        tags=("crm", "scheduling", "email", "reliability", "retry"),
    ),
    KnowledgeDocument(
        document_id="orbitdesk-demo",
        title="Demo environment",
        text=(
            "The public demo uses synthetic people and mock adapters. No external account is "
            "needed to run the intake, routing, task creation, booking handoff, or human-review "
            "paths."
        ),
        tags=("demo", "synthetic", "mock", "portfolio"),
    ),
)


def retrieve(query: str, *, limit: int = 3) -> list[KnowledgeDocument]:
    terms = {term.lower() for term in query.split() if len(term) > 2}
    scored: list[tuple[int, KnowledgeDocument]] = []
    for document in KNOWLEDGE_BASE:
        haystack = f"{document.title} {document.text} {' '.join(document.tags)}".lower()
        score = sum(1 for term in terms if term in haystack)
        if score:
            scored.append((score, document))
    scored.sort(key=lambda item: (-item[0], item[1].document_id))
    return [document for _, document in scored[:limit]]
