# Architecture and workflow

## Runtime flow

```mermaid
sequenceDiagram
    participant V as Visitor
    participant API as Intake API
    participant ID as Identity resolver
    participant DB as SQLite state
    participant Q as Qualification rules
    participant A as Adapter runner
    participant H as Human operator

    V->>API: Chat or assessment
    API->>ID: Normalize identity signals
    ID->>DB: Match, create, or flag conflict
    API->>DB: Append intake event
    API->>Q: Evaluate assessment inputs
    Q->>DB: Persist score and route
    DB->>A: Queue CRM / booking / follow-up job
    A->>DB: Record success or retryable failure
    ID-->>H: Ambiguous identity review
    A-->>H: Operator task or attention event
```

## Boundaries

The assistant and retrieval layer are advisory. Qualification, identity conflict handling, feature flags, persistence, and retry state are deterministic. External systems are represented by adapters so the local workflow can be tested without credentials.
