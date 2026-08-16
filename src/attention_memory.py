import hashlib
import re
from datetime import datetime, timezone

import boto3


TABLE_NAME = None


def configure(table_name):
    global TABLE_NAME
    TABLE_NAME = table_name


def _table():
    if not TABLE_NAME:
        raise RuntimeError(
            "Attention memory table not configured"
        )

    dynamodb = boto3.resource("dynamodb")
    return dynamodb.Table(TABLE_NAME)


def now_iso():
    return datetime.now(
        timezone.utc
    ).isoformat()


def normalize(text):
    text = text.lower().strip()

    text = re.sub(
        r"\s+",
        " ",
        text,
    )

    return text


def clean_pattern(text):
    text = normalize(text)

    removable = [
        "emails",
        "email",
        "messages",
        "message",
    ]

    for word in removable:
        text = re.sub(
            rf"\b{word}\b",
            "",
            text,
        )

    text = re.sub(
        r"\s+",
        " ",
        text,
    )

    return text.strip()


def preference_key(pattern):
    pattern = clean_pattern(
        pattern
    )

    digest = hashlib.sha256(
        pattern.encode("utf-8")
    ).hexdigest()[:24]

    return (
        "ATTENTION_PREF#"
        + digest
    )


def save_preference(
    user_id,
    pattern,
    priority,
    source_phrase,
):
    pattern = clean_pattern(
        pattern
    )

    if not pattern:
        raise ValueError(
            "Preference pattern is empty"
        )

    if priority not in {
        "HIGH",
        "MEDIUM",
        "LOW",
        "IGNORE",
    }:
        raise ValueError(
            "Invalid attention priority"
        )

    key = preference_key(
        pattern
    )

    existing = _table().get_item(
        Key={
            "user_id": user_id,
            "record_key": key,
        }
    ).get("Item")

    item = {
        "user_id":
            user_id,

        "record_key":
            key,

        "record_type":
            "ATTENTION_PREFERENCE",

        "pattern":
            pattern,

        "priority":
            priority,

        "source_phrase":
            source_phrase,

        "updated_at":
            now_iso(),
    }

    if existing:
        item["created_at"] = (
            existing.get(
                "created_at"
            )
            or existing.get(
                "updated_at"
            )
            or now_iso()
        )

        item["previous_priority"] = (
            existing.get(
                "priority"
            )
        )

    else:
        item["created_at"] = (
            now_iso()
        )

    _table().put_item(
        Item=item
    )

    return {
        "item":
            item,

        "updated":
            existing is not None,

        "previous_priority":
            (
                existing.get(
                    "priority"
                )
                if existing
                else None
            ),
    }


def parse_preference_command(
    message
):
    text = normalize(
        message
    )

    # Remove conversational prefixes.
    prefixes = [
        "actually ",
        "from now on ",
        "going forward ",
        "please ",
        "i want ",
        "i'd like ",
        "can you ",
        "could you ",
    ]

    changed = True

    while changed:
        changed = False

        for prefix in prefixes:
            if text.startswith(
                prefix
            ):
                text = text[
                    len(prefix):
                ].strip()

                changed = True

    # IGNORE

    patterns = [
        r"^ignore\s+(.+?)(?:\s+emails?)?$",
        r"^(.+?)\s+emails?\s+are\s+not\s+important$",
        r"^(.+?)\s+is\s+not\s+important$",
    ]

    for pattern in patterns:
        match = re.match(
            pattern,
            text,
        )

        if match:
            return {
                "pattern":
                    clean_pattern(
                        match.group(1)
                    ),
                "priority":
                    "IGNORE",
            }

    # HIGH

    patterns = [
        r"^(.+?)\s+emails?\s+are\s+always\s+important$",
        r"^make\s+(.+?)\s+emails?\s+high\s+priority$",
        r"^make\s+(.+?)\s+high\s+priority$",
        r"^(.+?)\s+emails?\s+are\s+high\s+priority$",
        r"^(.+?)\s+are\s+high\s+priority$",
        r"^(.+?)\s+is\s+high\s+priority$",
    ]

    for pattern in patterns:
        match = re.match(
            pattern,
            text,
        )

        if match:
            return {
                "pattern":
                    clean_pattern(
                        match.group(1)
                    ),
                "priority":
                    "HIGH",
            }

    # MEDIUM

    patterns = [
        r"^make\s+(.+?)\s+emails?\s+medium\s+priority$",
        r"^make\s+(.+?)\s+medium\s+priority$",
        r"^(.+?)\s+emails?\s+are\s+medium\s+priority$",
        r"^(.+?)\s+are\s+medium\s+priority$",
        r"^(.+?)\s+is\s+medium\s+priority$",
    ]

    for pattern in patterns:
        match = re.match(
            pattern,
            text,
        )

        if match:
            return {
                "pattern":
                    clean_pattern(
                        match.group(1)
                    ),
                "priority":
                    "MEDIUM",
            }

    # LOW

    patterns = [
        r"^make\s+(.+?)\s+emails?\s+low\s+priority$",
        r"^make\s+(.+?)\s+low\s+priority$",
        r"^(.+?)\s+emails?\s+are\s+low\s+priority$",
        r"^(.+?)\s+are\s+low\s+priority$",
        r"^(.+?)\s+is\s+low\s+priority$",
    ]

    for pattern in patterns:
        match = re.match(
            pattern,
            text,
        )

        if match:
            return {
                "pattern":
                    clean_pattern(
                        match.group(1)
                    ),
                "priority":
                    "LOW",
            }

    return None


def get_preferences(
    user_id
):
    result = _table().query(
        KeyConditionExpression=(
            "user_id = :user_id "
            "AND begins_with("
            "record_key, :prefix)"
        ),

        ExpressionAttributeValues={
            ":user_id":
                user_id,

            ":prefix":
                "ATTENTION_PREF#",
        },
    )

    return result.get(
        "Items",
        [],
    )


def apply_preferences(
    user_id,
    message,
    score,
    priority,
    reason,
):
    text = normalize(
        " ".join(
            [
                message.get(
                    "from",
                    "",
                ),
                message.get(
                    "subject",
                    "",
                ),
                message.get(
                    "snippet",
                    "",
                ),
            ]
        )
    )

    preferences = get_preferences(
        user_id
    )

    matched = []

    for pref in preferences:
        pattern = pref.get(
            "pattern",
            "",
        )

        if not pattern:
            continue

        if pattern not in text:
            continue

        pref_priority = pref.get(
            "priority"
        )

        matched.append(
            pattern
        )

        if pref_priority == "IGNORE":
            score = 0
            priority = "LOW"

        elif pref_priority == "HIGH":
            score = max(
                score,
                90,
            )
            priority = "HIGH"

        elif pref_priority == "MEDIUM":
            score = 65
            priority = "MEDIUM"

        elif pref_priority == "LOW":
            score = min(
                score,
                30,
            )
            priority = "LOW"

    if matched:
        reason = (
            reason
            + ". Personal preference: "
            + ", ".join(matched)
        )

    return {
        "score":
            score,

        "priority":
            priority,

        "reason":
            reason,

        "matched_preferences":
            matched,
    }
