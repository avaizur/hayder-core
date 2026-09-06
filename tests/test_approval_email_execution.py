import base64
import importlib
import json
import os
import sys
import unittest
from datetime import datetime, timedelta, timezone
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
    def test_chat_complete_email_draft_is_frozen_and_previewed(self):
        approval_table = Mock()

        with patch.object(app, "approval_table", approval_table):
            result = app.chat(
                "user-1",
                {
                    "message": "Send an email",
                    "email_draft": {
                        "to": " customer@example.com ",
                        "subject": " Status ",
                        "body": " Ready ",
                        "ignored": "not executable",
                    },
                },
            )

        response_body = json.loads(result["body"])
        item = approval_table.put_item.call_args.kwargs["Item"]
        expected = {
            "to": "customer@example.com",
            "subject": "Status",
            "body": "Ready",
        }
        self.assertEqual(item["details"], expected)
        self.assertEqual(response_body["email_draft"], expected)
        self.assertTrue(response_body["approval_required"])
        self.assertIn("To: customer@example.com", response_body["reply"])
        self.assertIn("Subject: Status", response_body["reply"])
        self.assertIn("Body:\nReady", response_body["reply"])
        self.assertIn("Nothing has been sent", response_body["reply"])

    def test_chat_labeled_complete_email_draft_is_structured(self):
        approval_table = Mock()
        message = (
            "Send email\n"
            "To: customer@example.com\n"
            "Subject: Status\n"
            "Body: Ready\nThanks"
        )

        with patch.object(app, "approval_table", approval_table):
            app.chat("user-1", {"message": message})

        item = approval_table.put_item.call_args.kwargs["Item"]
        self.assertEqual(
            item["details"],
            {
                "to": "customer@example.com",
                "subject": "Status",
                "body": "Ready\nThanks",
            },
        )

    def test_chat_incomplete_email_request_creates_no_approval(self):
        approval_table = Mock()

        with patch.object(app, "approval_table", approval_table):
            result = app.chat(
                "user-1",
                {
                    "message": "Send the email",
                    "email_draft": {
                        "to": "customer@example.com",
                        "body": "Ready",
                    },
                },
            )

        response_body = json.loads(result["body"])
        approval_table.put_item.assert_not_called()
        self.assertFalse(response_body["approval_required"])
        self.assertIn("not created an approval", response_body["reply"])
        self.assertIn("or sent anything", response_body["reply"])

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
        self.assertEqual(json.loads(chat_result["body"])["reply"], "Email sent.")

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

    def test_chat_email_failure_hides_internal_error(self):
        approval_id = "00000000-0000-0000-0000-000000000001"
        item = {
            "approval_id": approval_id,
            "status": "APPROVED",
            "action_type": "email_send",
            "execution_status": "FAILED",
            "execution_error": "secret upstream details",
        }

        with patch.object(
            app, "decide_approval", return_value=(item, None)
        ):
            result = app.chat(
                "user-1", {"message": "Approve " + approval_id}
            )

        response_body = json.loads(result["body"])
        self.assertEqual(response_body["execution_status"], "FAILED")
        self.assertIn("could not be sent", response_body["reply"])
        self.assertNotIn("secret upstream details", response_body["reply"])

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

    def test_conversational_approval_accepts_recent_pending_draft(self):
        now = datetime.now(timezone.utc)
        recent_time = (now - timedelta(minutes=5)).isoformat()
        item = {
            "approval_id": "00000000-0000-0000-0000-000000000001",
            "user_id": "user-1",
            "status": "WAITING_APPROVAL",
            "action_type": "email_send",
            "created_at": recent_time,
            "details": {
                "to": "customer@example.com",
                "subject": "Status",
                "body": "Ready",
            },
        }
        mock_table = Mock()
        mock_table.query.return_value = {"Items": [item]}

        with (
            patch.object(app, "approval_table", mock_table),
            patch.object(
                app,
                "decide_approval",
                return_value=(
                    {**item, "status": "APPROVED", "execution_status": "EXECUTED"},
                    None,
                ),
            ) as decide,
        ):
            result = app.chat("user-1", {"message": "Approve it"})

        decide.assert_called_once_with(
            "user-1", "00000000-0000-0000-0000-000000000001", "APPROVED"
        )
        self.assertEqual(result["statusCode"], 200)
        body = json.loads(result["body"])
        self.assertEqual(body.get("execution_status"), "EXECUTED")
        self.assertEqual(body.get("reply"), "Email sent.")

    def test_conversational_approval_rejects_stale_pending_draft(self):
        now = datetime.now(timezone.utc)
        stale_time = (now - timedelta(minutes=45)).isoformat()
        item = {
            "approval_id": "00000000-0000-0000-0000-000000000002",
            "user_id": "user-1",
            "status": "WAITING_APPROVAL",
            "action_type": "email_send",
            "created_at": stale_time,
            "details": {
                "to": "customer@example.com",
                "subject": "Status",
                "body": "Ready",
            },
        }
        mock_table = Mock()
        mock_table.query.return_value = {"Items": [item]}

        with (
            patch.object(app, "approval_table", mock_table),
            patch.object(app, "decide_approval") as decide,
        ):
            result = app.chat("user-1", {"message": "Approve it"})

        decide.assert_not_called()
        self.assertEqual(result["statusCode"], 200)
        body = json.loads(result["body"])
        self.assertEqual(body.get("reply"), "I have nothing to approve.")

    def test_conversational_reject_ignores_stale_pending_draft(self):
        now = datetime.now(timezone.utc)
        stale_time = (now - timedelta(minutes=45)).isoformat()
        item = {
            "approval_id": "00000000-0000-0000-0000-000000000002",
            "user_id": "user-1",
            "status": "WAITING_APPROVAL",
            "action_type": "email_send",
            "created_at": stale_time,
            "details": {
                "to": "customer@example.com",
                "subject": "Status",
                "body": "Ready",
            },
        }
        mock_table = Mock()
        mock_table.query.return_value = {"Items": [item]}

        with (
            patch.object(app, "approval_table", mock_table),
            patch.object(app, "decide_approval") as decide,
        ):
            result = app.chat("user-1", {"message": "Reject it"})

        decide.assert_not_called()
        self.assertEqual(result["statusCode"], 200)
        body = json.loads(result["body"])
        self.assertEqual(body.get("reply"), "I have nothing to reject.")

    def test_explicit_approval_by_id_remains_unaffected_for_stale_draft(self):
        now = datetime.now(timezone.utc)
        stale_time = (now - timedelta(hours=2)).isoformat()
        approval_id = "00000000-0000-0000-0000-000000000003"
        item = {
            "approval_id": approval_id,
            "user_id": "user-1",
            "status": "APPROVED",
            "action_type": "email_send",
            "execution_status": "EXECUTED",
            "created_at": stale_time,
            "summary": "Send update",
        }

        with patch.object(
            app, "decide_approval", return_value=(item, None)
        ) as decide:
            chat_result = app.chat(
                "user-1", {"message": f"Approve {approval_id}"}
            )

        decide.assert_called_once_with("user-1", approval_id, "APPROVED")
        self.assertEqual(chat_result["statusCode"], 200)
        body = json.loads(chat_result["body"])
        self.assertEqual(body.get("execution_status"), "EXECUTED")
        self.assertEqual(body.get("reply"), "Email sent.")

    def test_get_latest_pending_approval_freshness_window_behavior(self):
        now = datetime.now(timezone.utc)
        recent_item = {
            "approval_id": "recent-id",
            "user_id": "user-1",
            "status": "WAITING_APPROVAL",
            "created_at": (now - timedelta(minutes=10)).isoformat(),
        }
        stale_item = {
            "approval_id": "stale-id",
            "user_id": "user-1",
            "status": "WAITING_APPROVAL",
            "created_at": (now - timedelta(minutes=35)).isoformat(),
        }
        older_stale_item = {
            "approval_id": "older-stale-id",
            "user_id": "user-1",
            "status": "WAITING_APPROVAL",
            "created_at": (now - timedelta(hours=2)).isoformat(),
        }

        mock_table = Mock()
        with patch.object(app, "approval_table", mock_table):
            # 1. Only stale draft -> returns None
            mock_table.query.return_value = {"Items": [stale_item]}
            self.assertIsNone(app.get_latest_pending_approval("user-1"))

            # 2. Both stale and recent draft -> returns recent draft
            mock_table.query.return_value = {
                "Items": [stale_item, recent_item, older_stale_item]
            }
            self.assertEqual(
                app.get_latest_pending_approval("user-1"), recent_item
            )

            # 3. Only recent draft -> returns recent draft
            mock_table.query.return_value = {"Items": [recent_item]}
            self.assertEqual(
                app.get_latest_pending_approval("user-1"), recent_item
            )

            # 4. Multiple stale drafts -> returns None
            mock_table.query.return_value = {
                "Items": [stale_item, older_stale_item]
            }
            self.assertIsNone(app.get_latest_pending_approval("user-1"))

            # 5. Invalid created_at -> returns None
            invalid_item = {
                "approval_id": "bad-date-id",
                "user_id": "user-1",
                "status": "WAITING_APPROVAL",
                "created_at": "not-a-valid-date",
            }
            mock_table.query.return_value = {"Items": [invalid_item]}
            self.assertIsNone(app.get_latest_pending_approval("user-1"))


if __name__ == "__main__":
    unittest.main()
