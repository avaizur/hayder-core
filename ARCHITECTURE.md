# Hayder Core Architecture

```text
User
 |
 v
API Gateway HTTP API
 |
 v
Lambda: hayder-core
 |
 +--> DynamoDB
      PK: user_id
      SK: record_key

Latest record:
  PROJECT#xorwia

History records:
  HISTORY#xorwia#<timestamp>
```

The latest record makes `/continue` fast. History records preserve what changed over time.

## Approval principle

Read-only retrieval can eventually be automatic.
Writes to external systems, production deployments, sending messages, purchases, deletions and security changes should require explicit approval.
