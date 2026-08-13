# Hayder Core — Milestone 1

Hayder Core stores the latest checkpoint for each project and can return the exact next action later.

## What this version does

- `POST /memory/project` — save a project checkpoint
- `GET /continue/{project}?user_id=...` — retrieve the latest checkpoint
- `GET /health` — health check
- Stores an immutable history item every time a checkpoint is saved
- Uses API Gateway HTTP API + Lambda + DynamoDB
- No LLM cost yet

## Prerequisites

- AWS CLI configured
- AWS SAM CLI installed
- Permission to deploy Lambda, API Gateway, DynamoDB, IAM and CloudFormation resources

## Deploy

```bash
cd hayder-core
sam build
sam deploy --guided
```

Suggested stack name:

```text
hayder-core-dev
```

After deployment, copy the `HayderApiUrl` output.

## Test health

```bash
curl "$JARVIS_API_URL/health"
```

Expected:

```json
{"status":"ok","service":"hayder-core"}
```

## Save your first checkpoint

```bash
curl -X POST "$JARVIS_API_URL/memory/project" \
  -H "content-type: application/json" \
  -d @examples/xorwia-checkpoint.json
```

## Continue the project

```bash
curl "$JARVIS_API_URL/continue/xorwia?user_id=avais"
```

Hayder should return the current status, completed items, outstanding items and the exact `next_action`.

## Security note

This first milestone proves the memory contract. Before exposing it publicly for real use, the next milestone should add authentication so `user_id` is taken from the authenticated identity rather than trusted from the request.

## Next milestone

Milestone 2:
1. Authentication
2. AI summary/orchestration layer
3. Approval records
4. Gmail/Calendar/GitHub/AWS read-only connectors
