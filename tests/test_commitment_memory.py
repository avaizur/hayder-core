import importlib
import json
import os
import sys
import unittest
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
        return SimpleNamespace(Table=lambda name: SimpleNamespace(name=name))

    def client(self, service):
        return SimpleNamespace()


sys.modules.setdefault("boto3", FakeBoto3())
commitment_memory = importlib.import_module("commitment_memory")
app = importlib.import_module("app")


class CommitmentDetectionTests(unittest.TestCase):
    def test_detects_explicit_commitment_and_iso_due_date(self):
        detected = commitment_memory.detect_commitment(
            "I will send the report to Maya by 2026-09-05."
        )

        self.assertEqual(detected["commitment"], "send the report to Maya")
        self.assertEqual(detected["due_at"], "2026-09-05T23:59:59.999999+00:00")
        self.assertEqual(
            detected["source_phrase"],
            "I will send the report to Maya by 2026-09-05.",
        )

    def test_rejects_vague_conditional_and_non_first_person_phrases(self):
        rejected = [
            "I'll handle it.",
            "I will if Maya replies.",
            "I will send it if Maya replies.",
            "I promise not to call the supplier.",
            "I might send the report.",
            "We will send the report.",
            "Will you send the report?",
        ]

        for phrase in rejected:
            with self.subTest(phrase=phrase):
                self.assertIsNone(commitment_memory.detect_commitment(phrase))

    def test_saves_only_commitment_fields_in_existing_table(self):
        table = Mock()
        detected = commitment_memory.detect_commitment(
            "I promise to call the supplier."
        )

        item = commitment_memory.save_commitment(
            table,
            "user-1",
            detected,
            created_at="2026-09-02T10:00:00+00:00",
        )

        self.assertEqual(item["status"], "OPEN")
        self.assertEqual(item["commitment"], "call the supplier")
        self.assertNotIn("due_at", item)
        self.assertEqual(table.put_item.call_args.kwargs["Item"], item)


class CommitmentChatTests(unittest.TestCase):
    def test_chat_saves_commitment_without_external_action(self):
        memory_table = Mock()

        with (
            patch.object(app, "table", memory_table),
            patch.object(app, "resolve_intent") as resolve_intent,
            patch.object(app, "call_openai") as call_openai,
            patch.object(app, "create_approval_record") as create_approval,
        ):
            result = app.chat(
                "user-1",
                {"message": "I will email the supplier tomorrow."},
            )

        body = json.loads(result["body"])
        self.assertEqual(result["statusCode"], 201)
        self.assertEqual(body["tool"], "commitment_memory")
        memory_table.put_item.assert_called_once()
        resolve_intent.assert_not_called()
        call_openai.assert_not_called()
        create_approval.assert_not_called()

    def test_daily_briefing_resurfaces_only_open_commitments(self):
        memory_table = Mock()
        memory_table.query.side_effect = [
            {"Items": []},
            {
                "Items": [
                    {"commitment": "call the supplier", "status": "OPEN"},
                    {"commitment": "send the invoice", "status": "DONE"},
                ]
            },
        ]
        approval_table = Mock()
        approval_table.query.return_value = {"Items": []}

        with (
            patch.object(app, "resolve_intent", return_value={"intent": "daily_briefing"}),
            patch.object(app, "gmail_latest_messages", return_value={"messages": []}),
            patch.object(app, "important_summary", return_value={"messages": []}),
            patch.object(app, "refresh_google_access_token", return_value=("token", None)),
            patch.object(app, "calendar_events", return_value=[]),
            patch.object(app, "table", memory_table),
            patch.object(app, "approval_table", approval_table),
        ):
            result = app.chat("user-1", {"message": "daily briefing"})

        body = json.loads(result["body"])
        self.assertEqual(
            body["briefing"]["commitments"],
            [{"commitment": "call the supplier", "status": "OPEN"}],
        )
        self.assertIn("Commitment: call the supplier", body["reply"])
        self.assertNotIn("send the invoice", body["reply"])


if __name__ == "__main__":
    unittest.main()
