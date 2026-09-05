import importlib
import json
import os
import shutil
import subprocess
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
voice = importlib.import_module("voice")


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

    def test_routing_phrase_3_draft_email_to_myself_and_approve_it_flow(self):
        """Regression test:
        1. draft email to myself ...
        2. verify WAITING_APPROVAL created
        3. approve it resolves that item
        4. no direct send before approval
        """
        saved_items = {}

        def fake_put_item(Item):
            saved_items[Item["approval_id"]] = dict(Item)

        def fake_query(**kwargs):
            user_id = kwargs.get("ExpressionAttributeValues", {}).get(":user_id")
            items = [dict(v) for v in saved_items.values() if v.get("user_id") == user_id]
            return {"Items": items}

        def fake_update_item(**kwargs):
            key = kwargs.get("Key", {})
            aid = key.get("approval_id")
            item = saved_items.get(aid, {})
            values = kwargs.get("ExpressionAttributeValues", {})
            if ":new_status" in values:
                item["status"] = values[":new_status"]
            if ":executing" in values:
                item["execution_status"] = values[":executing"]
            if ":execution_status" in values:
                item["execution_status"] = values[":execution_status"]
            saved_items[aid] = item
            return {"Attributes": dict(item)}

        def fake_get_item(**kwargs):
            key = kwargs.get("Key", {})
            aid = key.get("approval_id")
            return {"Item": dict(saved_items.get(aid, {}))}

        mock_approval_table = Mock()
        mock_approval_table.put_item.side_effect = fake_put_item
        mock_approval_table.query.side_effect = fake_query
        mock_approval_table.update_item.side_effect = fake_update_item
        mock_approval_table.get_item.side_effect = fake_get_item

        with patch.object(app, "approval_table", mock_approval_table), \
             patch.object(app, "table", self.mock_table), \
             patch.object(intent_mod, "table", self.mock_table), \
             patch.object(app, "load_google_connection", return_value={"gmail_email": "user@gmail.com"}), \
             patch.object(app, "call_openai") as mock_openai, \
             patch.object(app, "gmail_send_email") as mock_send:

            # 1. draft email to myself ...
            draft_result = app.chat(
                "user-1",
                {"message": "Draft an email to myself saying Hayder launch test successful"},
            )

            # 4. no direct send before approval
            mock_send.assert_not_called()
            mock_openai.assert_not_called()

            # 2. verify WAITING_APPROVAL created
            self.assertEqual(draft_result["statusCode"], 200)
            draft_body = json.loads(draft_result["body"])
            self.assertTrue(draft_body.get("approval_required"))
            self.assertEqual(draft_body.get("status"), "WAITING_APPROVAL")
            approval_id = draft_body.get("approval_id")
            self.assertIsNotNone(approval_id)
            self.assertIn(approval_id, saved_items)
            saved_item = saved_items[approval_id]
            self.assertEqual(saved_item["status"], "WAITING_APPROVAL")
            self.assertEqual(saved_item["action_type"], "email_send")
            self.assertEqual(saved_item["target"], "user@gmail.com")
            self.assertEqual(saved_item["details"]["to"], "user@gmail.com")
            self.assertIn("Hayder launch test successful", saved_item["details"]["subject"])
            self.assertIn("Hayder launch test successful", saved_item["details"]["body"])

            # 3. approve it resolves that item
            approve_result = app.chat(
                "user-1",
                {"message": "Approve it"},
            )

            self.assertEqual(approve_result["statusCode"], 200)
            approve_body = json.loads(approve_result["body"])
            self.assertEqual(approve_body.get("approval_id"), approval_id)
            self.assertEqual(approve_body.get("status"), "APPROVED")
            self.assertEqual(approve_body.get("execution_status"), "EXECUTED")
            self.assertEqual(approve_body.get("reply"), "Email sent.")
            mock_send.assert_called_once_with("user-1", saved_item["details"])
            self.assertEqual(saved_items[approval_id]["status"], "APPROVED")
            self.assertEqual(saved_items[approval_id]["execution_status"], "EXECUTED")

    def test_routing_phrase_3_draught_email_to_myself_and_approve_it_flow(self):
        """Voice STT regression: 'draught an email' creates WAITING_APPROVAL, no send before approval, and 'Approve it' sends."""
        saved_items = {}

        def fake_put_item(Item):
            saved_items[Item["approval_id"]] = dict(Item)

        def fake_query(**kwargs):
            user_id = kwargs.get("ExpressionAttributeValues", {}).get(":user_id")
            items = [dict(v) for v in saved_items.values() if v.get("user_id") == user_id]
            return {"Items": items}

        def fake_update_item(**kwargs):
            key = kwargs.get("Key", {})
            aid = key.get("approval_id")
            item = saved_items.get(aid, {})
            values = kwargs.get("ExpressionAttributeValues", {})
            if ":new_status" in values:
                item["status"] = values[":new_status"]
            if ":executing" in values:
                item["execution_status"] = values[":executing"]
            if ":execution_status" in values:
                item["execution_status"] = values[":execution_status"]
            saved_items[aid] = item
            return {"Attributes": dict(item)}

        def fake_get_item(**kwargs):
            key = kwargs.get("Key", {})
            aid = key.get("approval_id")
            return {"Item": dict(saved_items.get(aid, {}))}

        mock_approval_table = Mock()
        mock_approval_table.put_item.side_effect = fake_put_item
        mock_approval_table.query.side_effect = fake_query
        mock_approval_table.update_item.side_effect = fake_update_item
        mock_approval_table.get_item.side_effect = fake_get_item

        with patch.object(app, "approval_table", mock_approval_table), \
             patch.object(app, "table", self.mock_table), \
             patch.object(intent_mod, "table", self.mock_table), \
             patch.object(app, "load_google_connection", return_value={"gmail_email": "user@gmail.com"}), \
             patch.object(app, "call_openai") as mock_openai, \
             patch.object(app, "gmail_send_email") as mock_send:

            # 1. draught an email to myself ...
            draft_result = app.chat(
                "user-1",
                {"message": "draught an email to myself saying Hayder launch test successful"},
            )

            # 2. no direct send before approval
            mock_send.assert_not_called()
            mock_openai.assert_not_called()

            # 3. verify WAITING_APPROVAL created
            self.assertEqual(draft_result["statusCode"], 200)
            draft_body = json.loads(draft_result["body"])
            self.assertTrue(draft_body.get("approval_required"))
            self.assertEqual(draft_body.get("status"), "WAITING_APPROVAL")
            approval_id = draft_body.get("approval_id")
            self.assertIsNotNone(approval_id)
            self.assertIn(approval_id, saved_items)
            saved_item = saved_items[approval_id]
            self.assertEqual(saved_item["status"], "WAITING_APPROVAL")
            self.assertEqual(saved_item["action_type"], "email_send")
            self.assertEqual(saved_item["target"], "user@gmail.com")
            self.assertEqual(saved_item["details"]["to"], "user@gmail.com")
            self.assertIn("Hayder launch test successful", saved_item["details"]["subject"])
            self.assertIn("Hayder launch test successful", saved_item["details"]["body"])

            # 4. subsequent "Approve it" sends through existing approval flow
            approve_result = app.chat(
                "user-1",
                {"message": "Approve it"},
            )

            self.assertEqual(approve_result["statusCode"], 200)
            approve_body = json.loads(approve_result["body"])
            self.assertEqual(approve_body.get("approval_id"), approval_id)
            self.assertEqual(approve_body.get("status"), "APPROVED")
            self.assertEqual(approve_body.get("execution_status"), "EXECUTED")
            self.assertEqual(approve_body.get("reply"), "Email sent.")
            mock_send.assert_called_once_with("user-1", saved_item["details"])
            self.assertEqual(saved_items[approval_id]["status"], "APPROVED")
            self.assertEqual(saved_items[approval_id]["execution_status"], "EXECUTED")

    def test_approve_it_without_pending_approval_reports_nothing_to_approve(self):
        with patch.object(app, "approval_table", self.mock_approval_table), \
             patch.object(app, "table", self.mock_table), \
             patch.object(intent_mod, "table", self.mock_table), \
             patch.object(app, "call_openai") as mock_openai:

            result = app.chat(
                "user-1",
                {"message": "Approve it"},
            )

        mock_openai.assert_not_called()
        self.assertEqual(result["statusCode"], 200)
        body = json.loads(result["body"])
        self.assertEqual(body.get("reply"), "I have nothing to approve.")

    def test_voice_send_to_hayder_speaks_non_2xx_reply_and_ignores_raw_errors(self):
        """Voice UI regression: sendToHayder displays and speaks non-empty reply on non-2xx (e.g. 409), but does not speak raw internal errors."""
        res = voice.lambda_handler({}, {})
        self.assertEqual(res["statusCode"], 200)
        self.assertIn("text/html", res["headers"]["content-type"])
        html = res["body"]
        self.assertIn("async function sendToHayder(message)", html)

        start = html.find("async function sendToHayder(")
        end = html.find("loginButton.addEventListener", start)
        self.assertNotEqual(start, -1)
        self.assertNotEqual(end, -1)
        fn_code = html[start:end].strip()

        self.assertIn("!response.ok", fn_code)
        self.assertIn("data.reply", fn_code)

        node_path = shutil.which("node")
        if not node_path:
            return

        test_js = f"""
let core, statusBox, replyBox, spoken;
function reset() {{
    core = {{ className: "" }};
    statusBox = {{ textContent: "" }};
    replyBox = {{ textContent: "" }};
    spoken = [];
}}
function speak(text) {{ spoken.push(text); }}
async function getValidIdToken() {{ return "fake-token"; }}
async function refreshSession() {{ return false; }}
function clearSession() {{}}
function showLogin() {{}}

{fn_code}

async function run() {{
    // 1. 409 with non-empty user-facing reply must be displayed and spoken
    reset();
    global.fetch = async () => ({{
        status: 409,
        ok: false,
        json: async () => ({{
            reply: "Your Google account is not connected. Say Connect my Google account to get started.",
            error: "Google account not connected"
        }})
    }});
    await sendToHayder("read my latest emails");
    if (!replyBox.textContent.includes("Your Google account is not connected")) {{
        throw new Error("409 reply was not displayed in replyBox");
    }}
    if (spoken.length !== 1 || !spoken[0].includes("Your Google account is not connected")) {{
        throw new Error("409 reply was not spoken: " + JSON.stringify(spoken));
    }}
    if (statusBox.textContent !== "Hayder replied") {{
        throw new Error("unexpected statusBox: " + statusBox.textContent);
    }}

    // 2. 500 without user-facing reply must NOT be spoken
    reset();
    global.fetch = async () => ({{
        status: 500,
        ok: false,
        json: async () => ({{
            error: "Internal database timeout"
        }})
    }});
    await sendToHayder("read my latest emails");
    if (spoken.length !== 0) {{
        throw new Error("raw internal error was spoken: " + JSON.stringify(spoken));
    }}
    if (replyBox.textContent !== "") {{
        throw new Error("raw internal error was displayed in replyBox");
    }}
    if (statusBox.textContent !== "Internal database timeout") {{
        throw new Error("unexpected statusBox: " + statusBox.textContent);
    }}

    // 3. 200 OK standard reply preserved
    reset();
    global.fetch = async () => ({{
        status: 200,
        ok: true,
        json: async () => ({{
            reply: "Here are your emails.",
            tool: "gmail_readonly"
        }})
    }});
    await sendToHayder("read my latest emails");
    if (!replyBox.textContent.includes("Here are your emails.")) {{
        throw new Error("200 reply was not displayed");
    }}
    if (spoken.length !== 1 || spoken[0] !== "Here are your emails.") {{
        throw new Error("200 reply was not spoken");
    }}
    if (statusBox.textContent !== "Tool: gmail_readonly") {{
        throw new Error("unexpected statusBox for 200: " + statusBox.textContent);
    }}
}}
run().then(() => console.log("OK")).catch((err) => {{
    console.error(err);
    process.exit(1);
}});
"""
        proc = subprocess.run([node_path, "-e", test_js], capture_output=True, text=True)
        self.assertEqual(proc.returncode, 0, msg=f"JS test failed:\nstdout: {proc.stdout}\nstderr: {proc.stderr}")
        self.assertIn("OK", proc.stdout)


if __name__ == "__main__":
    unittest.main()
