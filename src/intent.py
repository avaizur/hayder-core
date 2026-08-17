import hashlib
import json
import os
import re
import urllib.error
import urllib.request
from datetime import datetime, timezone

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


dynamodb = boto3.resource("dynamodb")
table = dynamodb.Table(TABLE_NAME)

secrets_client = boto3.client(
    "secretsmanager"
)

_secret_cache = {}


ALLOWED_READ_INTENTS = {
    "gmail_readonly",
    "aws_readonly",
    "project_continue",
    "calendar_readonly",
    "daily_briefing",
    "general_chat",
}


# Anything potentially changing external state
# must NOT be learned/routed by this module.
BLOCKED_WRITE_PHRASES = [
    "deploy",
    "release",
    "promote",
    "send email",
    "send the email",
    "send message",
    "delete",
    "destroy",
    "terminate",
    "purchase",
    "buy ",
    "pay for",
    "update iam",
    "change iam",
    "modify security group",
    "push to git",
    "push to github",
    "commit and push",
    "merge ",
]


def now_iso():
    return datetime.now(
        timezone.utc
    ).isoformat()


def normalize_phrase(text):
    text = text.lower().strip()

    text = re.sub(
        r"[^\w\s-]",
        " ",
        text,
    )

    text = re.sub(
        r"\s+",
        " ",
        text,
    )

    return text.strip()


def phrase_hash(text):
    normalized = normalize_phrase(text)

    return hashlib.sha256(
        normalized.encode("utf-8")
    ).hexdigest()


def intent_record_key(text):
    return (
        "INTENT#"
        + phrase_hash(text)
    )


def contains_write_intent(message):
    text = message.lower()

    return any(
        phrase in text
        for phrase in BLOCKED_WRITE_PHRASES
    )


def get_secret(secret_name):
    if secret_name in _secret_cache:
        return _secret_cache[
            secret_name
        ]

    result = secrets_client.get_secret_value(
        SecretId=secret_name
    )

    value = result.get(
        "SecretString"
    )

    if not value:
        raise RuntimeError(
            f"Secret {secret_name} is empty"
        )

    value = value.strip()

    _secret_cache[
        secret_name
    ] = value

    return value


def get_learned_intent(
    user_id,
    message,
):
    result = table.get_item(
        Key={
            "user_id": user_id,
            "record_key":
                intent_record_key(
                    message
                ),
        }
    )

    item = result.get("Item")

    if not item:
        return None

    intent = item.get("intent")

    if intent not in ALLOWED_READ_INTENTS:
        return None

    return {
        "intent": intent,
        "confidence": float(
            item.get(
                "confidence",
                1.0,
            )
        ),
        "source": "learned_memory",
        "phrase": item.get(
            "phrase"
        ),
    }


def remember_intent(
    user_id,
    message,
    intent,
    confidence,
    source,
):
    if intent not in ALLOWED_READ_INTENTS:
        return

    if intent == "general_chat":
        return

    if contains_write_intent(message):
        return

    normalized = normalize_phrase(
        message
    )

    if not normalized:
        return

    item = {
        "user_id": user_id,
        "record_key":
            intent_record_key(
                message
            ),
        "record_type":
            "INTENT_MEMORY",
        "phrase":
            message.strip(),
        "normalized_phrase":
            normalized,
        "intent":
            intent,
        "confidence":
            str(confidence),
        "source":
            source,
        "learned_at":
            now_iso(),
    }

    table.put_item(
        Item=item
    )


def heuristic_intent(message):
    text = normalize_phrase(
        message
    )

    # Gmail natural-language examples:
    # "check my latest email"
    # "anything new in my inbox"
    # "what mail came in"
    # "read my messages"

    gmail_words = [
        "email",
        "emails",
        "gmail",
        "inbox",
        "mail",
        "message",
        "messages",
    ]

    gmail_actions = [
        "check",
        "read",
        "latest",
        "recent",
        "new",
        "show",
        "what",
        "anything",
    ]

    if (
        any(
            word in text
            for word in gmail_words
        )
        and
        any(
            word in text
            for word in gmail_actions
        )
    ):
        return {
            "intent":
                "gmail_readonly",
            "confidence":
                0.92,
            "source":
                "heuristic",
        }

    # AWS read-only examples

    aws_words = [
        "aws",
        "lambda",
        "cloud",
        "function",
    ]

    aws_actions = [
        "check",
        "status",
        "show",
        "inspect",
        "health",
        "configuration",
        "config",
    ]

    if (
        any(
            word in text
            for word in aws_words
        )
        and
        any(
            word in text
            for word in aws_actions
        )
    ):
        return {
            "intent":
                "aws_readonly",
            "confidence":
                0.92,
            "source":
                "heuristic",
        }

    # Unified daily attention briefing

    briefing_phrases = [
        "what needs my attention today",
        "what needs attention today",
        "what needs my attention",
        "what needs attention",
        "whats needed by attention today",
        "what's needed by attention today",
        "what should i focus on today",
        "what should i do today",
        "brief me for today",
        "brief me today",
        "daily briefing",
        "give me my briefing",
        "what matters today",
        "what is important today",
        "anything important today",
    ]

    briefing_words = [
        "attention",
        "focus",
        "briefing",
        "important",
        "matters",
        "priority",
        "priorities",
    ]

    today_words = [
        "today",
        "now",
        "this morning",
        "this afternoon",
        "this evening",
    ]

    if (
        any(
            phrase in text
            for phrase in briefing_phrases
        )
        or (
            any(
                word in text
                for word in briefing_words
            )
            and
            any(
                word in text
                for word in today_words
            )
        )
    ):
        return {
            "intent":
                "daily_briefing",
            "confidence":
                0.96,
            "source":
                "heuristic",
        }

    # Calendar read-only

    calendar_words = [
        "calendar",
        "schedule",
        "meeting",
        "meetings",
        "appointment",
        "appointments",
        "interview",
        "interviews",
    ]

    calendar_time_words = [
        "today",
        "tomorrow",
        "this afternoon",
        "this evening",
        "what do i have",
        "anything",
        "check",
        "show",
    ]

    if (
        any(
            word in text
            for word in calendar_words
        )
        and
        any(
            phrase in text
            for phrase in calendar_time_words
        )
    ):
        return {
            "intent":
                "calendar_readonly",
            "confidence":
                0.92,
            "source":
                "heuristic",
        }

    # Project continuation

    continuation_words = [
        "continue",
        "carry on",
        "where we left",
        "resume",
        "pick up",
    ]

    if any(
        phrase in text
        for phrase in continuation_words
    ):
        return {
            "intent":
                "project_continue",
            "confidence":
                0.85,
            "source":
                "heuristic",
        }

    return None


