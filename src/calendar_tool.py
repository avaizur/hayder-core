import json
import urllib.parse
import urllib.request
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo


CALENDAR_BASE_URL = (
    "https://www.googleapis.com/calendar/v3"
)

USER_TIMEZONE = ZoneInfo("Europe/London")


def google_calendar_get(
    url,
    access_token,
):
    request = urllib.request.Request(
        url,
        headers={
            "Authorization":
                "Bearer " + access_token
        },
        method="GET",
    )

    with urllib.request.urlopen(
        request,
        timeout=15,
    ) as response:
        return json.loads(
            response
            .read()
            .decode("utf-8")
        )


def day_window(day="today"):
    now = datetime.now(
        USER_TIMEZONE
    )

    if day == "tomorrow":
        target = (
            now
            + timedelta(days=1)
        ).date()
    else:
        target = now.date()

    start = datetime(
        target.year,
        target.month,
        target.day,
        0,
        0,
        0,
        tzinfo=USER_TIMEZONE,
    )

    end = (
        start
        + timedelta(days=1)
    )

    return start, end


def calendar_events(
    access_token,
    day="today",
    max_results=10,
):
    start, end = day_window(
        day
    )

    params = urllib.parse.urlencode(
        {
            "timeMin":
                start.isoformat(),
            "timeMax":
                end.isoformat(),
            "singleEvents":
                "true",
            "orderBy":
                "startTime",
            "maxResults":
                max_results,
            "timeZone":
                "Europe/London",
        }
    )

    url = (
        CALENDAR_BASE_URL
        + "/calendars/primary/events?"
        + params
    )

    data = google_calendar_get(
        url,
        access_token,
    )

    events = []

    for item in data.get(
        "items",
        [],
    ):
        start_data = item.get(
            "start",
            {},
        )

        end_data = item.get(
            "end",
            {},
        )

        events.append(
            {
                "id":
                    item.get("id"),

                "summary":
                    item.get(
                        "summary",
                        "Untitled event",
                    ),

                "start":
                    (
                        start_data.get(
                            "dateTime"
                        )
                        or
                        start_data.get(
                            "date"
                        )
                    ),

                "end":
                    (
                        end_data.get(
                            "dateTime"
                        )
                        or
                        end_data.get(
                            "date"
                        )
                    ),

                "location":
                    item.get(
                        "location",
                        "",
                    ),

                "status":
                    item.get(
                        "status",
                        "",
                    ),
            }
        )

    return events


def event_time_text(value):
    if not value:
        return ""

    if "T" not in value:
        return "all day"

    try:
        dt = datetime.fromisoformat(
            value.replace(
                "Z",
                "+00:00",
            )
        )

        dt = dt.astimezone(
            USER_TIMEZONE
        )

        return dt.strftime(
            "%-I:%M %p"
        )

    except Exception:
        return value


def event_minutes_from_now(value):
    """Return minutes until a calendar event.

    Negative means the event has already started/passed.
    Returns None for all-day or invalid values.
    """

    if not value or "T" not in value:
        return None

    try:
        dt = datetime.fromisoformat(
            value.replace(
                "Z",
                "+00:00",
            )
        )

        dt = dt.astimezone(
            USER_TIMEZONE
        )

        now = datetime.now(
            USER_TIMEZONE
        )

        seconds = (
            dt - now
        ).total_seconds()

        return int(
            seconds // 60
        )

    except Exception:
        return None


def spoken_calendar_summary(
    events,
    day="today",
):
    label = (
        "tomorrow"
        if day == "tomorrow"
        else "today"
    )

    if not events:
        return (
            f"Your calendar is clear "
            f"{label}."
        )

    parts = [
        (
            f"You have {len(events)} "
            f"calendar event"
            + (
                "s"
                if len(events) != 1
                else ""
            )
            + f" {label}."
        )
    ]

    for index, event in enumerate(
        events,
        start=1,
    ):
        time_text = event_time_text(
            event.get("start")
        )

        parts.append(
            f"{index}. "
            f"{event.get('summary')}, "
            f"at {time_text}."
        )

    return " ".join(parts)

