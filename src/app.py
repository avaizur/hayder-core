import base64
import hashlib
import hmac
import json
import os
import re
import time
import uuid
import urllib.error
import urllib.request

from datetime import datetime, timezone
from urllib.parse import (
    parse_qs,
    quote,
    unquote,
    urlencode,
)

import boto3

from intent import resolve_intent
from attention import important_summary
from calendar_tool import (
    calendar_events,
    spoken_calendar_summary,
    event_time_text,
    event_minutes_from_now,
)
from attention_memory import configure, parse_preference_command, save_preference


TABLE_NAME = os.environ["HAYDER_TABLE"]
APPROVAL_TABLE_NAME = os.environ["HAYDER_APPROVAL_TABLE"]

HAYDER_FUNCTION_NAME = os.environ["AWS_LAMBDA_FUNCTION_NAME"]

OPENAI_SECRET_NAME = os.environ.get(
    "OPENAI_SECRET_NAME",
    "hayder/openai-api-key",
)

OPENAI_MODEL = os.environ.get(
    "OPENAI_MODEL",
    "gpt-5.6-luna",
)

GOOGLE_CLIENT_ID_SECRET = os.environ.get(
    "GOOGLE_CLIENT_ID_SECRET",
    "hayder/google/client-id",
)

GOOGLE_CLIENT_SECRET_SECRET = os.environ.get(
    "GOOGLE_CLIENT_SECRET_SECRET",
    "hayder/google/client-secret",
)

GOOGLE_ACCOUNT_LIMITS = {
    "basic": int(
        os.environ.get(
            "HAYDER_GOOGLE_LIMIT_BASIC",
            "1",
        )
    ),
    "pro": int(
        os.environ.get(
            "HAYDER_GOOGLE_LIMIT_PRO",
            "3",
        )
    ),
    "business": int(
        os.environ.get(
            "HAYDER_GOOGLE_LIMIT_BUSINESS",
            "10",
        )
    ),
}


GOOGLE_SCOPE = (
    "https://www.googleapis.com/auth/gmail.readonly "
    "https://www.googleapis.com/auth/calendar.events.readonly"
)

GOOGLE_AUTH_URL = (
    "https://accounts.google.com/o/oauth2/v2/auth"
)

GOOGLE_TOKEN_URL = (
    "https://oauth2.googleapis.com/token"
)

GMAIL_BASE_URL = (
    "https://gmail.googleapis.com/gmail/v1"
)


dynamodb = boto3.resource("dynamodb")

table = dynamodb.Table(TABLE_NAME)

configure(TABLE_NAME)

approval_table = dynamodb.Table(
    APPROVAL_TABLE_NAME
)

secrets_client = boto3.client(
    "secretsmanager"
)

lambda_client = boto3.client(
    "lambda"
)


_secret_cache = {}


# ------------------------------------------------
# BASIC HELPERS
# ------------------------------------------------

def response(
    status_code,
    body,
    headers=None,
):
    final_headers = {
        "content-type": "application/json",
    }

    if headers:
        final_headers.update(headers)

    return {
        "statusCode": status_code,
        "headers": final_headers,
        "body": (
            body
            if isinstance(body, str)
            else json.dumps(
                body,
                default=str,
            )
        ),
    }


def now_iso():
    return datetime.now(
        timezone.utc
    ).isoformat()


def normalise_project_name(name):
    return (
        name.strip()
        .lower()
        .replace(" ", "-")
    )


def get_body(event):

    raw = event.get("body") or "{}"

    if event.get("isBase64Encoded"):

        raw = base64.b64decode(
            raw
        ).decode("utf-8")

    return json.loads(raw)


def get_authenticated_user(event):

    claims = (
        event.get(
            "requestContext",
            {},
        )
        .get(
            "authorizer",
            {},
        )
        .get(
            "jwt",
            {},
        )
        .get(
            "claims",
            {},
        )
    )

    return (
        claims.get("email")
        or claims.get("sub")
    )


def get_secret(secret_name):

    if secret_name in _secret_cache:
        return _secret_cache[
            secret_name
        ]

    result = (
        secrets_client
        .get_secret_value(
            SecretId=secret_name
        )
    )

    value = result.get(
        "SecretString"
    )

    if not value:
        raise RuntimeError(
            f"Secret {secret_name} is empty"
        )

    _secret_cache[
        secret_name
    ] = value.strip()

    return value.strip()


def get_openai_api_key():

    return get_secret(
        OPENAI_SECRET_NAME
    )


def get_google_credentials():

    client_id = get_secret(
        GOOGLE_CLIENT_ID_SECRET
    )

    client_secret = get_secret(
        GOOGLE_CLIENT_SECRET_SECRET
    )

    return (
        client_id,
        client_secret,
    )


def get_api_origin(event):

    domain = (
        event.get(
            "requestContext",
            {}
        )
        .get(
            "domainName"
        )
    )

    if not domain:
        raise RuntimeError(
            "API domain not found"
        )

    return f"https://{domain}"


def google_redirect_uri(event):

    return (
        get_api_origin(event)
        + "/oauth/google/callback"
    )


# ------------------------------------------------
# PROJECT MEMORY
# ------------------------------------------------

def save_checkpoint(
    payload,
    user_id,
):

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
                "error":
                "Missing required fields: "
                + ", ".join(missing)
            },
        )

    project = normalise_project_name(
        payload["project"]
    )

    timestamp = now_iso()

    item = {
        "user_id": user_id,
        "record_key":
            f"PROJECT#{project}",
        "project": project,
        "status": payload["status"],
        "summary": payload["summary"],
        "completed":
            payload.get(
                "completed",
                [],
            ),
        "outstanding":
            payload.get(
                "outstanding",
                [],
            ),
        "next_action":
            payload["next_action"],
        "decisions":
            payload.get(
                "decisions",
                [],
            ),
        "people":
            payload.get(
                "people",
                [],
            ),
        "links":
            payload.get(
                "links",
                [],
            ),
        "updated_at": timestamp,
    }

    history_item = {
        **item,
        "record_key":
            f"HISTORY#{project}#{timestamp}",
    }

    table.put_item(
        Item=item
    )

    table.put_item(
        Item=history_item
    )

    return response(
        201,
        {
            "message":
                "Checkpoint saved",
            "project": project,
            "updated_at":
                timestamp,
            "next_action":
                item["next_action"],
        },
    )


def get_project_record(
    user_id,
    project,
):

    project = normalise_project_name(
        project
    )

    result = table.get_item(
        Key={
            "user_id": user_id,
            "record_key":
                f"PROJECT#{project}",
        }
    )

    return result.get("Item")


def continue_project(
    user_id,
    project,
):

    project = normalise_project_name(
        project
    )

    item = get_project_record(
        user_id,
        project,
    )

    if not item:

        return response(
            404,
            {
                "error":
                    "No checkpoint found "
                    f"for project '{project}'"
            },
        )

    return response(
        200,
        {
            "project":
                item["project"],
            "status":
                item["status"],
            "summary":
                item["summary"],
            "completed":
                item.get(
                    "completed",
                    [],
                ),
            "outstanding":
                item.get(
                    "outstanding",
                    [],
                ),
            "next_action":
                item[
                    "next_action"
                ],
            "decisions":
                item.get(
                    "decisions",
                    [],
                ),
            "people":
                item.get(
                    "people",
                    [],
                ),
            "updated_at":
                item[
                    "updated_at"
                ],
        },
    )


# ------------------------------------------------
# AWS READ-ONLY TOOL
# ------------------------------------------------

