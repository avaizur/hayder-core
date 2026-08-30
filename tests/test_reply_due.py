import sys
import unittest
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from attention_items import detect_reply_due_items

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


if __name__ == "__main__":
    unittest.main()
