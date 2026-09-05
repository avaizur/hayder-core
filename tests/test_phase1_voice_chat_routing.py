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
        return SimpleNamespace(
            Table=lambda name: SimpleNamespace(
                name=name,
                get_item=Mock(return_value={}),
                put_item=Mock(return_value={}),
                query=Mock(return_value={"Items": []}),
                scan=Mock(return_value={"Items": []}),
            ),
        )

    def client(self, service):
        return SimpleNamespace()


sys.modules.setdefault("boto3", FakeBoto3())
app = importlib.import_module("app")
intent_mod = importlib.import_module("intent")


class Phase1VoiceChatRoutingTests(unittest.TestCase):
    def setUp(self):
        self.mock_table = Mock()
        self.mock_table.get_item.return_value = {}
        self.mock_table.put_item.return_value = {}
        self.mock_table.query.return_value = {"Items": []}
        self.mock_approval_table = Mock()
        self.mock_approval_table.get_item.return_value = {}
        self.mock_approval_table.put_item.return_value = {}
        self.mock_approval_table.query.return_value = {"Items": []}

    def test_routing_phrase_1_connect_google_account(self):
        """Phrase 1: 'Connect my Google account' routes to Google connect onboarding."""
        event = {"headers": {"host": "api.hayder.test"}}
        with patch.object(app, "table", self.mock_table), \
             patch.object(intent_mod, "table", self.mock_table), \
             patch.object(app, "get_google_credentials", return_value=("fake-client-id", "fake-client-secret")), \
             patch.object(app, "call_openai") as mock_openai:

            result = app.chat(
                "user-1",
                {"message": "Connect my Google account"},
                event=event,
            )

        mock_openai.assert_not_called()
        self.assertEqual(result["statusCode"], 200)
        body = json.loads(result["body"])
        self.assertEqual(body.get("tool"), "google_connect")
        self.assertIn("authorization_url", body)
        self.assertTrue(body["authorization_url"].startswith("https://accounts.google.com/o/oauth2/v2/auth"))
        self.assertIn("client_id=fake-client-id", body["authorization_url"])
        self.assertIn("reply", body)

    def test_routing_phrase_2_what_needs_my_attention(self):
        """Phrase 2: 'What needs my attention?' invokes attention/briefing capability."""
        with patch.object(app, "table", self.mock_table), \
             patch.object(intent_mod, "table", self.mock_table), \
             patch.object(app, "approval_table", self.mock_approval_table), \
             patch.object(app, "gmail_latest_messages", return_value={"messages": []}), \
             patch.object(app, "gmail_follow_up_messages", return_value={"messages": []}), \
             patch.object(app, "refresh_google_access_token", return_value=("token", {})), \
             patch.object(app, "calendar_events", return_value=[]), \
             patch.object(app, "call_openai") as mock_openai:

            result = app.chat(
                "user-1",
                {"message": "What needs my attention?"},
            )

        mock_openai.assert_not_called()
        self.assertEqual(result["statusCode"], 200)
        body = json.loads(result["body"])
        self.assertEqual(body.get("tool"), "daily_attention_briefing")
        self.assertIn("briefing", body)
        self.assertIn("reply", body)

    def test_routing_phrase_3_draft_email_to_myself_creates_waiting_approval(self):
        """Phrase 3: 'Draft an email to myself saying Hayder launch test successful' creates WAITING_APPROVAL when email resolved."""
        with patch.object(app, "approval_table", self.mock_approval_table), \
             patch.object(app, "table", self.mock_table), \
             patch.object(intent_mod, "table", self.mock_table), \
             patch.object(app, "load_google_connection", return_value={"gmail_email": "user@gmail.com"}), \
             patch.object(app, "call_openai") as mock_openai, \
             patch.object(app, "gmail_send_email") as mock_send:

            result = app.chat(
                "user-1",
                {"message": "Draft an email to myself saying Hayder launch test successful"},
            )

        mock_openai.assert_not_called()
        mock_send.assert_not_called()
        self.assertEqual(result["statusCode"], 200)
        body = json.loads(result["body"])

        self.assertTrue(body.get("approval_required"))
        self.assertEqual(body.get("status"), "WAITING_APPROVAL")
        self.assertEqual(body.get("action_type"), "email_send")
        self.assertEqual(body.get("target"), "user@gmail.com")
        self.assertIn("Hayder launch test successful", body.get("reply", ""))

        # Verify DynamoDB record creation
        self.mock_approval_table.put_item.assert_called_once()
        saved_item = self.mock_approval_table.put_item.call_args.kwargs["Item"]
        self.assertEqual(saved_item["status"], "WAITING_APPROVAL")
        self.assertEqual(saved_item["action_type"], "email_send")
        self.assertEqual(saved_item["target"], "user@gmail.com")
        self.assertEqual(saved_item["details"]["to"], "user@gmail.com")
        self.assertIn("Hayder launch test successful", saved_item["details"]["subject"])
        self.assertIn("Hayder launch test successful", saved_item["details"]["body"])

    def test_routing_phrase_3_draft_email_to_myself_unresolvable_never_creates_approval_to_example_com(self):
        """Proves 'email myself' never creates an approval to example.com when real email cannot be resolved."""
        with patch.object(app, "approval_table", self.mock_approval_table), \
             patch.object(app, "table", self.mock_table), \
             patch.object(intent_mod, "table", self.mock_table), \
             patch.object(app, "load_google_connection", return_value=None), \
             patch.object(app, "call_openai") as mock_openai, \
             patch.object(app, "gmail_send_email") as mock_send:

            result = app.chat(
                "user-1",
                {"message": "Draft an email to myself saying Hayder launch test successful"},
            )

        mock_openai.assert_not_called()
        mock_send.assert_not_called()
        self.mock_approval_table.put_item.assert_not_called()

        self.assertEqual(result["statusCode"], 200)
        body = json.loads(result["body"])
        self.assertFalse(body.get("approval_required"))
        self.assertNotIn("approval_id", body)
        self.assertNotIn("example.com", json.dumps(body))
        self.assertIn("Provide a complete email draft with recipient", body.get("reply", ""))

    def test_control_read_latest_emails_routes_to_gmail(self):
        """Control: 'Read my latest emails' correctly routes to Gmail read path."""
        with patch.object(app, "table", self.mock_table), \
             patch.object(intent_mod, "table", self.mock_table), \
             patch.object(app, "gmail_latest_messages", return_value={"messages": [{"id": "1", "subject": "Test"}]}):

            result = app.chat(
                "user-1",
                {"message": "Read my latest emails"},
            )

        self.assertEqual(result["statusCode"], 200)
        body = json.loads(result["body"])
        self.assertEqual(body.get("tool"), "gmail_readonly")

    def test_control_calendar_readonly_routes_correctly(self):
        """Control: Calendar read-only query routes to calendar_readonly."""
        with patch.object(app, "table", self.mock_table), \
             patch.object(intent_mod, "table", self.mock_table), \
             patch.object(app, "refresh_google_access_token", return_value=("token", {})), \
             patch.object(app, "calendar_events", return_value=[]):

            result = app.chat(
                "user-1",
                {"message": "Check my calendar"},
            )

        self.assertEqual(result["statusCode"], 200)
        body = json.loads(result["body"])
        self.assertEqual(body.get("tool"), "calendar_readonly")


if __name__ == "__main__":
    unittest.main()
