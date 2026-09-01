import base64
import importlib
import json
import os
import sys
import unittest
from email import policy
from email.parser import BytesParser
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


class ApprovalEmailExecutionTests(unittest.TestCase):
    def test_structured_email_is_validated_and_frozen_at_creation(self):
        approval_table = Mock()
        payload = {
            "action_type": "email_send",
            "target": "customer@example.com",
            "summary": "Send update",
            "details": {
                "to": " customer@example.com ",
                "subject": "Status",
                "body": "Ready",
                "ignored": "not executable",
            },
        }

        with patch.object(app, "approval_table", approval_table):
            result = app.create_approval("user-1", payload)

        item = approval_table.put_item.call_args.kwargs["Item"]
        self.assertEqual(result["statusCode"], 201)
        self.assertEqual(
            item["details"],
            {
                "to": "customer@example.com",
                "subject": "Status",
                "body": "Ready",
            },
        )
        self.assertEqual(item["execution_status"], "PENDING")
        self.assertIsNone(item["executed_at"])

    def test_structured_email_requires_to_subject_and_body(self):
        approval_table = Mock()
        with patch.object(app, "approval_table", approval_table):
            result = app.create_approval(
                "user-1",
                {
                    "action_type": "email_send",
                    "target": "customer@example.com",
                    "summary": "Send update",
                    "details": {"to": "not-an-email", "body": "Ready"},
                },
            )

        body = json.loads(result["body"])
        self.assertEqual(result["statusCode"], 400)
        self.assertEqual(body["invalid"], ["subject", "to"])
        approval_table.put_item.assert_not_called()

    def test_successful_execution_claims_then_sends_and_completes(self):
        claimed = {
            "status": "APPROVED",
            "action_type": "email_send",
            "details": {
                "to": "customer@example.com",
                "subject": "Status",
                "body": "Ready",
            },
        }
        executed = {**claimed, "execution_status": "EXECUTED"}

        with (
            patch.object(app, "claim_email_execution", return_value=claimed),
            patch.object(app, "gmail_send_email") as send,
            patch.object(app, "finish_email_execution", return_value=executed) as finish,
        ):
            result = app.execute_approved_email("user-1", "approval-1")

        send.assert_called_once_with("user-1", claimed["details"])
        finish.assert_called_once_with(
            "user-1", "approval-1", "EXECUTED"
        )
        self.assertEqual(result["execution_status"], "EXECUTED")

    def test_duplicate_or_failed_execution_is_never_sent_again(self):
        claimed = {
            "status": "APPROVED",
            "action_type": "email_send",
            "details": {
                "to": "customer@example.com",
                "subject": "Status",
                "body": "Ready",
            },
        }
        failed = {**claimed, "execution_status": "FAILED"}

        with (
            patch.object(
                app, "claim_email_execution", side_effect=[claimed, None]
            ),
            patch.object(
                app, "gmail_send_email", side_effect=RuntimeError("send failed")
            ) as send,
            patch.object(app, "finish_email_execution", return_value=failed) as finish,
            patch.object(app, "get_approval_record", return_value=failed),
        ):
            first = app.execute_approved_email("user-1", "approval-1")
            second = app.execute_approved_email("user-1", "approval-1")

        self.assertEqual(send.call_count, 1)
        finish.assert_called_once_with(
            "user-1", "approval-1", "FAILED", "send failed"
        )
        self.assertEqual(first["execution_status"], "FAILED")
        self.assertEqual(second["execution_status"], "FAILED")

    def test_chat_created_email_without_frozen_fields_fails_without_send(self):
        claimed = {
            "status": "APPROVED",
            "action_type": "email_send",
            "details": {
                "source": "chat",
                "original_message": "send the email",
            },
        }
        failed = {**claimed, "execution_status": "FAILED"}

        with (
            patch.object(app, "claim_email_execution", return_value=claimed),
            patch.object(app, "gmail_send_email") as send,
            patch.object(app, "finish_email_execution", return_value=failed) as finish,
        ):
            result = app.execute_approved_email("user-1", "approval-1")

        send.assert_not_called()
        finish.assert_called_once_with(
            "user-1",
            "approval-1",
            "FAILED",
            "INVALID_EMAIL_DETAILS",
        )
        self.assertEqual(result["execution_status"], "FAILED")

    def test_gmail_send_uses_gmail_send_endpoint_and_rfc_message(self):
        with (
            patch.object(
                app, "refresh_google_access_token", return_value=("token", {})
            ),
            patch.object(app, "google_api_post", return_value={"id": "message-1"}) as post,
        ):
            result = app.gmail_send_email(
                "user-1",
                {
                    "to": "customer@example.com",
                    "subject": "Status",
                    "body": "Ready",
                },
            )

        url, token, payload = post.call_args.args
        padding = "=" * (-len(payload["raw"]) % 4)
        message = BytesParser(policy=policy.default).parsebytes(
            base64.urlsafe_b64decode(payload["raw"] + padding)
        )
        self.assertEqual(url, app.GMAIL_BASE_URL + "/users/me/messages/send")
        self.assertEqual(token, "token")
        self.assertEqual(message["To"], "customer@example.com")
        self.assertEqual(message["Subject"], "Status")
        self.assertEqual(message.get_content().strip(), "Ready")
        self.assertEqual(result, {"id": "message-1"})

    def test_chat_and_http_approval_use_shared_orchestration(self):
        item = {
            "approval_id": "00000000-0000-0000-0000-000000000001",
            "status": "APPROVED",
            "action_type": "email_send",
            "execution_status": "EXECUTED",
            "summary": "Send update",
        }
        approval_id = item["approval_id"]

        with patch.object(
            app, "decide_approval", return_value=(item, None)
        ) as decide:
            chat_result = app.chat(
                "user-1", {"message": "Approve " + approval_id}
            )
        decide.assert_called_once_with("user-1", approval_id, "APPROVED")
        self.assertEqual(json.loads(chat_result["body"])["execution_status"], "EXECUTED")

        event = {
            "rawPath": "/approval/" + approval_id + "/approve",
            "pathParameters": {"approval_id": approval_id},
            "requestContext": {
                "http": {"method": "POST"},
                "authorizer": {"jwt": {"claims": {"sub": "user-1"}}},
            },
        }
        with patch.object(
            app, "decide_approval", return_value=(item, None)
        ) as decide:
            http_result = app.lambda_handler(event, None)
        decide.assert_called_once_with("user-1", approval_id, "APPROVED")
        self.assertEqual(json.loads(http_result["body"])["execution_status"], "EXECUTED")

    def test_claim_is_conditioned_on_approved_email_pending_state(self):
        table = Mock()
        table.update_item.return_value = {
            "Attributes": {"execution_status": "EXECUTING"}
        }

        with patch.object(app, "approval_table", table):
            result = app.claim_email_execution("user-1", "approval-1")

        call = table.update_item.call_args.kwargs
        self.assertEqual(result["execution_status"], "EXECUTING")
        self.assertEqual(
            call["ExpressionAttributeValues"][":pending"], "PENDING"
        )
        self.assertEqual(
            call["ExpressionAttributeValues"][":executing"], "EXECUTING"
        )
        self.assertIn(
            "#action_type = :email_send", call["ConditionExpression"]
        )

    def test_other_approval_types_remain_decision_only(self):
        deployment = {
            "status": "APPROVED",
            "action_type": "deployment",
            "execution_status": "PENDING",
        }
        with (
            patch.object(
                app, "update_approval_status", return_value=(deployment, None)
            ),
            patch.object(app, "execute_approved_email") as execute,
        ):
            item, error = app.decide_approval(
                "user-1", "approval-1", "APPROVED"
            )

        execute.assert_not_called()
        self.assertIs(item, deployment)
        self.assertIsNone(error)

    def test_oauth_requests_gmail_send_scope(self):
        self.assertIn(
            "https://www.googleapis.com/auth/gmail.send",
            app.GOOGLE_SCOPE,
        )


if __name__ == "__main__":
    unittest.main()
