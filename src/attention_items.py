from collections import Counter
from datetime import datetime, timedelta, timezone
from email.utils import parsedate_to_datetime
import re


URGENCY_ORDER = {
    "urgent": 0,
    "high": 1,
    "medium": 2,
    "low": 3,
}


TYPE_ORDER = {
    "reply_due": "important_unread_email",
    "important_unread_email": "reply_due",
}


def _attention_item_sort_key(item):
    return (
        URGENCY_ORDER[item["urgency"]],
        TYPE_ORDER.get(item["type"], item["type"]),
        item["title"].lower(),
        item["source"],
    )


def _parse_datetime(value):
    if not value or "T" not in value:
        return None

    try:
        parsed = datetime.fromisoformat(
            value.replace("Z", "+00:00")
        )
    except (TypeError, ValueError):
        return None

    if parsed.tzinfo is None:
        return None

    return parsed


def _email_labels(message):
    return {
        str(label).upper()
        for label in message.get("labelIds", [])
    }


def _attention_item(item_type, title, reason, urgency, source):
    return {
        "type": item_type,
        "title": title,
        "reason": reason,
        "urgency": urgency,
        "source": source,
    }


_REPLY_REQUEST_RE = re.compile(
    r"(?:\?|\b(?:can|could|would|will) you\b|\bplease (?:reply|respond|confirm)\b"
    r"|\blet me know\b|\bwhat do you think\b)",
    re.IGNORECASE,
)
_AUTOMATED_SENDER_RE = re.compile(
    r"(?:^|[<@._+-])(?:no[._-]?reply|do[._-]?not[._-]?reply|notifications?)(?:[>@._+-]|$)",
    re.IGNORECASE,
)
_AUTOMATED_LABELS = {"CATEGORY_FORUMS", "CATEGORY_PROMOTIONS", "CATEGORY_SOCIAL"}


def _message_datetime(message):
    """Read a Gmail internal timestamp or an RFC 2822 Date header."""
    internal_date = message.get("internalDate")
    if internal_date is not None:
        try:
            return datetime.fromtimestamp(int(internal_date) / 1000, tz=timezone.utc)
        except (TypeError, ValueError, OverflowError):
            pass

    value = message.get("date")
    if not value:
        return None
    try:
        parsed = parsedate_to_datetime(value)
    except (TypeError, ValueError, OverflowError):
        return None
    if parsed.tzinfo is None:
        return None
    return parsed


def _looks_automated(message, labels):
    sender = str(message.get("from") or "")
    return bool(_AUTOMATED_SENDER_RE.search(sender) or labels & _AUTOMATED_LABELS)


def _reply_due_item(message):
    subject = message.get("subject") or "(no subject)"
    sender = message.get("from") or "unknown sender"
    return _attention_item(
        "reply_due",
        f"Reply needed: {subject}",
        f"From {sender}.",
        "high",
        "gmail",
    )


def detect_reply_due_items(gmail_messages, now, follow_up_days=3):
    """Detect conservative reply candidates from already-fetched Gmail data."""
    if now.tzinfo is None:
        raise ValueError("now must be timezone-aware")
    if follow_up_days < 0:
        raise ValueError("follow_up_days must not be negative")

    messages = gmail_messages or []
    items = []
    for message in messages:
        labels = _email_labels(message)
        text = " ".join(str(message.get(field) or "") for field in ("subject", "snippet"))
        if (
            {"INBOX", "UNREAD", "IMPORTANT"} <= labels
            and "SENT" not in labels
            and not _looks_automated(message, labels)
            and _REPLY_REQUEST_RE.search(text)
        ):
            items.append(_reply_due_item(message))

    cutoff = now - timedelta(days=follow_up_days)
    threads = {}
    for message in messages:
        thread_id = message.get("threadId")
        sent_at = _message_datetime(message)
        if thread_id and sent_at is not None:
            threads.setdefault(str(thread_id), []).append((sent_at, message))

    for thread_messages in threads.values():
        thread_messages.sort(key=lambda entry: entry[0])
        sent_at, latest = thread_messages[-1]
        labels = _email_labels(latest)
        if "SENT" not in labels or sent_at >= cutoff:
            continue
        if labels & {"DRAFT", "SPAM", "TRASH"}:
            continue
        subject = latest.get("subject") or "(no subject)"
        items.append(_attention_item(
            "follow_up_due", subject,
            f"Sent {follow_up_days}+ days ago with no later reply in the thread.",
            "medium", "gmail",
        ))

    return sorted(items, key=lambda item: (
        URGENCY_ORDER[item["urgency"]], item["type"],
        item["title"].lower(), item["source"],
    ))