def get_hayder_lambda_status():

    result = (
        lambda_client
        .get_function_configuration(
            FunctionName=
                HAYDER_FUNCTION_NAME
        )
    )

    return {
        "function":
            result.get(
                "FunctionName"
            ),
        "runtime":
            result.get(
                "Runtime"
            ),
        "memory_mb":
            result.get(
                "MemorySize"
            ),
        "timeout_seconds":
            result.get(
                "Timeout"
            ),
        "state":
            result.get(
                "State"
            ),
        "last_modified":
            result.get(
                "LastModified"
            ),
        "version":
            result.get(
                "Version"
            ),
    }


def detect_aws_read_request(
    message
):

    text = message.lower()

    phrases = [
        "check your lambda",
        "check hayder lambda",
        "check lambda status",
        "what is your lambda status",
        "show your lambda status",
        "check your aws",
    ]

    return any(
        phrase in text
        for phrase in phrases
    )


# ------------------------------------------------
# GOOGLE OAUTH
# ------------------------------------------------

def b64url_encode(data):

    return (
        base64.urlsafe_b64encode(
            data
        )
        .decode("utf-8")
        .rstrip("=")
    )


def b64url_decode(text):

    padding = (
        "="
        * (-len(text) % 4)
    )

    return base64.urlsafe_b64decode(
        text + padding
    )


def create_google_state(
    user_id
):

    _, client_secret = (
        get_google_credentials()
    )

    payload = {
        "u": user_id,
        "t": int(time.time()),
        "n": uuid.uuid4().hex,
    }

    payload_bytes = json.dumps(
        payload,
        separators=(",", ":"),
    ).encode("utf-8")

    encoded = b64url_encode(
        payload_bytes
    )

    signature = hmac.new(
        client_secret.encode(
            "utf-8"
        ),
        encoded.encode(
            "utf-8"
        ),
        hashlib.sha256,
    ).digest()

    return (
        encoded
        + "."
        + b64url_encode(
            signature
        )
    )


def verify_google_state(
    state
):

    try:

        encoded, signature = (
            state.split(".", 1)
        )

        _, client_secret = (
            get_google_credentials()
        )

        expected = hmac.new(
            client_secret.encode(
                "utf-8"
            ),
            encoded.encode(
                "utf-8"
            ),
            hashlib.sha256,
        ).digest()

        received = (
            b64url_decode(
                signature
            )
        )

        if not hmac.compare_digest(
            expected,
            received,
        ):
            return None

        payload = json.loads(
            b64url_decode(
                encoded
            ).decode("utf-8")
        )

        timestamp = int(
            payload.get("t", 0)
        )

        if (
            int(time.time())
            - timestamp
            > 600
        ):
            return None

        return payload.get("u")

    except Exception:

        return None


def google_connect(
    event,
    user_id,
):

    capacity = google_account_capacity(
        user_id
    )

    if not capacity["can_add"]:
        return response(
            403,
            {
                "assistant":
                    "Hayder",
                "error":
                    "GOOGLE_ACCOUNT_LIMIT_REACHED",
                "plan":
                    capacity["plan"],
                "account_limit":
                    capacity["limit"],
                "connected_accounts":
                    capacity["connected"],
                "reply":
                    (
                        "Your Hayder "
                        + capacity["plan"].title()
                        + " plan has reached its Google account limit."
                    ),
            },
        )

    client_id, _ = (
        get_google_credentials()
    )

    redirect_uri = (
        google_redirect_uri(
            event
        )
    )

    state = create_google_state(
        user_id
    )

    params = {
        "client_id":
            client_id,
        "redirect_uri":
            redirect_uri,
        "response_type":
            "code",
        "scope":
            GOOGLE_SCOPE,
        "access_type":
            "offline",
        "include_granted_scopes":
            "true",
        "prompt":
            "select_account consent",
        "state":
            state,
    }

    authorization_url = (
        GOOGLE_AUTH_URL
        + "?"
        + urlencode(params)
    )

    return response(
        200,
        {
            "assistant":
                "Hayder",
            "authorization_url":
                authorization_url,
            "scope":
                "gmail.readonly",
            "message":
                "Open authorization_url "
                "in your browser to connect Gmail."
        },
    )


def post_form(
    url,
    payload,
):

    body = urlencode(
        payload
    ).encode("utf-8")

    req = urllib.request.Request(
        url,
        data=body,
        headers={
            "Content-Type":
                "application/x-www-form-urlencoded"
        },
        method="POST",
    )

    try:

        with urllib.request.urlopen(
            req,
            timeout=20,
        ) as api_response:

            return json.loads(
                api_response
                .read()
                .decode("utf-8")
            )

    except urllib.error.HTTPError as exc:

        error_body = (
            exc.read()
            .decode(
                "utf-8",
                errors="replace",
            )
        )

        print(
            "[GOOGLE HTTP ERROR]",
            exc.code,
            error_body,
        )

        raise RuntimeError(
            f"Google returned HTTP "
            f"{exc.code}"
        )


def google_api_get(
    url,
    access_token,
):

    req = urllib.request.Request(
        url,
        headers={
            "Authorization":
                "Bearer "
                + access_token
        },
        method="GET",
    )

    try:

        with urllib.request.urlopen(
            req,
            timeout=20,
        ) as api_response:

            return json.loads(
                api_response
                .read()
                .decode("utf-8")
            )

    except urllib.error.HTTPError as exc:

        error_body = (
            exc.read()
            .decode(
                "utf-8",
                errors="replace",
            )
        )

        print(
            "[GMAIL HTTP ERROR]",
            exc.code,
            error_body,
        )

        raise RuntimeError(
            f"Gmail returned HTTP "
            f"{exc.code}"
        )


def google_user_secret_name(
    user_id
):
    """Legacy single-account secret.

    Kept temporarily for backward compatibility.
    """

    digest = hashlib.sha256(
        user_id.encode(
            "utf-8"
        )
    ).hexdigest()

    return (
        "hayder/google/users/"
        + digest
        + "/gmail"
    )


def google_account_secret_name(
    user_id,
    google_email,
):
    """Return a separate secret name for each Google account."""

    user_digest = hashlib.sha256(
        user_id.encode(
            "utf-8"
        )
    ).hexdigest()

    account_digest = hashlib.sha256(
        google_email
        .strip()
        .lower()
        .encode(
            "utf-8"
        )
    ).hexdigest()

    return (
        "hayder/google/users/"
        + user_digest
        + "/accounts/"
        + account_digest
    )


def google_account_record_key(
    google_email,
):
    digest = hashlib.sha256(
        google_email
        .strip()
        .lower()
        .encode("utf-8")
    ).hexdigest()

    return (
        "GOOGLE_ACCOUNT#"
        + digest
    )


def google_default_record_key():
    return "GOOGLE_DEFAULT"


def put_google_secret(
    secret_name,
    connection,
):
    secret_value = json.dumps(
        connection
    )

    try:
        secrets_client.create_secret(
            Name=secret_name,
            SecretString=secret_value,
            Description=(
                "Hayder Google OAuth "
                "refresh token"
            ),
        )

    except (
        secrets_client
        .exceptions
        .ResourceExistsException
    ):
        secrets_client.put_secret_value(
            SecretId=secret_name,
            SecretString=secret_value,
        )


def read_google_secret(
    secret_name,
):
    try:
        result = (
            secrets_client
            .get_secret_value(
                SecretId=secret_name
            )
        )

    except (
        secrets_client
        .exceptions
        .ResourceNotFoundException
    ):
        return None

    secret_string = result.get(
        "SecretString"
    )

    if not secret_string:
        return None

    return json.loads(
        secret_string
    )


