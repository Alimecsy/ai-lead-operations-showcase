# Demo walkthrough

Run:

```bash
python -m lead_ops.demo
```

The output contains two useful views of the same workflow:

1. `before_retry` shows the synthetic scenario results and the first adapter attempt.
2. `sales_after_retry` shows the same local lead after retrying the injected CRM failure.

Look for these signals:

- `sales`, `nurture`, and `educate` are selected by deterministic rules;
- the identity conflict has route `review` and a `human_review` job;
- the chat response contains retrieval source identifiers;
- the failed CRM job keeps its lead qualification and later becomes `succeeded`;
- the event trail explains the order of intake, route selection, queuing, failure, and recovery.

## API walkthrough

Start the API with:

```bash
uvicorn lead_ops.main:app --reload
```

Then call `POST /assessment`, save the returned `lead_id`, inspect `GET /leads/{lead_id}`, and use `POST /leads/{lead_id}/retry` for any failed job.
