import sys
import unittest
from datetime import datetime, timezone
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
sys.path.insert(0, str(SRC))

from attention_items import build_attention_items


NOW = datetime(2026, 8, 28, 9, 0, tzinfo=timezone.utc)


class BuildAttentionItemsTests(unittest.TestCase):
    def build(self, **overrides):
        inputs = {
            "gmail_metadata": [],
            "calendar_events": [],
            "project_next_actions": [],
            "approval_items": [],
            "source_errors": {},
            "now": NOW,
        }
        inputs.update(overrides)
        return build_attention_items(**inputs)

    def test_includes_only_email_that_is_both_important_and_unread(self):
        items = self.build(
            gmail_metadata=[
                {
                    "subject": "Action required",
                    "from": "person@example.com",
                    "labelIds": ["INBOX", "UNREAD", "IMPORTANT"],
                },
                {"subject": "Read", "labelIds": ["IMPORTANT"]},
                {"subject": "Ordinary", "labelIds": ["UNREAD"]},
            ]
        )

        self.assertEqual(len(items), 1)
        self.assertEqual(items[0]["type"], "important_unread_email")
        self.assertEqual(items[0]["title"], "Action required")
        self.assertEqual(items[0]["urgency"], "high")

    def test_includes_reply_due_without_duplicate_important_unread_item(self):
        items = self.build(
            gmail_metadata=[
                {
                    "subject": "Can you confirm the launch time?",
                    "from": "Alex <alex@example.com>",
                    "snippet": "Please reply when you can.",
                    "labelIds": ["INBOX", "UNREAD", "IMPORTANT"],
                }
            ]
        )

        self.assertEqual(len(items), 1)
        self.assertEqual(items[0]["type"], "reply_due")
        self.assertEqual(items[0]["title"], "Can you confirm the launch time?")

    def test_does_not_include_follow_up_due_items(self):
        items = self.build(
            gmail_metadata=[
                {
                    "threadId": "waiting",
                    "subject": "Proposal",
                    "date": "Mon, 24 Aug 2026 09:00:00 +0000",
                    "labelIds": ["SENT"],
                }
            ]
        )

        self.assertEqual(items, [])

    def test_marks_imminent_meetings_and_ignores_past_or_all_day_events(self):
        items = self.build(
            calendar_events=[
                {
                    "summary": "Stand-up",
                    "start": "2026-08-28T09:20:00Z",
                    "end": "2026-08-28T09:40:00Z",
                },
                {
                    "summary": "Later meeting",
                    "start": "2026-08-28T10:15:00Z",
                    "end": "2026-08-28T10:45:00Z",
                },
                {"summary": "All day", "start": "2026-08-28", "end": "2026-08-29"},
                {
                    "summary": "Past",
                    "start": "2026-08-28T08:00:00Z",
                    "end": "2026-08-28T08:30:00Z",
                },
            ]
        )

        imminent = [item for item in items if item["type"] == "imminent_meeting"]
        self.assertEqual([item["title"] for item in imminent], ["Stand-up", "Later meeting"])
        self.assertEqual([item["urgency"] for item in imminent], ["urgent", "high"])

    def test_detects_overlaps_but_not_adjacent_events(self):
        items = self.build(
            calendar_events=[
                {
                    "summary": "Alpha",
                    "start": "2026-08-28T12:00:00Z",
                    "end": "2026-08-28T13:00:00Z",
                },
                {
                    "summary": "Beta",
                    "start": "2026-08-28T12:30:00Z",
                    "end": "2026-08-28T13:30:00Z",
                },
                {
                    "summary": "Gamma",
                    "start": "2026-08-28T13:30:00Z",
                    "end": "2026-08-28T14:00:00Z",
                },
            ]
        )

        conflicts = [item for item in items if item["type"] == "calendar_conflict"]
        self.assertEqual(len(conflicts), 1)
        self.assertEqual(conflicts[0]["title"], "Calendar conflict: Alpha and Beta")

    def test_includes_only_waiting_approvals(self):
        items = self.build(
            approval_items=[
                {
                    "summary": "Deploy release",
                    "action_type": "deployment",
                    "status": "WAITING_APPROVAL",
                },
                {"summary": "Old request", "status": "APPROVED"},
            ]
        )

        self.assertEqual(len(items), 1)
        self.assertEqual(items[0]["type"], "waiting_approval")
        self.assertEqual(items[0]["title"], "Deploy release")

    def test_adds_explicit_errors_and_ignores_false_flags(self):
        items = self.build(
            source_errors={
                "gmail": "Gmail timed out.",
                "calendar": True,
                "approvals": False,
            }
        )

        self.assertEqual([item["source"] for item in items], ["calendar", "gmail"])
        self.assertEqual(items[1]["reason"], "Gmail timed out.")

    def test_output_order_is_deterministic_and_projects_are_not_yet_emitted(self):
        inputs = {
            "gmail_metadata": [
                {"subject": "Zulu", "labelIds": ["IMPORTANT", "UNREAD"]},
                {"subject": "Alpha", "labelIds": ["UNREAD", "IMPORTANT"]},
            ],
            "project_next_actions": [{"project": "hayder", "next_action": "Ship it"}],
            "source_errors": {"gmail": True},
        }

        first = self.build(**inputs)
        second = self.build(**inputs)

        self.assertEqual(first, second)
        self.assertEqual([item["title"] for item in first], ["Alpha", "Zulu", "gmail data unavailable"])
        self.assertNotIn("Ship it", str(first))

    def test_requires_timezone_aware_now(self):
        with self.assertRaisesRegex(ValueError, "timezone-aware"):
            self.build(now=datetime(2026, 8, 28, 9, 0))


if __name__ == "__main__":
    unittest.main()