def build_attention_items(
    gmail_metadata,
    calendar_events,
    project_next_actions,
    approval_items,
    source_errors,
    now,
    imminent_minutes=120,
):
    """Build deterministic attention items from already-fetched data.

    ``now`` must be timezone-aware. Project actions are accepted as part of the
    collector contract but intentionally do not produce items in this version.
    """
    if now.tzinfo is None:
        raise ValueError("now must be timezone-aware")

    if imminent_minutes < 0:
        raise ValueError("imminent_minutes must not be negative")

    # Reserved for a later phase of the collector.
    _ = project_next_actions

    items = []

    reply_due_items = [
        item
        for item in detect_reply_due_items(gmail_metadata, now)
        if item["type"] == "reply_due"
    ]
    items.extend(reply_due_items)
    reply_due_counts = Counter(
        (item["title"], item["reason"])
        for item in reply_due_items
    )

    for message in gmail_metadata or []:
        labels = _email_labels(message)

        if "UNREAD" not in labels or "IMPORTANT" not in labels:
            continue

        reply_due = _reply_due_item(message)
        reply_due_key = (reply_due["title"], reply_due["reason"])
        if reply_due_counts[reply_due_key]:
            reply_due_counts[reply_due_key] -= 1
            continue

        subject = message.get("subject") or "(no subject)"
        sender = message.get("from") or "unknown sender"
        items.append(
            _attention_item(
                "important_unread_email",
                subject,
                f"Unread email marked important from {sender}.",
                "high",
                "gmail",
            )
        )

    timed_events = []
    for event in calendar_events or []:
        start = _parse_datetime(event.get("start"))
        end = _parse_datetime(event.get("end"))

        if start is None:
            continue

        title = event.get("summary") or "Untitled event"
        timed_events.append((start, end, title, event.get("id") or ""))

        minutes_until = int((start - now).total_seconds() // 60)
        if 0 <= minutes_until <= imminent_minutes:
            items.append(
                _attention_item(
                    "imminent_meeting",
                    title,
                    f"Starts in {minutes_until} minutes.",
                    "urgent" if minutes_until <= 30 else "high",
                    "calendar",
                )
            )

    timed_events.sort(key=lambda event: (event[0], event[2].lower(), event[3]))
    for index, first in enumerate(timed_events):
        first_start, first_end, first_title, _ = first
        if first_end is None or first_end <= first_start:
            continue

        for second in timed_events[index + 1:]:
            second_start, second_end, second_title, _ = second
            if second_start >= first_end:
                break
            if second_end is None or second_end <= second_start:
                continue
            if first_start < second_end and second_start < first_end:
                items.append(
                    _attention_item(
                        "calendar_conflict",
                        f"Calendar conflict: {first_title} and {second_title}",
                        "These calendar events overlap.",
                        "urgent",
                        "calendar",
                    )
                )

    for approval in approval_items or []:
        status = approval.get("status")
        execution_status = approval.get("execution_status")

        if status == "WAITING_APPROVAL":
            title = approval.get("summary") or "Approval waiting"
            action_type = approval.get("action_type") or "action"
            items.append(
                _attention_item(
                    "waiting_approval",
                    title,
                    f"{action_type} is waiting for your approval.",
                    "high",
                    "approvals",
                )
            )
            continue

        if (
            status == "APPROVED"
            and execution_status in {"PENDING", "EXECUTING", "FAILED"}
        ):
            title = approval.get("summary") or "Approved action unfinished"
            items.append(
                _attention_item(
                    "unfinished_action",
                    title,
                    "This approved action has not finished. Review it before "
                    "taking any further action.",
                    "high",
                    "approvals",
                )
            )

    for source, error in sorted((source_errors or {}).items()):
        if not error:
            continue

        items.append(
            _attention_item(
                "source_error",
                f"{source} data unavailable",
                "Some information may be missing. Try again later.",
                "low",
                source,
            )
        )

    return sorted(
        items,
        key=_attention_item_sort_key,
    )
