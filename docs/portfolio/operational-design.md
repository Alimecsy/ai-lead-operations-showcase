# Operational design notes

## What if an external service fails?

The local lead record and event are written before an adapter runs. A failed adapter job stores its error and attempt count. Retrying the lead reuses the same explicit boundary and records a success event if the downstream action recovers. Repeated failure produces an operator-attention event.

## What if identity is ambiguous?

Email and phone values are normalized before matching. If they point to different records, the system creates a separate review record instead of merging data or sending the case to downstream systems. A human-review job explains which records need resolution.

## What should AI decide?

The assistant can retrieve fictional product information, summarize the workflow, and answer general questions. It cannot select a sales route, claim an outcome, invent a price, or make an identity merge.

## What is an automated component allowed to do?

The demo may create local state, append events, queue mock adapter work, and retry failed mock work. It cannot contact a real person or external vendor because all adapters are local.

## How is human activity distinguished from synthetic monitoring?

The workflow accepts provenance as an internal service concern. The API defaults to `human`; the demo harness explicitly marks its fixtures as `synthetic`. Provenance is stored alongside the lead and adapter payloads.

Chat and assessment are visitor-facing routes. Lead inspection and retry are operator routes and can require `SHOWCASE_OPERATOR_TOKEN`, keeping the authentication boundary explicit without forcing credentials into the demo.

## How can an operator reconstruct what happened?

Each lead has a reference, qualification record, event trail, and integration jobs. Together they show the input, route, downstream attempts, failure reason, and recovery state without requiring access to an external vendor account.
