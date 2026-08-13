import json
import os
from datetime import datetime, timezone
from urllib.parse import unquote

import boto3

TABLE_NAME = os.environ["HAYDER_TABLE"]
table = boto3.resource("dynamodb").Table(TABLE_NAME)


def response(status_code, body):
    return {
        "statusCode": status_code,
        "headers": {"content-type": "application/json"},
        "body": json.dumps(body, default=str),
    }


def now_iso():
    return datetime.now(timezone.utc).isoformat()


def normalise_project_name(name):
    return name.strip().lower().replace(" ", "-")


def get_body(event):
    raw = event.get("body") or "{}"
    if event.get("isBase64Encoded"):
        import base64
        raw = base64.b64decode(raw).decode("utf-8")
    return json.loads(raw)


def save_checkpoint(payload):
    required = ["user_id", "project", "status", "summary", "next_action"]
    missing = [field for field in required if not payload.get(field)]
    if missing:
        return response(400, {"error": f"Missing required fields: {', '.join(missing)}"})

    user_id = payload["user_id"].strip().lower()
    project = normalise_project_name(payload["project"])
    timestamp = now_iso()

    item = {
        "user_id": user_id,
        "record_key": f"PROJECT#{project}",
        "project": project,
        "status": payload["status"],
        "summary": payload["summary"],
        "completed": payload.get("completed", []),
        "outstanding": payload.get("outstanding", []),
        "next_action": payload["next_action"],
        "decisions": payload.get("decisions", []),
        "people": payload.get("people", []),
        "links": payload.get("links", []),
        "updated_at": timestamp,
    }

    history_item = {
        **item,
        "record_key": f"HISTORY#{project}#{timestamp}",
    }

    table.put_item(Item=item)
    table.put_item(Item=history_item)

    return response(
        201,
        {
            "message": "Checkpoint saved",
            "project": project,
            "updated_at": timestamp,
            "next_action": item["next_action"],
        },
    )


def continue_project(user_id, project):
    project = normalise_project_name(project)
    result = table.get_item(
        Key={
            "user_id": user_id.strip().lower(),
            "record_key": f"PROJECT#{project}",
        }
    )
    item = result.get("Item")

    if not item:
        return response(404, {"error": f"No checkpoint found for project '{project}'"})

    return response(
        200,
        {
            "project": item["project"],
            "status": item["status"],
            "summary": item["summary"],
            "completed": item.get("completed", []),
            "outstanding": item.get("outstanding", []),
            "next_action": item["next_action"],
            "decisions": item.get("decisions", []),
            "people": item.get("people", []),
            "updated_at": item["updated_at"],
        },
    )


def lambda_handler(event, context):
    request_context = event.get("requestContext", {})
    http = request_context.get("http", {})
    method = http.get("method", "")
    path = event.get("rawPath", "")

    if method == "GET" and path == "/health":
        return response(200, {"status": "ok", "service": "hayder-core"})

    if method == "POST" and path == "/memory/project":
        try:
            return save_checkpoint(get_body(event))
        except json.JSONDecodeError:
            return response(400, {"error": "Invalid JSON body"})

    if method == "GET" and path.startswith("/continue/"):
        project = unquote(path.split("/continue/", 1)[1])
        query = event.get("queryStringParameters") or {}
        user_id = query.get("user_id")
        if not user_id:
            return response(400, {"error": "user_id query parameter is required"})
        return continue_project(user_id, project)

    return response(404, {"error": "Route not found"})