def get_google_default(
    user_id,
):
    result = table.get_item(
        Key={
            "user_id": user_id,
            "record_key":
                google_default_record_key(),
        }
    )

    return result.get("Item")


def set_google_default(
    user_id,
    google_email,
    secret_name,
):
    table.put_item(
        Item={
            "user_id": user_id,
            "record_key":
                google_default_record_key(),
            "provider": "google",
            "account_email":
                google_email,
            "secret_name":
                secret_name,
            "updated_at":
                now_iso(),
        }
    )


def register_google_account(
    user_id,
    google_email,
    secret_name,
    scope=GOOGLE_SCOPE,
):
    table.put_item(
        Item={
            "user_id": user_id,
            "record_key":
                google_account_record_key(
                    google_email
                ),
            "provider": "google",
            "account_email":
                google_email,
            "secret_name":
                secret_name,
            "scope":
                scope,
            "status":
                "connected",
            "updated_at":
                now_iso(),
        }
    )


def migrate_legacy_google_connection(
    user_id,
):
    """Safely copy the old single-account connection.

    The legacy secret is deliberately NOT deleted.
    """

    existing_default = (
        get_google_default(
            user_id
        )
    )

    if existing_default:
        return existing_default

    legacy_name = (
        google_user_secret_name(
            user_id
        )
    )

    legacy = read_google_secret(
        legacy_name
    )

    if not legacy:
        return None

    google_email = (
        legacy.get(
            "gmail_email"
        )
    )

    if not google_email:
        return None

    account_secret = (
        google_account_secret_name(
            user_id,
            google_email,
        )
    )

    migrated = dict(legacy)

    migrated[
        "connection_type"
    ] = "google"

    put_google_secret(
        account_secret,
        migrated,
    )

    register_google_account(
        user_id,
        google_email,
        account_secret,
        migrated.get(
            "scope",
            GOOGLE_SCOPE,
        ),
    )

    set_google_default(
        user_id,
        google_email,
        account_secret,
    )

    print(
        "[GOOGLE MIGRATION] "
        "Legacy Google connection "
        "copied into multi-account model."
    )

    return {
        "user_id": user_id,
        "record_key":
            google_default_record_key(),
        "provider": "google",
        "account_email":
            google_email,
        "secret_name":
            account_secret,
    }


def store_google_refresh_token(
    user_id,
    refresh_token,
    gmail_email,
):
    # First preserve an existing legacy account
    # as the default before adding another one.
    migrate_legacy_google_connection(
        user_id
    )

    secret_name = (
        google_account_secret_name(
            user_id,
            gmail_email,
        )
    )

    connection = {
        "refresh_token":
            refresh_token,
        "gmail_email":
            gmail_email,
        "scope":
            GOOGLE_SCOPE,
        "connected_at":
            now_iso(),
        "connection_type":
            "google",
    }

    put_google_secret(
        secret_name,
        connection,
    )

    register_google_account(
        user_id,
        gmail_email,
        secret_name,
        GOOGLE_SCOPE,
    )

    # For a brand-new Hayder user,
    # make the first connected account default.
    existing_default = (
        get_google_default(
            user_id
        )
    )

    if not existing_default:
        set_google_default(
            user_id,
            gmail_email,
            secret_name,
        )


def get_user_plan(
    user_id,
):
    """Return the user's commercial Hayder plan.

    Unknown users safely default to Basic.
    """

    result = table.get_item(
        Key={
            "user_id":
                user_id,
            "record_key":
                "ACCOUNT_PLAN",
        }
    )

    item = result.get(
        "Item",
        {}
    )

    plan = (
        item.get(
            "plan",
            "basic",
        )
        .strip()
        .lower()
    )

    if plan not in (
        "basic",
        "pro",
        "business",
    ):
        return "basic"

    return plan


def set_user_plan(
    user_id,
    plan,
):
    plan_name = (
        plan
        .strip()
        .lower()
    )

    if plan_name not in (
        "basic",
        "pro",
        "business",
    ):
        raise ValueError(
            "INVALID_PLAN"
        )

    table.put_item(
        Item={
            "user_id":
                user_id,
            "record_key":
                "ACCOUNT_PLAN",
            "plan":
                plan_name,
            "updated_at":
                now_iso(),
        }
    )

    return plan_name


def google_account_limit(
    plan,
):
    plan_name = (
        plan
        or "basic"
    ).strip().lower()

    return GOOGLE_ACCOUNT_LIMITS.get(
        plan_name,
        GOOGLE_ACCOUNT_LIMITS["basic"],
    )


def google_account_count(
    user_id,
):
    result = table.query(
        KeyConditionExpression=(
            "user_id = :user_id "
            "AND begins_with("
            "record_key, :prefix)"
        ),
        ExpressionAttributeValues={
            ":user_id":
                user_id,
            ":prefix":
                "GOOGLE_ACCOUNT#",
        },
        Select="COUNT",
    )

    return int(
        result.get(
            "Count",
            0,
        )
    )


def google_account_capacity(
    user_id,
):
    plan = get_user_plan(
        user_id
    )

    limit = google_account_limit(
        plan
    )

    count = google_account_count(
        user_id
    )

    return {
        "plan":
            plan,
        "limit":
            limit,
        "connected":
            count,
        "remaining":
            max(
                limit - count,
                0,
            ),
        "can_add":
            count < limit,
    }


def list_google_accounts(
    user_id,
):
    # Automatically migrate the old model
    # the first time this is called.
    migrate_legacy_google_connection(
        user_id
    )

    result = table.query(
        KeyConditionExpression=(
            "user_id = :user_id "
            "AND begins_with("
            "record_key, :prefix)"
        ),
        ExpressionAttributeValues={
            ":user_id":
                user_id,
            ":prefix":
                "GOOGLE_ACCOUNT#",
        },
    )

    default = get_google_default(
        user_id
    )

    default_email = (
        default.get(
            "account_email"
        )
        if default
        else None
    )

    accounts = []

    for item in result.get(
        "Items",
        [],
    ):
        email = item.get(
            "account_email"
        )

        accounts.append(
            {
                "email":
                    email,
                "scope":
                    item.get(
                        "scope",
                        "",
                    ),
                "status":
                    item.get(
                        "status",
                        "connected",
                    ),
                "default":
                    email
                    == default_email,
            }
        )

    return accounts


def load_google_connection(
    user_id,
    google_email=None,
):
    if google_email:

        secret_name = (
            google_account_secret_name(
                user_id,
                google_email,
            )
        )

        connection = (
            read_google_secret(
                secret_name
            )
        )

        if connection:
            return connection

        return None

    default = get_google_default(
        user_id
    )

    if not default:

        default = (
            migrate_legacy_google_connection(
                user_id
            )
        )

    if not default:
        return None

    secret_name = default.get(
        "secret_name"
    )

    if not secret_name:
        return None

    return read_google_secret(
        secret_name
    )


