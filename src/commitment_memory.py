import re
import uuid
from datetime import datetime, time, timezone


_COMMITMENT = re.compile(
    r"^(?P<prefix>I will|I'll|I promise to|I commit to)\s+"
    r"(?P<text>[^?]+?)[.!]?$",
    re.IGNORECASE,
)
_DUE_AT = re.compile(
    r"\s+(?:by|on)\s+(?P<due>\d{4}-\d{2}-\d{2}"
    r"(?:T\d{2}:\d{2}(?::\d{2})?(?:Z|[+-]\d{2}:\d{2})?)?)$",
    re.IGNORECASE,
)
_CONDITIONAL = re.compile(r"\b(?:if|when|once|unless)\b", re.IGNORECASE)
_VAGUE = re.compile(
    r"^(?:not|try|maybe|probably|hopefully|intend|plan)\b|"
    r"\b(?:it|this|that|something|things|everything)$",
    re.IGNORECASE,
)


def now_iso():
    return datetime.now(timezone.utc).isoformat()


def _parse_due_at(value):
    try:
        if "T" not in value:
            due_date = datetime.strptime(value, "%Y-%m-%d").date()
            return datetime.combine(
                due_date,
                time.max,
                tzinfo=timezone.utc,
            ).isoformat()

        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        if parsed.tzinfo is None:
            return None
        return parsed.isoformat()
    except ValueError:
        return None


def detect_commitment(message):
    source_phrase = message.strip()
    match = _COMMITMENT.fullmatch(source_phrase)
    if not match:
        return None

    commitment_text = match.group("text").strip()
    if (
        len(commitment_text.split()) < 2
        or _CONDITIONAL.search(commitment_text)
        or _VAGUE.search(commitment_text)
        or re.search(r"\b(?:will not|won't|cannot|can't)\b", source_phrase, re.IGNORECASE)
    ):
        return None

    due_at = None
    due_match = _DUE_AT.search(commitment_text)
    if due_match:
        due_at = _parse_due_at(due_match.group("due"))
        if due_at is None:
            return None
        commitment_text = commitment_text[:due_match.start()].strip()

    return {
        "commitment": commitment_text,
        "due_at": due_at,
        "source_phrase": source_phrase,
    }


def save_commitment(table, user_id, detected, created_at=None):
    created_at = created_at or now_iso()
    item = {
        "user_id": user_id,
        "record_key": "COMMITMENT#" + created_at + "#" + uuid.uuid4().hex,
        "record_type": "COMMITMENT",
        "commitment": detected["commitment"],
        "status": "OPEN",
        "source_phrase": detected["source_phrase"],
        "created_at": created_at,
    }
    if detected.get("due_at"):
        item["due_at"] = detected["due_at"]

    table.put_item(Item=item)
    return item


def open_commitments(table, user_id):
    result = table.query(
        KeyConditionExpression=(
            "user_id = :user_id AND begins_with(record_key, :prefix)"
        ),
        ExpressionAttributeValues={
            ":user_id": user_id,
            ":prefix": "COMMITMENT#",
        },
    )
    return [
        item
        for item in result.get("Items", [])
        if item.get("status") == "OPEN"
    ]
