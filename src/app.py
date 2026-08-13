import json
import os
import re
import uuid
import urllib.error
import urllib.request
from datetime import datetime, timezone
from urllib.parse import unquote

import boto3


TABLE_NAME = os.environ["HAYDER_TABLE"]
APPROVAL_TABLE_NAME = os.environ["HAYDER_APPROVAL_TABLE"]

OPENAI_SECRET_NAME = os.environ.get(
    "OPENAI_SECRET_NAME",
    "hayder/openai-api-key",
)

OPENAI_MODEL = os.environ.get(
    "OPENAI_MODEL",
    "gpt-5.6-luna",
)

table = boto3.resource("dynamodb").Table(TABLE_NAME)
approval_table = boto3.resource("dynamodb").Table(APPROVAL_TABLE_NAME)

secrets_client = boto3.client("secretsmanager")

_openai_api_key = None


def response(status_code, body):
    return {
        "statusCode": status_code,
        "headers": {
            "content-type": "application/json",
        },
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


def get_authenticated_user(event):
    claims = (
        event.get("requestContext", {})
        .get("authorizer", {})
        .get("jwt", {})
        .get("claims", {})
    )

    return claims.get("email") or claims.get("sub")


def get_openai_api_key():
    global _openai_api_key

    if _openai_api_key:
        return _openai_api_key

    result = secrets_client.get_secret_value(
        SecretId=OPENAI_SECRET_NAME
    )

    secret = result.get("SecretString")

    if not secret:
        raise RuntimeError(
            "OpenAI API key was not found in Secrets Manager"
        )

    _openai_api_key = secret.strip()
    return _openai_api_key


def save_checkpoint(payload, user_id):
    required = [
        "project",
        "status",
        "summary",
        "next_action",
    ]

    missing = [
        field for field in required
        if not payload.get(field)
    ]

    if missing:
        return response(
            400,
            {
                "error": (
                    "Missing required fields: "
                    + ", ".join(missing)
                )
            },
        )

    project = normalise_project_name(
        payload["project"]
    )

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


def get_project_record(user_id, project):
    project = normalise_project_name(project)

    result = table.get_item(
        Key={
            "user_id": user_id,
            "record_key": f"PROJECT#{project}",
        }
    )

    return result.get("Item")


def continue_project(user_id, project):
    project = normalise_project_name(project)

    item = get_project_record(user_id, project)

    if not item:
        return response(
            404,
            {
                "error": (
                    f"No checkpoint found for project '{project}'"
                )
            },
        )

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


def create_approval_record(
    user_id,
    action_type,
    target,
    summary,
    details=None,
):
    approval_id = str(uuid.uuid4())
    timestamp = now_iso()

    item = {
        "user_id": user_id,
        "approval_id": approval_id,
        "action_type": action_type,
        "target": target,
        "summary": summary,
        "details": details or {},
        "status": "WAITING_APPROVAL",
        "created_at": timestamp,
        "updated_at": timestamp,
        "approved_at": None,
        "rejected_at": None,
        "executed_at": None,
    }

    approval_table.put_item(Item=item)

    return item


def create_approval(user_id, payload):
    required = [
        "action_type",
        "target",
        "summary",
    ]

    missing = [
        field for field in required
        if not payload.get(field)
    ]

    if missing:
        return response(
            400,
            {
                "error": (
                    "Missing required fields: "
                    + ", ".join(missing)
                )
            },
        )

    allowed_action_types = {
        "aws_change",
        "git_change",
        "email_send",
        "deployment",
        "delete",
        "purchase",
    }

    action_type = payload["action_type"]

    if action_type not in allowed_action_types:
        return response(
            400,
            {
                "error": "Unsupported action_type",
                "allowed": sorted(allowed_action_types),
            },
        )

    item = create_approval_record(
        user_id=user_id,
        action_type=action_type,
        target=payload["target"],
        summary=payload["summary"],
        details=payload.get("details", {}),
    )

    return response(
        201,
        {
            "message": "Approval request created",
            "approval_id": item["approval_id"],
            "status": item["status"],
            "action_type": item["action_type"],
            "target": item["target"],
            "summary": item["summary"],
        },
    )


def update_approval_status(
    user_id,
    approval_id,
    new_status,
):
    now = now_iso()

    timestamp_field = (
        "approved_at"
        if new_status == "APPROVED"
        else "rejected_at"
    )

    try:
        result = approval_table.update_item(
            Key={
                "user_id": user_id,
                "approval_id": approval_id,
            },
            UpdateExpression=(
                "SET #status = :new_status, "
                "#updated_at = :now, "
                f"#{timestamp_field} = :now"
            ),
            ConditionExpression=(
                "attribute_exists(approval_id) "
                "AND #status = :waiting"
            ),
            ExpressionAttributeNames={
                "#status": "status",
                "#updated_at": "updated_at",
                f"#{timestamp_field}": timestamp_field,
            },
            ExpressionAttributeValues={
                ":new_status": new_status,
                ":waiting": "WAITING_APPROVAL",
                ":now": now,
            },
            ReturnValues="ALL_NEW",
        )

    except approval_table.meta.client.exceptions.ConditionalCheckFailedException:
        existing = approval_table.get_item(
            Key={
                "user_id": user_id,
                "approval_id": approval_id,
            }
        ).get("Item")

        if not existing:
            return None, "NOT_FOUND"

        return existing, "ALREADY_CHANGED"

    return result["Attributes"], None


def detect_project(message):
    text = message.strip().lower()

    known_projects = [
        "xorwia",
        "hayder",
    ]

    for project in known_projects:
        if project in text:
            return project

    patterns = [
        r"continue\s+([a-zA-Z0-9_-]+)",
        r"project\s+([a-zA-Z0-9_-]+)",
        r"working\s+on\s+([a-zA-Z0-9_-]+)",
    ]

    for pattern in patterns:
        match = re.search(
            pattern,
            text,
            re.IGNORECASE,
        )

        if match:
            return normalise_project_name(
                match.group(1)
            )

    return None


def build_project_context(user_id, message):
    project = detect_project(message)

    if not project:
        return None, ""

    item = get_project_record(
        user_id,
        project,
    )

    if not item:
        return project, (
            f"The user mentioned project '{project}', "
            "but Hayder currently has no saved checkpoint for it."
        )

    context = {
        "project": item.get("project"),
        "status": item.get("status"),
        "summary": item.get("summary"),
        "completed": item.get("completed", []),
        "outstanding": item.get("outstanding", []),
        "next_action": item.get("next_action"),
        "decisions": item.get("decisions", []),
        "people": item.get("people", []),
        "updated_at": item.get("updated_at"),
    }

    return project, json.dumps(
        context,
        default=str,
    )


def detect_sensitive_action(message):
    text = message.lower()

    rules = [
        (
            "deployment",
            [
                "deploy ",
                "deploy to ",
                "release to ",
                "promote to ",
            ],
        ),
        (
            "email_send",
            [
                "send email",
                "send the email",
                "email this",
                "send message",
                "send the message",
            ],
        ),
        (
            "delete",
            [
                "delete ",
                "remove permanently",
                "destroy ",
            ],
        ),
        (
            "purchase",
            [
                "buy ",
                "purchase ",
                "pay for ",
            ],
        ),
        (
            "aws_change",
            [
                "change aws",
                "update iam",
                "change iam",
                "modify security group",
                "create aws",
                "terminate instance",
            ],
        ),
        (
            "git_change",
            [
                "push to git",
                "push to github",
                "merge ",
                "commit and push",
            ],
        ),
    ]

    for action_type, phrases in rules:
        for phrase in phrases:
            if phrase in text:
                project = detect_project(message)

                target = project or "unspecified"

                return {
                    "action_type": action_type,
                    "target": target,
                    "summary": message.strip(),
                }

    return None


def detect_approval_command(message):
    text = message.strip()

    approve_match = re.match(
        r"^approve\s+([0-9a-fA-F-]{36})$",
        text,
        re.IGNORECASE,
    )

    if approve_match:
        return (
            "APPROVED",
            approve_match.group(1),
        )

    reject_match = re.match(
        r"^reject\s+([0-9a-fA-F-]{36})$",
        text,
        re.IGNORECASE,
    )

    if reject_match:
        return (
            "REJECTED",
            reject_match.group(1),
        )

    return None


def extract_openai_text(data):
    output_text = data.get("output_text")

    if output_text:
        return output_text

    text_parts = []

    for item in data.get("output", []):
        if item.get("type") != "message":
            continue

        for content in item.get("content", []):
            if content.get("type") == "output_text":
                text = content.get("text")

                if text:
                    text_parts.append(text)

    return "\n".join(text_parts).strip()


def call_openai(
    user_message,
    project_context="",
):
    api_key = get_openai_api_key()

    instructions = """
You are Hayder, a secure personal AI operations assistant.

Help the authenticated user manage projects, business work,
technical work and day-to-day operations.

Rules:

1. Use saved Hayder memory when supplied.
2. Never claim an external action happened unless an executor
   actually performed it.
3. Deployments, sending messages, purchases, deletions,
   security changes, AWS write changes and Git write changes
   require explicit approval.
4. Approval does not mean execution. It only grants permission
   for a future executor.
5. Be concise, practical and action-oriented.
6. Your name is Hayder.
"""

    if project_context:
        input_text = (
            f"USER MESSAGE:\n{user_message}\n\n"
            "SAVED HAYDER PROJECT MEMORY:\n"
            f"{project_context}"
        )
    else:
        input_text = (
            f"USER MESSAGE:\n{user_message}"
        )

    payload = {
        "model": OPENAI_MODEL,
        "instructions": instructions,
        "input": input_text,
        "reasoning": {
            "effort": "low"
        },
    }

    request = urllib.request.Request(
        "https://api.openai.com/v1/responses",
        data=json.dumps(payload).encode("utf-8"),
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        },
        method="POST",
    )

    try:
        with urllib.request.urlopen(
            request,
            timeout=25,
        ) as api_response:
            raw = api_response.read().decode(
                "utf-8"
            )

    except urllib.error.HTTPError as exc:
        error_body = exc.read().decode(
            "utf-8",
            errors="replace",
        )

        print(
            "[OPENAI HTTP ERROR]",
            exc.code,
            error_body,
        )

        raise RuntimeError(
            f"OpenAI returned HTTP {exc.code}"
        )

    except urllib.error.URLError as exc:
        print(
            "[OPENAI CONNECTION ERROR]",
            str(exc),
        )

        raise RuntimeError(
            "Unable to connect to OpenAI"
        )

    data = json.loads(raw)

    text = extract_openai_text(data)

    if not text:
        raise RuntimeError(
            "OpenAI returned no text response"
        )

    return text