def google_callback(
    event
):

    query = (
        event.get(
            "queryStringParameters"
        )
        or {}
    )

    if query.get("error"):

        return response(
            400,
            {
                "error":
                    query.get(
                        "error"
                    )
            },
        )

    code = query.get("code")
    state = query.get("state")

    if not code or not state:

        return response(
            400,
            {
                "error":
                    "Missing OAuth code "
                    "or state"
            },
        )

    user_id = verify_google_state(
        state
    )

    if not user_id:

        return response(
            400,
            {
                "error":
                    "Invalid or expired "
                    "OAuth state"
            },
        )

    client_id, client_secret = (
        get_google_credentials()
    )

    token_data = post_form(
        GOOGLE_TOKEN_URL,
        {
            "code":
                code,
            "client_id":
                client_id,
            "client_secret":
                client_secret,
            "redirect_uri":
                google_redirect_uri(
                    event
                ),
            "grant_type":
                "authorization_code",
        },
    )

    access_token = (
        token_data.get(
            "access_token"
        )
    )

    refresh_token = (
        token_data.get(
            "refresh_token"
        )
    )

    if not access_token:

        return response(
            502,
            {
                "error":
                    "Google did not "
                    "return an access token"
            },
        )

    if not refresh_token:

        return response(
            400,
            {
                "error":
                    "Google did not return "
                    "a refresh token. "
                    "Reconnect and approve "
                    "consent again."
            },
        )

    profile = google_api_get(
        GMAIL_BASE_URL
        + "/users/me/profile",
        access_token,
    )

    gmail_email = (
        profile.get(
            "emailAddress"
        )
        or "unknown"
    )

    store_google_refresh_token(
        user_id,
        refresh_token,
        gmail_email,
    )

    html = f"""
<!DOCTYPE html>
<html>
<head>
<meta charset="utf-8">
<title>Hayder Gmail Connected</title>
</head>

<body style="
font-family:Arial;
max-width:700px;
margin:60px auto;
padding:20px;
">

<h1>✅ Gmail connected to Hayder</h1>

<p>
Connected Gmail account:
<strong>{gmail_email}</strong>
</p>

<p>
Permission:
<strong>Read only</strong>
</p>

<p>
Hayder cannot send or delete email
with this Gmail permission.
</p>

<p>
You can now return to Hayder Voice
and say:
</p>

<h2>
“Hayder, read my latest 5 emails.”
</h2>

<a href="/voice">
Return to Hayder Voice
</a>

</body>
</html>
"""

    return response(
        200,
        html,
        headers={
            "content-type":
                "text/html; charset=utf-8"
        },
    )




def refresh_google_access_token(
    user_id,
    google_email=None,
):

    connection = (
        load_google_connection(
            user_id,
            google_email,
        )
    )

    if not connection:

        raise RuntimeError(
            "GMAIL_NOT_CONNECTED"
        )

    refresh_token = (
        connection.get(
            "refresh_token"
        )
    )

    if not refresh_token:

        raise RuntimeError(
            "GMAIL_NOT_CONNECTED"
        )

    client_id, client_secret = (
        get_google_credentials()
    )

    data = post_form(
        GOOGLE_TOKEN_URL,
        {
            "client_id":
                client_id,
            "client_secret":
                client_secret,
            "refresh_token":
                refresh_token,
            "grant_type":
                "refresh_token",
        },
    )

    access_token = (
        data.get(
            "access_token"
        )
    )

    if not access_token:

        raise RuntimeError(
            "GOOGLE_REFRESH_FAILED"
        )

    return (
        access_token,
        connection,
    )


# ------------------------------------------------
# GMAIL READ-ONLY TOOL
# ------------------------------------------------

def detect_gmail_read_request(
    message
):

    text = message.lower()

    phrases = [
        "read my latest email",
        "read my latest emails",
        "read latest email",
        "read latest emails",
        "check my email",
        "check my emails",
        "latest 5 emails",
        "latest five emails",
        "recent emails",
    ]

    return any(
        phrase in text
        for phrase in phrases
    )


def detect_important_inbox_request(
    message
):

    text = message.lower()

    importance_words = [
        "important",
        "urgent",
        "priority",
        "worth my attention",
        "need my attention",
        "anything i should know",
        "anything important",
        "what needs attention",
    ]

    inbox_words = [
        "email",
        "emails",
        "gmail",
        "inbox",
        "mail",
        "messages",
    ]

    return (
        any(
            phrase in text
            for phrase in importance_words
        )
        and
        any(
            word in text
            for word in inbox_words
        )
    )



def gmail_latest_messages(
    user_id,
    max_results=5,
):

    access_token, connection = (
        refresh_google_access_token(
            user_id
        )
    )

    params = urlencode(
        {
            "maxResults":
                max_results,
            "q":
                "in:inbox",
        }
    )

    listing = google_api_get(
        GMAIL_BASE_URL
        + "/users/me/messages?"
        + params,
        access_token,
    )

    messages = []

    for item in listing.get(
        "messages",
        [],
    ):

        message_id = item["id"]

        query = urlencode(
            [
                (
                    "format",
                    "metadata",
                ),
                (
                    "metadataHeaders",
                    "From",
                ),
                (
                    "metadataHeaders",
                    "Subject",
                ),
                (
                    "metadataHeaders",
                    "Date",
                ),
            ]
        )

        msg = google_api_get(
            GMAIL_BASE_URL
            + "/users/me/messages/"
            + quote(
                message_id
            )
            + "?"
            + query,
            access_token,
        )

        headers = {}

        for header in (
            msg.get(
                "payload",
                {}
            ).get(
                "headers",
                []
            )
        ):

            headers[
                header.get(
                    "name",
                    ""
                ).lower()
            ] = header.get(
                "value",
                ""
            )

        messages.append(
            {
                "id":
                    message_id,
                "from":
                    headers.get(
                        "from",
                        ""
                    ),
                "subject":
                    headers.get(
                        "subject",
                        "(no subject)",
                    ),
                "date":
                    headers.get(
                        "date",
                        "",
                    ),
                "snippet":
                    msg.get(
                        "snippet",
                        "",
                    ),
            }
        )

    return {
        "gmail_account":
            connection.get(
                "gmail_email"
            ),
        "messages":
            messages,
    }


def gmail_spoken_reply(
    result
):

    messages = result.get(
        "messages",
        [],
    )

    if not messages:

        return (
            "I checked Gmail. "
            "There are no messages "
            "in your inbox."
        )

    parts = [
        "I checked Gmail. "
        f"Here are your latest "
        f"{len(messages)} emails."
    ]

    for index, msg in enumerate(
        messages,
        start=1,
    ):

        sender = msg.get(
            "from",
            "unknown sender",
        )

        subject = msg.get(
            "subject",
            "no subject",
        )

        parts.append(
            f"Email {index}. "
            f"From {sender}. "
            f"Subject: {subject}."
        )

    return " ".join(parts)


# ------------------------------------------------
# APPROVAL ENGINE
# ------------------------------------------------

def create_approval_record(
    user_id,
    action_type,
    target,
    summary,
    details=None,
):

    approval_id = str(
        uuid.uuid4()
    )

    timestamp = now_iso()

    item = {
        "user_id":
            user_id,
        "approval_id":
            approval_id,
        "action_type":
            action_type,
        "target":
            target,
        "summary":
            summary,
        "details":
            details or {},
        "status":
            "WAITING_APPROVAL",
        "created_at":
            timestamp,
        "updated_at":
            timestamp,
        "approved_at":
            None,
        "rejected_at":
            None,
        "executed_at":
            None,
    }

    approval_table.put_item(
        Item=item
    )

    return item