def extract_response_text(data):
    output_text = data.get(
        "output_text"
    )

    if output_text:
        return output_text.strip()

    parts = []

    for item in data.get(
        "output",
        [],
    ):
        if item.get("type") != "message":
            continue

        for content in item.get(
            "content",
            [],
        ):
            if (
                content.get("type")
                == "output_text"
            ):
                text = content.get(
                    "text"
                )

                if text:
                    parts.append(
                        text
                    )

    return "\n".join(
        parts
    ).strip()


def classify_with_ai(message):
    api_key = get_secret(
        OPENAI_SECRET_NAME
    )

    instructions = """
You are the intent classifier for Hayder.

Classify the user's request into exactly ONE of these intents:

gmail_readonly
aws_readonly
calendar_readonly
project_continue
general_chat

Definitions:

gmail_readonly:
The user wants to read, check, inspect, review, summarize,
or discover email/inbox information.

aws_readonly:
The user wants to inspect or check AWS/Lambda status,
configuration, health, or other read-only infrastructure information.

calendar_readonly:
The user wants to inspect their calendar, schedule, meetings,
appointments, interviews, or events.

project_continue:
The user wants to resume, continue, recall, or pick up work
on an existing project.

general_chat:
Everything else.

IMPORTANT SAFETY RULE:
If the request asks to SEND, DELETE, DEPLOY, CHANGE, MODIFY,
PURCHASE, COMMIT, PUSH, RELEASE, TERMINATE, or otherwise perform
a write/change action, return general_chat.
The existing Hayder approval engine must handle those requests.

Return ONLY valid JSON:

{
  "intent": "gmail_readonly",
  "confidence": 0.95
}

Confidence must be between 0 and 1.
"""

    payload = {
        "model":
            OPENAI_MODEL,
        "instructions":
            instructions,
        "input":
            message,
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
            timeout=20,
        ) as api_response:
            raw = (
                api_response
                .read()
                .decode("utf-8")
            )

    except urllib.error.HTTPError as exc:
        body = (
            exc.read()
            .decode(
                "utf-8",
                errors="replace",
            )
        )

        print(
            "[INTENT AI HTTP ERROR]",
            exc.code,
            body,
        )

        return None

    except Exception as exc:
        print(
            "[INTENT AI ERROR]",
            str(exc),
        )

        return None

    try:
        data = json.loads(raw)

        text = extract_response_text(
            data
        )

        # Remove markdown fences if a model ever
        # returns them despite instruction.

        text = (
            text.replace(
                "```json",
                "",
            )
            .replace(
                "```",
                "",
            )
            .strip()
        )

        result = json.loads(
            text
        )

        intent = result.get(
            "intent"
        )

        confidence = float(
            result.get(
                "confidence",
                0,
            )
        )

        if (
            intent
            not in
            ALLOWED_READ_INTENTS
        ):
            return None

        return {
            "intent":
                intent,
            "confidence":
                confidence,
            "source":
                "ai_classifier",
        }

    except Exception as exc:
        print(
            "[INTENT AI PARSE ERROR]",
            str(exc),
        )

        return None


def resolve_intent(
    user_id,
    message,
):
    """
    Resolution order:

    1. Protect all possible write actions.
    2. Check learned user-specific phrase.
    3. Run safe deterministic heuristics.
    4. Ask AI classifier.
    5. Learn only high-confidence read-only results.
    """

    if contains_write_intent(
        message
    ):
        return {
            "intent":
                None,
            "confidence":
                1.0,
            "source":
                "write_action_blocked",
        }

    learned = get_learned_intent(
        user_id,
        message,
    )

    if learned:
        return learned

    heuristic = heuristic_intent(
        message
    )

    if heuristic:
        if (
            heuristic[
                "confidence"
            ]
            >= 0.90
        ):
            remember_intent(
                user_id=
                    user_id,
                message=
                    message,
                intent=
                    heuristic[
                        "intent"
                    ],
                confidence=
                    heuristic[
                        "confidence"
                    ],
                source=
                    heuristic[
                        "source"
                    ],
            )

        return heuristic

    classified = classify_with_ai(
        message
    )

    if not classified:
        return {
            "intent":
                "general_chat",
            "confidence":
                0,
            "source":
                "fallback",
        }

    # Only automatically remember high-confidence,
    # read-only classifications.

    if (
        classified[
            "intent"
        ]
        in {
            "gmail_readonly",
            "aws_readonly",
            "project_continue",
        }
        and
        classified[
            "confidence"
        ]
        >= 0.90
    ):
        remember_intent(
            user_id=
                user_id,
            message=
                message,
            intent=
                classified[
                    "intent"
                ],
            confidence=
                classified[
                    "confidence"
                ],
            source=
                classified[
                    "source"
                ],
        )

    return classified
