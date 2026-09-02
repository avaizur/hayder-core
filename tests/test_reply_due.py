import importlib
import os
import sys
import unittest
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch
from urllib.parse import parse_qs, urlparse

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from attention_items import detect_reply_due_items

os.environ.setdefault("HAYDER_TABLE", "test-memory")
os.environ.setdefault("HAYDER_APPROVAL_TABLE", "test-approvals")
os.environ.setdefault("AWS_LAMBDA_FUNCTION_NAME", "test-function")


class FakeBoto3:
    def resource(self, service):
        return SimpleNamespace(Table=lambda name: SimpleNamespace(name=name))

    def client(self, service):
        return SimpleNamespace()


sys.modules.setdefault("boto3", FakeBoto3())
app = importlib.import_module("app")

NOW = datetime(2026, 8, 28, 9, 0, tzinfo=timezone.utc)


class DetectReplyDueItemsTests(unittest.TestCase):
    def test_detects_only_conservative_unread_reply_requests(self):
        messages = [
            {
                "subject": "Can you confirm the launch time?",
                "from": "Alex <alex@example.com>",
                "snippet": "Please reply when you can.",
                "labelIds": ["INBOX", "UNREAD", "IMPORTANT"],
            },
            {
                "subject": "Weekly newsletter",
                "from": "news@example.com",
                "snippet": "What do you think?",
                "labelIds": ["INBOX", "UNREAD", "IMPORTANT", "CATEGORY_PROMOTIONS"],
            },
            {
                "subject": "Can you review this?",
                "from": "person@example.com",
                "labelIds": ["INBOX", "IMPORTANT"],
            },
            {
                "subject": "Status update",
                "from": "person@example.com",
                "labelIds": ["INBOX", "UNREAD", "IMPORTANT"],
            },
        ]

        items = detect_reply_due_items(messages, NOW)

        self.assertEqual(len(items), 1)
        self.assertEqual(items[0]["type"], "reply_due")
        self.assertEqual(
            items[0]["title"],
            "Reply needed: Can you confirm the launch time?",
        )
        self.assertEqual(items[0]["reason"], "From Alex <alex@example.com>.")
        self.assertEqual(items[0]["source"], "gmail")

    def test_detects_old_sent_message_when_it_is_latest_in_thread(self):
        messages = [
            {
                "threadId": "waiting",
                "subject": "Proposal",
                "date": "Mon, 24 Aug 2026 09:00:00 +0000",
                "labelIds": ["SENT"],
            },
            {
                "threadId": "answered",
                "subject": "Question",
                "date": "Sun, 23 Aug 2026 09:00:00 +0000",
                "labelIds": ["SENT"],
            },
            {
                "threadId": "answered",
                "subject": "Re: Question",
                "date": "Mon, 24 Aug 2026 09:00:00 +0000",
                "labelIds": ["INBOX"],
            },
            {
                "threadId": "recent",
                "subject": "Recent note",
                "date": "Wed, 26 Aug 2026 10:00:00 +0000",
                "labelIds": ["SENT"],
            },
        ]

        items = detect_reply_due_items(messages, NOW)

        self.assertEqual(len(items), 1)
        self.assertEqual(items[0]["type"], "follow_up_due")
        self.assertEqual(items[0]["title"], "Proposal")
        self.assertEqual(items[0]["urgency"], "medium")

    def test_does_not_guess_follow_up_without_thread_or_valid_date(self):
        messages = [
            {
                "subject": "No thread",
                "date": "Sun, 23 Aug 2026 09:00:00 +0000",
                "labelIds": ["SENT"],
            },
            {
                "threadId": "bad-date",
                "subject": "No date",
                "date": "unknown",
                "labelIds": ["SENT"],
            },
        ]

        self.assertEqual(detect_reply_due_items(messages, NOW), [])

    def test_requires_timezone_aware_now(self):
        with self.assertRaisesRegex(ValueError, "timezone-aware"):
            detect_reply_due_items([], datetime(2026, 8, 28, 9, 0))


    def test_internal_date_and_id_deterministically_order_equal_timestamps(self):
        messages = [
            {
                "id": "a-sent",
                "threadId": "same-time",
                "subject": "Proposal",
                "internalDate": "1787562000000",
                "labelIds": ["SENT"],
            },
            {
                "id": "z-reply",
                "threadId": "same-time",
                "subject": "Re: Proposal",
                "internalDate": "1787562000000",
                "labelIds": ["INBOX"],
            },
        ]

        self.assertEqual(detect_reply_due_items(messages, NOW), [])

    def test_later_reply_in_complete_thread_prevents_follow_up(self):
        messages = [
            {
                "id": "old-sent",
                "threadId": "answered",
                "subject": "Question",
                "internalDate": "1787475600000",
                "labelIds": ["SENT"],
            },
            {
                "id": "later-reply",
                "threadId": "answered",
                "subject": "Re: Question",
                "internalDate": "1787562000000",
                "labelIds": ["INBOX"],
            },
        ]

        self.assertEqual(detect_reply_due_items(messages, NOW), [])


class GmailFollowUpFetchTests(unittest.TestCase):
    def test_fetches_all_candidate_pages_and_complete_unique_threads(self):
        calls = []

        def fake_get(url, token):
            calls.append(url)
            parsed = urlparse(url)
            query = parse_qs(parsed.query)
            if parsed.path.endswith("/messages"):
                self.assertEqual(query["q"], ["in:sent older_than:3d"])
                if "pageToken" not in query:
                    return {
                        "messages": [
                            {"id": "candidate-1", "threadId": "thread-b"},
                            {"id": "candidate-2", "threadId": "thread-b"},
                        ],
                        "nextPageToken": "next",
                    }
                return {
                    "messages": [
                        {"id": "candidate-3", "threadId": "thread-a"}
                    ]
                }

            thread_id = parsed.path.rsplit("/", 1)[-1]
            return {
                "messages": [{
                    "id": "message-" + thread_id,
                    "threadId": thread_id,
                    "labelIds": ["SENT"],
                    "internalDate": "1787475600000",
                    "payload": {"headers": [
                        {"name": "From", "value": "me@example.com"},
                        {"name": "Subject", "value": "Proposal"},
                    ]},
                }]
            }

        with (
            patch.object(
                app,
                "refresh_google_access_token",
                return_value=("token", {}),
            ),
            patch.object(app, "google_api_get", side_effect=fake_get),
        ):
            result = app.gmail_follow_up_messages("user-1")

        self.assertEqual(len(result["messages"]), 2)
        self.assertEqual(
            set(result["messages"][0]),
            {"id", "threadId", "labelIds", "internalDate", "from", "subject"},
        )
        self.assertEqual(
            [urlparse(url).path for url in calls if "/threads/" in url],
            [
                "/gmail/v1/users/me/threads/thread-a",
                "/gmail/v1/users/me/threads/thread-b",
            ],
        )


if __name__ == "__main__":
    unittest.main()