def create_approval(
    user_id,
    payload,
):

    required = [
        "action_type",
        "target",
        "summary",
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
                "error":
                    "Missing required fields: "
                    + ", ".join(missing)
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

    action_type = (
        payload[
            "action_type"
        ]
    )

    if (
        action_type
        not in
        allowed_action_types
    ):

        return response(
            400,
            {
                "error":
                    "Unsupported action_type",
                "allowed":
                    sorted(
                        allowed_action_types
                    ),
            },
        )

    item = create_approval_record(
        user_id=
            user_id,
        action_type=
            action_type,
        target=
            payload["target"],
        summary=
            payload["summary"],
        details=
            payload.get(
                "details",
                {},
            ),
    )

    return response(
        201,
        {
            "message":
                "Approval request created",
            "approval_id":
                item[
                    "approval_id"
                ],
            "status":
                item["status"],
            "action_type":
                item[
                    "action_type"
                ],
            "target":
                item["target"],
            "summary":
                item["summary"],
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
        if new_status
        == "APPROVED"
        else "rejected_at"
    )

    try:

        result = (
            approval_table
            .update_item(
                Key={
                    "user_id":
                        user_id,
                    "approval_id":
                        approval_id,
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
                    "#status":
                        "status",
                    "#updated_at":
                        "updated_at",
                    f"#{timestamp_field}":
                        timestamp_field,
                },
                ExpressionAttributeValues={
                    ":new_status":
                        new_status,
                    ":waiting":
                        "WAITING_APPROVAL",
                    ":now":
                        now,
                },
                ReturnValues=
                    "ALL_NEW",
            )
        )

    except (
        approval_table
        .meta
        .client
        .exceptions
        .ConditionalCheckFailedException
    ):

        existing = (
            approval_table
            .get_item(
                Key={
                    "user_id":
                        user_id,
                    "approval_id":
                        approval_id,
                }
            )
            .get("Item")
        )

        if not existing:

            return (
                None,
                "NOT_FOUND",
            )

        return (
            existing,
            "ALREADY_CHANGED",
        )

    return (
        result[
            "Attributes"
        ],
        None,
    )


# ------------------------------------------------
# PROJECT DETECTION
# ------------------------------------------------

def detect_project(
    message
):

    text = (
        message.strip()
        .lower()
    )

    known_projects = [
        "xorwia",
        "hayder",
    ]

    for project in (
        known_projects
    ):

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

            return (
                normalise_project_name(
                    match.group(1)
                )
            )

    return None


def build_project_context(
    user_id,
    message,
):

    project = detect_project(
        message
    )

    if not project:

        return (
            None,
            "",
        )

    item = get_project_record(
        user_id,
        project,
    )

    if not item:

        return (
            project,
            (
                "The user mentioned "
                f"project '{project}', "
                "but Hayder currently "
                "has no saved checkpoint "
                "for it."
            ),
        )

    context = {
        "project":
            item.get(
                "project"
            ),
        "status":
            item.get(
                "status"
            ),
        "summary":
            item.get(
                "summary"
            ),
        "completed":
            item.get(
                "completed",
                [],
            ),
        "outstanding":
            item.get(
                "outstanding",
                [],
            ),
        "next_action":
            item.get(
                "next_action"
            ),
        "decisions":
            item.get(
                "decisions",
                [],
            ),
        "people":
            item.get(
                "people",
                [],
            ),
        "updated_at":
            item.get(
                "updated_at"
            ),
    }

    return (
        project,
        json.dumps(
            context,
            default=str,
        ),
    )


# ------------------------------------------------
# SENSITIVE ACTION DETECTION
# ------------------------------------------------

def detect_sensitive_action(
    message
):

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

    for (
        action_type,
        phrases,
    ) in rules:

        for phrase in phrases:

            if phrase in text:

                project = (
                    detect_project(
                        message
                    )
                )

                return {
                    "action_type":
                        action_type,
                    "target":
                        project
                        or "unspecified",
                    "summary":
                        message.strip(),
                }

    return None


def detect_approval_command(
    message
):

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


# ------------------------------------------------
# OPENAI
# ------------------------------------------------

def extract_openai_text(
    data
):

    output_text = (
        data.get(
            "output_text"
        )
    )

    if output_text:
        return output_text

    text_parts = []

    for item in (
        data.get(
            "output",
            [],
        )
    ):

        if (
            item.get("type")
            != "message"
        ):
            continue

        for content in (
            item.get(
                "content",
                [],
            )
        ):

            if (
                content.get("type")
                == "output_text"
            ):

                text = content.get(
                    "text"
                )

                if text:
                    text_parts.append(
                        text
                    )

    return "\n".join(
        text_parts
    ).strip()


def call_openai(
    user_message,
    project_context="",
):

    api_key = (
        get_openai_api_key()
    )

    instructions = """
You are Hayder, a secure personal AI operations assistant.

Help the authenticated user manage projects, business work,
technical work and day-to-day operations.

Rules:

1. Use saved Hayder memory when supplied.
2. Never claim an external action happened unless an executor actually performed it.
3. Deployments, sending messages, purchases, deletions, security changes,
   AWS write changes and Git write changes require explicit approval.
4. Approval does not mean execution.
5. Read-only checks do not need approval.
6. Gmail access is read-only unless a future separately-approved capability exists.
7. Be concise, practical and action-oriented.
8. Your name is Hayder.
"""

    if project_context:

        input_text = (
            "USER MESSAGE:\n"
            + user_message
            + "\n\n"
            "SAVED HAYDER PROJECT MEMORY:\n"
            + project_context
        )

    else:

        input_text = (
            "USER MESSAGE:\n"
            + user_message
        )

    payload = {
        "model":
            OPENAI_MODEL,
        "instructions":
            instructions,
        "input":
            input_text,
        "reasoning": {
            "effort":
                "low"
        },
    }

    request = urllib.request.Request(
        "https://api.openai.com/v1/responses",
        data=json.dumps(
            payload
        ).encode("utf-8"),
        headers={
            "Authorization":
                "Bearer "
                + api_key,
            "Content-Type":
                "application/json",
        },
        method="POST",
    )

    try:

        with urllib.request.urlopen(
            request,
            timeout=25,
        ) as api_response:

            raw = (
                api_response
                .read()
                .decode("utf-8")
            )

    except urllib.error.HTTPError as exc:

        error_body = (
            exc.read()
            .decode(
                "utf-8",
                errors="replace",
            )
        )

        print(
            "[OPENAI HTTP ERROR]",
            exc.code,
            error_body,
        )

        raise RuntimeError(
            "OpenAI returned HTTP "
            + str(exc.code)
        )

    except urllib.error.URLError as exc:

        print(
            "[OPENAI CONNECTION ERROR]",
            str(exc),
        )

        raise RuntimeError(
            "Unable to connect "
            "to OpenAI"
        )

    data = json.loads(raw)

    text = extract_openai_text(
        data
    )

    if not text:

        raise RuntimeError(
            "OpenAI returned "
            "no text response"
        )

    return text


# ------------------------------------------------
# CHAT
# ------------------------------------------------

def chat(
    user_id,
    payload,
):

    message = payload.get(
        "message"
    )

    if not message:

        return response(
            400,
            {
                "error":
                    "message is required"
            },
        )

    # ------------------------------------------------
    # PERSONAL ATTENTION LEARNING
    # ------------------------------------------------

    preference = parse_preference_command(
        message
    )

    if preference:

        saved_result = save_preference(
            user_id=user_id,
            pattern=preference[
                "pattern"
            ],
            priority=preference[
                "priority"
            ],
            source_phrase=message,
        )

        saved = saved_result[
            "item"
        ]

        if saved_result[
            "updated"
        ]:

            reply_text = (
                "Updated. I changed "
                + saved["pattern"]
                + " from "
                + str(
                    saved_result[
                        "previous_priority"
                    ]
                ).lower()
                + " to "
                + saved["priority"].lower()
                + " priority."
            )

        else:

            reply_text = (
                "Understood. I will treat "
                + saved["pattern"]
                + " as "
                + saved["priority"].lower()
                + " priority when I review "
                + "your inbox."
            )

        return response(
            200,
            {
                "assistant":
                    "Hayder",
                "tool":
                    "attention_learning",
                "preference":
                    {
                        "pattern":
                            saved[
                                "pattern"
                            ],
                        "priority":
                            saved[
                                "priority"
                            ],
                        "updated":
                            saved_result[
                                "updated"
                            ],
                    },
                "reply":
                    reply_text,
            },
        )

    # ------------------------------------------------
    # SAFETY FIRST: APPROVAL / WRITE ACTIONS
    # ------------------------------------------------

    approval_command = (
        detect_approval_command(
            message
        )
    )

    if approval_command:

        (
            new_status,
            approval_id,
        ) = approval_command

        item, error = (
            update_approval_status(
                user_id,
                approval_id,
                new_status,
            )
        )

        if error == "NOT_FOUND":

            return response(
                404,
                {
                    "assistant":
                        "Hayder",
                    "reply":
                        "I could not find "
                        "that approval request."
                },
            )

        if error == "ALREADY_CHANGED":

            return response(
                409,
                {
                    "assistant":
                        "Hayder",
                    "approval_id":
                        approval_id,
                    "status":
                        item.get(
                            "status"
                        ),
                    "reply":
                        "That approval request "
                        "has already been "
                        f"{item.get('status')}."
                },
            )

        return response(
            200,
            {
                "assistant":
                    "Hayder",
                "approval_id":
                    approval_id,
                "status":
                    item["status"],
                "reply":
                    "Approval "
                    f"{approval_id} "
                    "is now "
                    f"{item['status']}. "
                    "No external action "
                    "has been executed yet."
            },
        )

    sensitive_action = (
        detect_sensitive_action(
            message
        )
    )

    if sensitive_action:

        item = (
            create_approval_record(
                user_id=
                    user_id,
                action_type=
                    sensitive_action[
                        "action_type"
                    ],
                target=
                    sensitive_action[
                        "target"
                    ],
                summary=
                    sensitive_action[
                        "summary"
                    ],
                details={
                    "source":
                        "chat",
                    "original_message":
                        message,
                },
            )
        )

        return response(
            200,
            {
                "assistant":
                    "Hayder",
                "approval_required":
                    True,
                "approval_id":
                    item[
                        "approval_id"
                    ],
                "status":
                    item[
                        "status"
                    ],
                "action_type":
                    item[
                        "action_type"
                    ],
                "target":
                    item[
                        "target"
                    ],
                "reply":
                    "This action requires "
                    "your approval. "
                    "I created approval request "
                    f"{item['approval_id']}. "
                    "No external action has "
                    "been performed. "
                    "To approve it, say: "
                    "Approve "
                    f"{item['approval_id']}"
            },
        )

    # ------------------------------------------------
    # INTENT + LEARNING LAYER
    # ------------------------------------------------

    try:

        resolved = resolve_intent(
            user_id,
            message,
        )

    except Exception as exc:

        print(
            "[INTENT RESOLUTION ERROR]",
            str(exc),
        )

        resolved = {
            "intent":
                "general_chat",
            "confidence":
                0,
            "source":
                "error_fallback",
        }

    intent = resolved.get(
        "intent"
    )

    # ------------------------------------------------
    # DAILY ATTENTION BRIEFING
    # ------------------------------------------------

    if intent == "daily_briefing":

        briefing_parts = []
        briefing_data = {
            "email": [],
            "calendar": [],
            "projects": [],
        }

        # EMAIL ATTENTION
        try:

            gmail_result = gmail_latest_messages(
                user_id,
                10,
            )

            attention_result = important_summary(
                gmail_result.get(
                    "messages",
                    [],
                ),
                limit=3,
                user_id=user_id,
            )

            important_mail = attention_result.get(
                "messages",
                [],
            )

            briefing_data["email"] = important_mail

            if important_mail:

                briefing_parts.append(
                    f"You have {len(important_mail)} "
                    "email items worth attention."
                )

                for item in important_mail:

                    briefing_parts.append(
                        f"{item.get('priority', 'MEDIUM')} priority email: "
                        f"{item.get('subject', 'No subject')}."
                    )

        except Exception as exc:

            print(
                "[BRIEFING EMAIL ERROR]",
                str(exc),
            )

        # TODAY'S CALENDAR
        try:

            access_token, _ = (
                refresh_google_access_token(
                    user_id
                )
            )

            events = calendar_events(
                access_token,
                day="today",
                max_results=10,
            )

            briefing_data["calendar"] = events

            if events:

                briefing_parts.append(
                    f"You have {len(events)} "
                    "calendar event"
                    + (
                        "s"
                        if len(events) != 1
                        else ""
                    )
                    + " today."
                )

                for event in events[:3]:

                    briefing_parts.append(
                        "Calendar: "
                        + event.get(
                            "summary",
                            "Untitled event",
                        )
                        + "."
                    )

        except Exception as exc:

            print(
                "[BRIEFING CALENDAR ERROR]",
                str(exc),
            )

        # PROJECT NEXT ACTIONS
        try:

            result = table.query(
                KeyConditionExpression=(
                    "user_id = :user_id "
                    "AND begins_with("
                    "record_key, :prefix)"
                ),
                ExpressionAttributeValues={
                    ":user_id":
                        user_id,
                    ":prefix":
                        "PROJECT#",
                },
            )

            projects = result.get(
                "Items",
                [],
            )

            briefing_data["projects"] = projects

            for project in projects[:3]:

                next_action = project.get(
                    "next_action"
                )

                if next_action:

                    briefing_parts.append(
                        "Project "
                        + project.get(
                            "project",
                            "unknown",
                        )
                        + ": "
                        + next_action
                        + "."
                    )

        except Exception as exc:

            print(
                "[BRIEFING PROJECT ERROR]",
                str(exc),
            )

        # Build a cleaner NOW / TODAY / LATER briefing.

        now_items = []
        today_items = []
        later_items = []

        # Group duplicate important email subjects.
        subject_counts = {}

        for item in briefing_data["email"]:

            subject = item.get(
                "subject",
                "No subject",
            )

            priority = item.get(
                "priority",
                "MEDIUM",
            )

            key = (
                subject.strip().lower()
            )

            if key not in subject_counts:
                subject_counts[key] = {
                    "subject": subject,
                    "count": 0,
                    "priority": priority,
                }

            subject_counts[key]["count"] += 1

            if priority == "HIGH":
                subject_counts[key][
                    "priority"
                ] = "HIGH"

        for item in subject_counts.values():

            count = item["count"]
            subject = item["subject"]
            priority = item["priority"]

            if count > 1:
                text = (
                    f"{count} emails with subject "
                    f"{subject}"
                )
            else:
                text = subject

            if priority == "HIGH":
                now_items.append(
                    "Email: " + text
                )
            else:
                today_items.append(
                    "Email: " + text
                )

        # Calendar belongs in TODAY initially.
        # Events promoted to URGENT are removed later.
        calendar_today_items = []

        if briefing_data["calendar"]:

            for event in briefing_data[
                "calendar"
            ][:3]:

                event_time = event_time_text(
                    event.get("start")
                )

                calendar_text = (
                    "Calendar: "
                    + event.get(
                        "summary",
                        "Untitled event",
                    )
                    + (
                        " at " + event_time
                        if event_time
                        else ""
                    )
                )

                calendar_today_items.append(
                    {
                        "text": calendar_text,
                        "summary": event.get(
                            "summary",
                            "",
                        ),
                    }
                )

        else:

            today_items.append(
                "Calendar is clear today"
            )

        # Project next actions belong in TODAY/LATER.
        for project in briefing_data[
            "projects"
        ][:3]:

            next_action = project.get(
                "next_action"
            )

            if next_action:

                later_items.append(
                    "Project "
                    + project.get(
                        "project",
                        "unknown",
                    )
                    + ": "
                    + next_action
                )

        parts = [
            "Here is your Hayder briefing."
        ]

        if now_items:

            parts.append(
                "NOW: "
                + "; ".join(
                    now_items
                )
                + "."
            )

        if today_items:

            parts.append(
                "TODAY: "
                + "; ".join(
                    today_items
                )
                + "."
            )

        if later_items:

            parts.append(
                "LATER: "
                + "; ".join(
                    later_items
                )
                + "."
            )

        if (
            not now_items
            and not today_items
            and not later_items
        ):

            parts.append(
                "Nothing currently needs "
                "your attention."
            )

        # Time-aware urgency and recommended focus.
        recommendations = []
        urgent_items = []

        for event in briefing_data["calendar"]:

            summary_raw = event.get(
                "summary",
                "Calendar event",
            )

            summary = summary_raw.lower()

            minutes_until = (
                event_minutes_from_now(
                    event.get("start")
                )
            )

            # Interviews within the next 2 hours
            # become urgent.
            if (
                "interview" in summary
                and minutes_until is not None
                and 0 <= minutes_until <= 120
            ):

                hours = (
                    minutes_until // 60
                )

                minutes = (
                    minutes_until % 60
                )

                if hours > 0 and minutes > 0:
                    countdown = (
                        f"{hours} hour"
                        + (
                            "s"
                            if hours != 1
                            else ""
                        )
                        + f" {minutes} minute"
                        + (
                            "s"
                            if minutes != 1
                            else ""
                        )
                    )

                elif hours > 0:
                    countdown = (
                        f"{hours} hour"
                        + (
                            "s"
                            if hours != 1
                            else ""
                        )
                    )

                else:
                    countdown = (
                        f"{minutes} minutes"
                    )

                event_time = event_time_text(
                    event.get("start")
                )

                urgent_items.append(
                    f"{summary_raw} is at "
                    f"{event_time}, about "
                    f"{countdown} away"
                )

                recommendations.append(
                    "Focus on interview preparation now."
                )

                break

            elif "interview" in summary:

                recommendations.append(
                    "Keep today's interview preparation "
                    "ahead of lower-priority work."
                )

                break

        # Remove calendar events already promoted to URGENT.
        urgent_summaries = set()

        for item in urgent_items:
            for event in briefing_data["calendar"]:
                summary = event.get(
                    "summary",
                    "",
                )

                if summary and summary in item:
                    urgent_summaries.add(
                        summary.lower()
                    )

        for item in calendar_today_items:

            if (
                item["summary"].lower()
                not in urgent_summaries
            ):
                today_items.append(
                    item["text"]
                )

        if urgent_items:
            parts.insert(
                1,
                "URGENT: "
                + "; ".join(
                    urgent_items
                )
                + "."
            )

        if now_items and not urgent_items:
            recommendations.append(
                "Review the NOW items before "
                "lower-priority work."
            )

        if later_items:
            recommendations.append(
                "Return to project work after "
                "today's higher-priority items."
            )

        if recommendations:
            parts.append(
                "RECOMMENDED: "
                + " ".join(
                    recommendations
                )
            )

        reply = " ".join(parts)

        return response(
            200,
            {
                "assistant":
                    "Hayder",
                "tool":
                    "daily_attention_briefing",
                "intent":
                    resolved,
                "briefing":
                    briefing_data,
                "reply":
                    reply,
            },
        )

    # ------------------------------------------------
    # IMPORTANT INBOX / ATTENTION ENGINE
    # ------------------------------------------------

    if (
        intent == "gmail_readonly"
        and detect_important_inbox_request(
            message
        )
    ):

        try:

            gmail_result = (
                gmail_latest_messages(
                    user_id,
                    10,
                )
            )

            attention_result = (
                important_summary(
                    gmail_result.get(
                        "messages",
                        [],
                    ),
                    limit=5,
                    user_id=user_id,
                )
            )

            return response(
                200,
                {
                    "assistant":
                        "Hayder",
                    "tool":
                        "attention_engine",
                    "intent":
                        resolved,
                    "gmail_account":
                        gmail_result.get(
                            "gmail_account"
                        ),
                    "important_messages":
                        attention_result.get(
                            "messages",
                            [],
                        ),
                    "reply":
                        attention_result.get(
                            "reply"
                        ),
                },
            )

        except RuntimeError as exc:

            if (
                str(exc)
                == "GMAIL_NOT_CONNECTED"
            ):

                return response(
                    409,
                    {
                        "assistant":
                            "Hayder",
                        "gmail_connected":
                            False,
                        "intent":
                            resolved,
                        "reply":
                            "Gmail is not connected "
                            "to this Hayder account yet."
                    },
                )

            print(
                "[ATTENTION ENGINE ERROR]",
                str(exc),
            )

            return response(
                502,
                {
                    "assistant":
                        "Hayder",
                    "reply":
                        "I could not analyse "
                        "your important emails."
                },
            )

        except Exception as exc:

            print(
                "[ATTENTION ENGINE ERROR]",
                str(exc),
            )

            return response(
                502,
                {
                    "assistant":
                        "Hayder",
                    "reply":
                        "I could not analyse "
                        "your important emails."
                },
            )

    # ------------------------------------------------
    # CALENDAR READ ONLY
    # ------------------------------------------------

    if intent == "calendar_readonly":

        try:

            day = (
                "tomorrow"
                if "tomorrow" in message.lower()
                else "today"
            )

            access_token, _ = (
                refresh_google_access_token(
                    user_id
                )
            )

            events = calendar_events(
                access_token,
                day=day,
                max_results=10,
            )

            return response(
                200,
                {
                    "assistant":
                        "Hayder",
                    "tool":
                        "calendar_readonly",
                    "intent":
                        resolved,
                    "day":
                        day,
                    "events":
                        events,
                    "reply":
                        spoken_calendar_summary(
                            events,
                            day,
                        ),
                },
            )

        except RuntimeError as exc:

            if str(exc) == "GMAIL_NOT_CONNECTED":

                return response(
                    409,
                    {
                        "assistant":
                            "Hayder",
                        "reply":
                            "Your Google account is not connected yet."
                    },
                )

            print(
                "[CALENDAR ERROR]",
                str(exc),
            )

            return response(
                502,
                {
                    "assistant":
                        "Hayder",
                    "reply":
                        "I could not read your calendar."
                },
            )

        except Exception as exc:

            print(
                "[CALENDAR ERROR]",
                str(exc),
            )

            return response(
                502,
                {
                    "assistant":
                        "Hayder",
                    "reply":
                        "I could not read your calendar."
                },
            )

    # ------------------------------------------------
    # GMAIL READ ONLY
    # ------------------------------------------------

    if intent == "gmail_readonly":

        try:

            gmail_result = (
                gmail_latest_messages(
                    user_id,
                    5,
                )
            )

            return response(
                200,
                {
                    "assistant":
                        "Hayder",
                    "tool":
                        "gmail_readonly",
                    "intent":
                        resolved,
                    "gmail":
                        gmail_result,
                    "reply":
                        gmail_spoken_reply(
                            gmail_result
                        ),
                },
            )

        except RuntimeError as exc:

            if (
                str(exc)
                == "GMAIL_NOT_CONNECTED"
            ):

                return response(
                    409,
                    {
                        "assistant":
                            "Hayder",
                        "gmail_connected":
                            False,
                        "intent":
                            resolved,
                        "reply":
                            "Gmail is not connected "
                            "to this Hayder account yet."
                    },
                )

            print(
                "[GMAIL READ ERROR]",
                str(exc),
            )

            return response(
                502,
                {
                    "assistant":
                        "Hayder",
                    "reply":
                        "I could not read Gmail."
                },
            )

        except Exception as exc:

            print(
                "[GMAIL READ ERROR]",
                str(exc),
            )

            return response(
                502,
                {
                    "assistant":
                        "Hayder",
                    "reply":
                        "I could not read Gmail."
                },
            )

    # ------------------------------------------------
    # AWS READ ONLY
    # ------------------------------------------------

    if intent == "aws_readonly":

        try:

            status = (
                get_hayder_lambda_status()
            )

            reply = (
                "My AWS Lambda is "
                f"{status.get('state')}. "
                "It is running "
                f"{status.get('runtime')}, "
                "with "
                f"{status.get('memory_mb')} "
                "MB memory and a "
                f"{status.get('timeout_seconds')} "
                "second timeout. "
                "Last modified: "
                f"{status.get('last_modified')}."
            )

            return response(
                200,
                {
                    "assistant":
                        "Hayder",
                    "tool":
                        "aws_lambda_readonly",
                    "intent":
                        resolved,
                    "aws":
                        status,
                    "reply":
                        reply,
                },
            )

        except Exception as exc:

            print(
                "[AWS READ ERROR]",
                str(exc),
            )

            return response(
                502,
                {
                    "error":
                        "Hayder could not "
                        "read its AWS Lambda "
                        "configuration"
                },
            )

    # ------------------------------------------------
    # PROJECT CONTINUATION
    # ------------------------------------------------

    if intent == "project_continue":

        project = detect_project(
            message
        )

        if project:

            item = get_project_record(
                user_id,
                project,
            )

            if item:

                completed = item.get(
                    "completed",
                    [],
                )

                outstanding = item.get(
                    "outstanding",
                    [],
                )

                next_action = item.get(
                    "next_action",
                    "",
                )

                reply = (
                    f"Continuing {project}. "
                    f"{item.get('summary', '')} "
                )

                if completed:
                    reply += (
                        "Completed: "
                        + ", ".join(
                            completed
                        )
                        + ". "
                    )

                if outstanding:
                    reply += (
                        "Outstanding: "
                        + ", ".join(
                            outstanding
                        )
                        + ". "
                    )

                if next_action:
                    reply += (
                        "Next action: "
                        + next_action
                        + "."
                    )

                return response(
                    200,
                    {
                        "assistant":
                            "Hayder",
                        "tool":
                            "project_memory",
                        "intent":
                            resolved,
                        "project":
                            project,
                        "reply":
                            reply,
                    },
                )

    # ------------------------------------------------
    # NORMAL AI CHAT FALLBACK
    # ------------------------------------------------

    (
        project,
        project_context,
    ) = build_project_context(
        user_id,
        message,
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
                "error":
                    "Hayder could not "
                    "reach the AI service"
            },
        )

    return response(
        200,
        {
            "assistant":
                "Hayder",
            "model":
                OPENAI_MODEL,
            "intent":
                resolved,
            "project":
                project,
            "reply":
                reply,
        },
    )


# ------------------------------------------------
# MAIN LAMBDA HANDLER
# ------------------------------------------------

def lambda_handler(
    event,
    context,
):

    request_context = (
        event.get(
            "requestContext",
            {},
        )
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

    path_parameters = (
        event.get(
            "pathParameters",
            {},
        )
        or {}
    )

    # PUBLIC HEALTH

    if (
        method == "GET"
        and path == "/health"
    ):

        return response(
            200,
            {
                "status":
                    "ok",
                "service":
                    "hayder-core",
            },
        )

    # PUBLIC GOOGLE CALLBACK

    if (
        method == "GET"
        and path
        == "/oauth/google/callback"
    ):

        try:

            return google_callback(
                event
            )

        except Exception as exc:

            print(
                "[GOOGLE CALLBACK ERROR]",
                str(exc),
            )

            return response(
                500,
                {
                    "error":
                        "Google connection failed"
                },
            )

    # EVERYTHING BELOW REQUIRES COGNITO

    user_id = (
        get_authenticated_user(
            event
        )
    )

    if not user_id:

        return response(
            401,
            {
                "error":
                    "Authenticated user "
                    "not found"
            },
        )

    # GOOGLE CONNECT

    if (
        method == "GET"
        and path
        == "/oauth/google/connect"
    ):

        return google_connect(
            event,
            user_id,
        )

    # ACCOUNT PLAN ADMIN
    # Temporary development-only route.

    if (
        method == "POST"
        and path == "/account/plan"
    ):
        body = get_body(event)

        plan = body.get(
            "plan",
            ""
        )

        try:
            saved_plan = set_user_plan(
                user_id,
                plan,
            )

        except ValueError:
            return response(
                400,
                {
                    "error":
                        "Plan must be basic, pro, or business."
                },
            )

        return response(
            200,
            {
                "assistant":
                    "Hayder",
                "plan":
                    saved_plan,
            },
        )

    # GOOGLE ACCOUNTS

    if (
        method == "GET"
        and path == "/google/accounts"
    ):

        accounts = list_google_accounts(
            user_id
        )

        capacity = google_account_capacity(
            user_id
        )

        return response(
            200,
            {
                "assistant":
                    "Hayder",
                "accounts":
                    accounts,
                "plan":
                    capacity["plan"],
                "account_limit":
                    capacity["limit"],
                "connected_accounts":
                    capacity["connected"],
                "remaining_accounts":
                    capacity["remaining"],
                "can_add_account":
                    capacity["can_add"],
            },
        )

    # PROJECT MEMORY

    if (
        method == "POST"
        and path
        == "/memory/project"
    ):

        try:

            return save_checkpoint(
                get_body(event),
                user_id,
            )

        except json.JSONDecodeError:

            return response(
                400,
                {
                    "error":
                        "Invalid JSON body"
                },
            )

    # CONTINUE PROJECT

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

    # CHAT

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
                {
                    "error":
                        "Invalid JSON body"
                },
            )

    # CREATE APPROVAL

    if (
        method == "POST"
        and path
        == "/approval/create"
    ):

        try:

            return create_approval(
                user_id,
                get_body(event),
            )

        except json.JSONDecodeError:

            return response(
                400,
                {
                    "error":
                        "Invalid JSON body"
                },
            )

    # APPROVE

    if (
        method == "POST"
        and path.endswith(
            "/approve"
        )
        and "/approval/"
        in path
    ):

        approval_id = (
            path_parameters.get(
                "approval_id"
            )
        )

        item, error = (
            update_approval_status(
                user_id,
                approval_id,
                "APPROVED",
            )
        )

        if error:

            return response(
                409
                if item
                else 404,
                {
                    "error":
                        error,
                    "current_status":
                        (
                            item.get(
                                "status"
                            )
                            if item
                            else None
                        ),
                },
            )

        return response(
            200,
            {
                "approval_id":
                    approval_id,
                "status":
                    item["status"],
                "summary":
                    item["summary"],
            },
        )

    # REJECT

    if (
        method == "POST"
        and path.endswith(
            "/reject"
        )
        and "/approval/"
        in path
    ):

        approval_id = (
            path_parameters.get(
                "approval_id"
            )
        )

        item, error = (
            update_approval_status(
                user_id,
                approval_id,
                "REJECTED",
            )
        )

        if error:

            return response(
                409
                if item
                else 404,
                {
                    "error":
                        error,
                    "current_status":
                        (
                            item.get(
                                "status"
                            )
                            if item
                            else None
                        ),
                },
            )

        return response(
            200,
            {
                "approval_id":
                    approval_id,
                "status":
                    item["status"],
                "summary":
                    item["summary"],
            },
        )

    return response(
        404,
        {
            "error":
                "Route not found"
        },
    )
