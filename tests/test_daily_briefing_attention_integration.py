import importlib
import json
import os
import sys
import unittest
from datetime import timezone
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch


ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
sys.path.insert(0, str(SRC))

os.environ.setdefault("HAYDER_TABLE", "test-memory")
os.environ.setdefault("HAYDER_APPROVAL_TABLE", "test-approvals")
os.environ.setdefault("AWS_LAMBDA_FUNCTION_NAME", "test-function")


class FakeBoto3:
    def resource(self, service):
        return SimpleNamespace(
            Table=lambda name: SimpleNamespace(name=name),
        )

    def client(self, service):
        return SimpleNamespace()


sys.modules.setdefault("boto3", FakeBoto3())
app = importlib.import_module("app")


class DailyBriefingAttentionIntegrationTests(unittest.TestCase):
    def test_builds_and_renders_attention_from_fetched_briefing_data(self):
        gmail_messages = [
            {
                "subject": "Action required",
                "from": "person@example.com",
                "labelIds": ["UNREAD", "IMPORTANT"],
            }
        ]
        events = [
            {
                "summary": "Planning",
                "start": "2099-08-28T09:30:00Z",
                "end": "2099-08-28T10:00:00Z",
            }
        ]
        projects = [{"project": "Hayder", "next_action": "Ship"}]
        approvals = [
            {
                "summary": "Deploy release",
                "action_type": "deployment",
                "status": "WAITING_APPROVAL",
            }
        ]
        project_table = Mock()
        project_table.query.return_value = {"Items": projects}
        approval_table = Mock()
        approval_table.query.return_value = {"Items": approvals}
        attention_items = [
            {
                "type": "waiting_approval",
                "title": "Deploy release",
                "reason": "deployment is waiting for your approval.",
                "urgency": "high",
                "source": "approvals",
            }
        ]

        with (
            patch.object(app, "resolve_intent", return_value={"intent": "daily_briefing"}),
            patch.object(app, "gmail_latest_messages", return_value={"messages": gmail_messages}),
            patch.object(app, "important_summary", return_value={"messages": []}),
            patch.object(app, "refresh_google_access_token", return_value=("token", None)),
            patch.object(app, "calendar_events", return_value=events),
            patch.object(app, "table", project_table),
            patch.object(app, "approval_table", approval_table),
            patch.object(app, "build_attention_items", return_value=attention_items) as build,
        ):
            result = app.chat("user-1", {"message": "daily briefing"})

        body = json.loads(result["body"])
        inputs = build.call_args.kwargs
        self.assertIs(inputs["gmail_metadata"], gmail_messages)
        self.assertIs(inputs["calendar_events"], events)
        self.assertIs(inputs["project_next_actions"], projects)
        self.assertIs(inputs["approval_items"], approvals)
        self.assertEqual(inputs["source_errors"], {})
        self.assertEqual(inputs["now"].tzinfo, timezone.utc)
        self.assertEqual(body["briefing"]["attention_items"], attention_items)
        self.assertIn("Needs your attention: Deploy release.", body["reply"])

    def test_renders_approved_unfinished_action_as_safe_reminder(self):
        approval_table = Mock()
        approval_table.query.return_value = {
            "Items": [
                {
                    "summary": "Send customer update",
                    "status": "APPROVED",
                    "execution_status": "FAILED",
                    "execution_error": "private provider failure details",
                }
            ]
        }
        project_table = Mock()
        project_table.query.return_value = {"Items": []}

        with (
            patch.object(app, "resolve_intent", return_value={"intent": "daily_briefing"}),
            patch.object(app, "gmail_latest_messages", return_value={"messages": []}),
            patch.object(app, "important_summary", return_value={"messages": []}),
            patch.object(app, "refresh_google_access_token", return_value=("token", None)),
            patch.object(app, "calendar_events", return_value=[]),
            patch.object(app, "table", project_table),
            patch.object(app, "approval_table", approval_table),
        ):
            result = app.chat("user-1", {"message": "daily briefing"})

        body = json.loads(result["body"])
        self.assertEqual(
            body["briefing"]["attention_items"],
            [
                {
                    "type": "unfinished_action",
                    "title": "Send customer update",
                    "reason": (
                        "This approved action has not finished. Review it before "
                        "taking any further action."
                    ),
                    "urgency": "high",
                    "source": "approvals",
                }
            ],
        )
        self.assertIn("Needs your attention: Send customer update.", body["reply"])
        self.assertNotIn("private provider failure details", str(body))

    def test_passes_fetch_errors_to_attention_builder(self):
        project_table = Mock()
        project_table.query.side_effect = RuntimeError("projects failed")
        approval_table = Mock()
        approval_table.query.side_effect = RuntimeError("approvals failed")

        with (
            patch.object(app, "resolve_intent", return_value={"intent": "daily_briefing"}),
            patch.object(app, "gmail_latest_messages", side_effect=RuntimeError("gmail failed")),
            patch.object(app, "refresh_google_access_token", side_effect=RuntimeError("calendar failed")),
            patch.object(app, "table", project_table),
            patch.object(app, "approval_table", approval_table),
            patch.object(app, "build_attention_items", return_value=[]) as build,
        ):
            result = app.chat("user-1", {"message": "daily briefing"})

        self.assertEqual(result["statusCode"], 200)
        self.assertEqual(
            build.call_args.kwargs["source_errors"],
            {
                "gmail": "Gmail data could not be loaded",
                "calendar": "Calendar data could not be loaded",
                "projects": "Project data could not be loaded",
                "approvals": "Approvals could not be loaded",
            },
        )


if __name__ == "__main__":
    unittest.main()
