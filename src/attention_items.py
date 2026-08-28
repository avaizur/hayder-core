from datetime import datetime


URGENCY_ORDER = {
    "urgent": 0,
    "high": 1,
    "medium": 2,
}


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

    for message in gmail_metadata or []:
        labels = _email_labels(message)

        if "UNREAD" not in labels or "IMPORTANT" not in labels:
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
        if approval.get("status") != "WAITING_APPROVAL":
            continue

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

    for source, error in sorted((source_errors or {}).items()):
        if not error:
            continue

        reason = error if isinstance(error, str) else "The source could not be read."
        items.append(
            _attention_item(
                "source_error",
                f"{source} data unavailable",
                reason,
                "medium",
                source,
            )
        )

    return sorted(
        items,
        key=lambda item: (
            URGENCY_ORDER[item["urgency"]],
            item["type"],
            item["title"].lower(),
            item["source"],
        ),
    )
