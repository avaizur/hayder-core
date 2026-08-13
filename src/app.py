import json
import os
import re
import urllib.error
import urllib.request
from datetime import datetime, timezone
from urllib.parse import unquote

import boto3


TABLE_NAME = os.environ["HAYDER_TABLE"]
OPENAI_SECRET_NAME = os.environ.get(
    "OPENAI_SECRET_NAME",
    "hayder/openai-api-key",
)
OPENAI_MODEL = os.environ.get(
    "OPENAI_MODEL",
    "gpt-5.6-luna",
)

table = boto3.resource("dynamodb").Table(TABLE_NAME)
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
        field
        for field in required
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
        "completed": payload.get(
            "completed",
            [],
        ),
        "outstanding": payload.get(
            "outstanding",
            [],
        ),
        "next_action": payload["next_action"],
        "decisions": payload.get(
            "decisions",
            [],
        ),
        "people": payload.get(
            "people",
            [],
        ),
        "links": payload.get(
            "links",
            [],
        ),
        "updated_at": timestamp,
    }

    history_item = {
        **item,
        "record_key": (
            f"HISTORY#{project}#{timestamp}"
        ),
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

    item = get_project_record(
        user_id,
        project,
    )

    if not item:
        return response(
            404,
            {
                "error": (
                    "No checkpoint found for "
                    f"project '{project}'"
                )
            },
        )

    return response(
        200,
        {
            "project": item["project"],
            "status": item["status"],
            "summary": item["summary"],
            "completed": item.get(
                "completed",
                [],
            ),
            "outstanding": item.get(
                "outstanding",
                [],
            ),
            "next_action": item[
                "next_action"
            ],
            "decisions": item.get(
                "decisions",
                [],
            ),
            "people": item.get(
                "people",
                [],
            ),
            "updated_at": item[
                "updated_at"
            ],
        },
    )


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


def build_project_context(
    user_id,
    message,
):
    project = detect_project(message)

    if not project:
        return None, ""

    item = get_project_record(
        user_id,
        project,
    )

    if not item:
        return project, (
            f"The user mentioned project "
            f"'{project}', but Hayder currently "
            "has no saved checkpoint for it."
        )

    context = {
        "project": item.get("project"),
        "status": item.get("status"),
        "summary": item.get("summary"),
        "completed": item.get(
            "completed",
            [],
        ),
        "outstanding": item.get(
            "outstanding",
            [],
        ),
        "next_action": item.get(
            "next_action",
        ),
        "decisions": item.get(
            "decisions",
            [],
        ),
        "people": item.get(
            "people",
            [],
        ),
        "updated_at": item.get(
            "updated_at",
        ),
    }

    return project, json.dumps(
        context,
        default=str,
    )


def extract_openai_text(data):
    output_text = data.get("output_text")

    if output_text:
        return output_text

    output = data.get("output", [])

    text_parts = []

    for item in output:
        if item.get("type") != "message":
            continue

        for content in item.get(
            "content",
            [],
        ):
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

    system_instructions = """
You are Hayder, a secure personal AI operations assistant.

Your job is to help the authenticated user run projects,
business work and day-to-day operational tasks.

Important rules:

1. Use saved project memory when it is provided.
2. When asked to continue a project, clearly state:
   - where the project currently stands,
   - what is already completed,
   - what is outstanding,
   - the recommended next action.
3. Never claim an external action has been performed unless
   Hayder actually executed it through an approved tool.
4. Production deployments, sending messages, purchases,
   deletions, security changes and other important write
   actions must require explicit user approval.
5. Be concise, practical and action-oriented.
6. The assistant's name is Hayder.
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
        "instructions": system_instructions,
        "input": input_text,
        "reasoning": {
            "effort": "low"
        },
    }

    request = urllib.request.Request(
        "https://api.openai.com/v1/responses",
        data=json.dumps(payload).encode(
            "utf-8"
        ),
        headers={
            "Authorization": (
                f"Bearer {api_key}"
            ),
            "Content-Type": (
                "application/json"
            ),
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
        print(
            "[OPENAI EMPTY RESPONSE]",
            raw,
        )

        raise RuntimeError(
            "OpenAI returned no text response"
        )

    return text


def chat(user_id, payload):
    message = payload.get("message")

    if not message:
        return response(
            400,
            {
                "error": (
                    "message is required"
                )
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
                    "Hayder could not reach "
                    "the AI service"
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
                    "Authenticated user "
                    "not found"
                )
            },
        )

    if (
        method == "POST"
        and path == "/memory/project"
    ):
        try:
            payload = get_body(event)

            return save_checkpoint(
                payload,
                user_id,
            )

        except json.JSONDecodeError:
            return response(
                400,
                {
                    "error": (
                        "Invalid JSON body"
                    )
                },
            )

    if (
        method == "GET"
        and path.startswith(
            "/continue/"
        )
    ):
        project = unquote(
            path.split(
                "/continue/",
                1,
            )[1]
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
            payload = get_body(event)

            return chat(
                user_id,
                payload,
            )

        except json.JSONDecodeError:
            return response(
                400,
                {
                    "error": (
                        "Invalid JSON body"
                    )
                },
            )

    return response(
        404,
        {
            "error": "Route not found"
        },
    )