def chat(user_id, payload):
    message = payload.get("message")

    if not message:
        return response(
            400,
            {"error": "message is required"},
        )

    approval_command = detect_approval_command(
        message
    )

    if approval_command:
        new_status, approval_id = (
            approval_command
        )

        item, error = update_approval_status(
            user_id,
            approval_id,
            new_status,
        )

        if error == "NOT_FOUND":
            return response(
                404,
                {
                    "assistant": "Hayder",
                    "reply": (
                        "I could not find that approval request."
                    ),
                },
            )

        if error == "ALREADY_CHANGED":
            return response(
                409,
                {
                    "assistant": "Hayder",
                    "approval_id": approval_id,
                    "status": item.get("status"),
                    "reply": (
                        "That approval request has already "
                        f"been {item.get('status')}."
                    ),
                },
            )

        return response(
            200,
            {
                "assistant": "Hayder",
                "approval_id": approval_id,
                "status": item["status"],
                "reply": (
                    f"Approval {approval_id} is now "
                    f"{item['status']}. "
                    "No external action has been executed yet."
                ),
            },
        )

    sensitive_action = detect_sensitive_action(
        message
    )

    if sensitive_action:
        item = create_approval_record(
            user_id=user_id,
            action_type=sensitive_action[
                "action_type"
            ],
            target=sensitive_action[
                "target"
            ],
            summary=sensitive_action[
                "summary"
            ],
            details={
                "source": "chat",
                "original_message": message,
            },
        )

        return response(
            200,
            {
                "assistant": "Hayder",
                "approval_required": True,
                "approval_id": item[
                    "approval_id"
                ],
                "status": item["status"],
                "action_type": item[
                    "action_type"
                ],
                "target": item["target"],
                "reply": (
                    "This action requires your approval. "
                    "I created approval request "
                    f"{item['approval_id']}. "
                    "No external action has been performed. "
                    "To approve it, say: "
                    f"Approve {item['approval_id']}"
                ),
            },
        )

    project, project_context = (
        build_project_context(
            user_id,
            message,
        )
    )

    try:
        reply = call_openai(
            message,
            project_context,
        )

    except Exception as exc:
        print(
            "[HAYDER CHAT ERROR]",
            str(exc),
        )

        return response(
            502,
            {
                "error": (
                    "Hayder could not reach the AI service"
                )
            },
        )

    return response(
        200,
        {
            "assistant": "Hayder",
            "model": OPENAI_MODEL,
            "project": project,
            "reply": reply,
        },
    )


def lambda_handler(event, context):
    request_context = event.get(
        "requestContext",
        {},
    )

    http = request_context.get(
        "http",
        {},
    )

    method = http.get(
        "method",
        "",
    )

    path = event.get(
        "rawPath",
        "",
    )

    path_parameters = event.get(
        "pathParameters",
        {},
    ) or {}

    if (
        method == "GET"
        and path == "/health"
    ):
        return response(
            200,
            {
                "status": "ok",
                "service": "hayder-core",
            },
        )

    user_id = get_authenticated_user(
        event
    )

    if not user_id:
        return response(
            401,
            {
                "error": (
                    "Authenticated user not found"
                )
            },
        )

    if (
        method == "POST"
        and path == "/memory/project"
    ):
        try:
            return save_checkpoint(
                get_body(event),
                user_id,
            )

        except json.JSONDecodeError:
            return response(
                400,
                {"error": "Invalid JSON body"},
            )

    if (
        method == "GET"
        and path.startswith("/continue/")
    ):
        project = unquote(
            path.split("/continue/", 1)[1]
        )

        return continue_project(
            user_id,
            project,
        )

    if (
        method == "POST"
        and path == "/chat"
    ):
        try:
            return chat(
                user_id,
                get_body(event),
            )

        except json.JSONDecodeError:
            return response(
                400,
                {"error": "Invalid JSON body"},
            )

    if (
        method == "POST"
        and path == "/approval/create"
    ):
        try:
            return create_approval(
                user_id,
                get_body(event),
            )

        except json.JSONDecodeError:
            return response(
                400,
                {"error": "Invalid JSON body"},
            )

    if (
        method == "POST"
        and path.endswith("/approve")
        and "/approval/" in path
    ):
        approval_id = path_parameters.get(
            "approval_id"
        )

        item, error = update_approval_status(
            user_id,
            approval_id,
            "APPROVED",
        )

        if error:
            return response(
                409 if item else 404,
                {
                    "error": error,
                    "current_status": (
                        item.get("status")
                        if item
                        else None
                    ),
                },
            )

        return response(
            200,
            {
                "approval_id": approval_id,
                "status": item["status"],
                "summary": item["summary"],
            },
        )

    if (
        method == "POST"
        and path.endswith("/reject")
        and "/approval/" in path
    ):
        approval_id = path_parameters.get(
            "approval_id"
        )

        item, error = update_approval_status(
            user_id,
            approval_id,
            "REJECTED",
        )

        if error:
            return response(
                409 if item else 404,
                {
                    "error": error,
                    "current_status": (
                        item.get("status")
                        if item
                        else None
                    ),
                },
            )

        return response(
            200,
            {
                "approval_id": approval_id,
                "status": item["status"],
                "summary": item["summary"],
            },
        )

    return response(
        404,
        {"error": "Route not found"},
    )
