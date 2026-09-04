import importlib
import json
import os
import sys
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch
from urllib.parse import parse_qs, urlparse


ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
sys.path.insert(0, str(SRC))

os.environ.setdefault("HAYDER_TABLE", "test-memory")
os.environ.setdefault("HAYDER_APPROVAL_TABLE", "test-approvals")
os.environ.setdefault("AWS_LAMBDA_FUNCTION_NAME", "test-function")


class FakeResourceNotFoundException(Exception):
    pass


class FakeResourceExistsException(Exception):
    pass


class FakeSecretsClient:
    exceptions = SimpleNamespace(
        ResourceExistsException=FakeResourceExistsException,
        ResourceNotFoundException=FakeResourceNotFoundException,
    )

    def __init__(self):
        self.values = {}
        self.put_calls = []

    def create_secret(self, Name, SecretString, Description):
        if Name in self.values:
            raise FakeResourceExistsException()
        self.values[Name] = SecretString

    def put_secret_value(self, SecretId, SecretString):
        self.put_calls.append(SecretId)
        self.values[SecretId] = SecretString

    def get_secret_value(self, SecretId):
        if SecretId not in self.values:
            raise FakeResourceNotFoundException()
        return {"SecretString": self.values[SecretId]}


class FakeBoto3:
    def resource(self, service):
        return SimpleNamespace(
            Table=lambda name: SimpleNamespace(
                name=name,
                get_item=lambda **kwargs: {},
                put_item=lambda **kwargs: None,
            ),
        )

    def client(self, service):
        return SimpleNamespace()


sys.modules.setdefault("boto3", FakeBoto3())
app = importlib.import_module("app")


class GoogleSingleAccountTests(unittest.TestCase):
    def test_oauth_explicitly_prompts_for_google_account_choice(self):
        event = {
            "headers": {"host": "api.example.com"},
            "requestContext": {"http": {"protocol": "HTTP/1.1"}},
        }

        with (
            patch.object(app, "get_google_credentials", return_value=("client", "secret")),
            patch.object(app, "google_redirect_uri", return_value="https://api.example.com/oauth/google/callback"),
            patch.object(app, "create_google_state", return_value="signed-state"),
        ):
            result = app.google_connect(event, "hayder-user")

        body = json.loads(result["body"])
        query = parse_qs(urlparse(body["authorization_url"]).query)

        self.assertEqual(result["statusCode"], 200)
        self.assertEqual(query["prompt"], ["select_account consent"])
        self.assertEqual(query["access_type"], ["offline"])
        self.assertEqual(
            body["scope"],
            "gmail.readonly gmail.send calendar.events.readonly",
        )
        self.assertIn("Gmail read/send", body["message"])
        self.assertIn("read-only Calendar", body["message"])

    def test_reconnecting_replaces_the_users_single_secret(self):
        secrets = FakeSecretsClient()

        with patch.object(app, "secrets_client", secrets):
            app.store_google_refresh_token(
                "hayder-user", "first-token", "first@gmail.com"
            )
            app.store_google_refresh_token(
                "hayder-user", "second-token", "second@gmail.com"
            )

        secret_name = app.google_user_secret_name("hayder-user")
        saved = json.loads(secrets.values[secret_name])

        self.assertEqual(secrets.put_calls, [secret_name])
        self.assertEqual(saved["refresh_token"], "second-token")
        self.assertEqual(saved["gmail_email"], "second@gmail.com")

    def test_existing_google_default_connection_can_still_load(self):
        secrets = FakeSecretsClient()
        existing_secret = "hayder/google/users/hash/accounts/account-hash"
        secrets.values[existing_secret] = json.dumps(
            {
                "refresh_token": "existing-token",
                "gmail_email": "existing@gmail.com",
            }
        )
        fake_table = SimpleNamespace(
            get_item=lambda Key: {
                "Item": {
                    "secret_name": existing_secret,
                }
            }
        )

        with (
            patch.object(app, "secrets_client", secrets),
            patch.object(app, "table", fake_table),
        ):
            connection = app.load_google_connection(
                "hayder-user"
            )

        self.assertEqual(
            connection["refresh_token"],
            "existing-token",
        )

    def test_phase_one_template_has_no_multi_account_surface(self):
        template = (ROOT / "template.yaml").read_text()

        self.assertNotIn("HAYDER_GOOGLE_LIMIT_", template)
        self.assertNotIn("/google/accounts", template)
        self.assertNotIn("/account/plan", template)

    def test_disconnected_google_user_facing_messages(self):
        with patch.object(app, "load_google_connection", return_value=None):
            # 1. Gmail read-only
            gmail_res = app.chat("user-1", {"message": "read my latest emails"})
            self.assertEqual(gmail_res["statusCode"], 409)
            gmail_body = json.loads(gmail_res["body"])
            self.assertEqual(gmail_body["reply"], app.GOOGLE_DISCONNECTED_MESSAGE)
            self.assertNotIn("to this Hayder account", gmail_body["reply"])

            # 2. Calendar read-only
            cal_res = app.chat("user-1", {"message": "what is on my calendar today"})
            self.assertEqual(cal_res["statusCode"], 409)
            cal_body = json.loads(cal_res["body"])
            self.assertEqual(cal_body["reply"], app.GOOGLE_DISCONNECTED_MESSAGE)

            # 3. Attention inbox
            att_res = app.chat("user-1", {"message": "what is important in my inbox"})
            self.assertEqual(att_res["statusCode"], 409)
            att_body = json.loads(att_res["body"])
            self.assertEqual(att_body["reply"], app.GOOGLE_DISCONNECTED_MESSAGE)
            self.assertNotIn("to this Hayder account", att_body["reply"])

    def test_expired_or_revoked_google_auth_gives_single_reconnect_instruction(self):
        auth_error = RuntimeError("Google returned HTTP 400")

        with patch.object(app, "refresh_google_access_token", side_effect=auth_error):
            # 1. Gmail read-only
            gmail_res = app.chat("user-1", {"message": "read my latest emails"})
            self.assertEqual(gmail_res["statusCode"], 409)
            gmail_body = json.loads(gmail_res["body"])
            self.assertEqual(gmail_body["reply"], app.GOOGLE_RECONNECT_MESSAGE)

            # 2. Calendar read-only
            cal_res = app.chat("user-1", {"message": "what is on my calendar today"})
            self.assertEqual(cal_res["statusCode"], 409)
            cal_body = json.loads(cal_res["body"])
            self.assertEqual(cal_body["reply"], app.GOOGLE_RECONNECT_MESSAGE)

            # 3. Attention inbox
            att_res = app.chat("user-1", {"message": "what is important in my inbox"})
            self.assertEqual(att_res["statusCode"], 409)
            att_body = json.loads(att_res["body"])
            self.assertEqual(att_body["reply"], app.GOOGLE_RECONNECT_MESSAGE)

    def test_failed_oauth_callback_safe_responses(self):
        # 1. User denied/cancelled in browser
        browser_event = {
            "queryStringParameters": {"error": "access_denied"},
            "headers": {"accept": "text/html,application/xhtml+xml"},
        }
        res = app.google_callback(browser_event)
        self.assertEqual(res["statusCode"], 400)
        self.assertIn("text/html", res["headers"]["content-type"])
        self.assertIn("Google connection was cancelled or denied", res["body"])
        self.assertIn("/voice", res["body"])
        self.assertNotIn("access_denied", res["body"])

        # 2. User denied/cancelled via JSON client
        json_event = {
            "queryStringParameters": {"error": "access_denied"},
            "headers": {"accept": "application/json"},
        }
        res_json = app.google_callback(json_event)
        self.assertEqual(res_json["statusCode"], 400)
        body = json.loads(res_json["body"])
        self.assertIn("Google connection was cancelled or denied", body["error"])

        # 3. Missing code or state
        res_missing = app.google_callback({"queryStringParameters": {}})
        self.assertEqual(res_missing["statusCode"], 400)
        self.assertIn("Missing OAuth code or state", json.loads(res_missing["body"])["error"])

        # 4. Invalid or expired state
        with patch.object(app, "verify_google_state", return_value=None):
            res_invalid_state = app.google_callback(
                {"queryStringParameters": {"code": "dummy-code", "state": "expired-state"}}
            )
            self.assertEqual(res_invalid_state["statusCode"], 400)
            self.assertIn("expired or is invalid", json.loads(res_invalid_state["body"])["error"])

        # 5. Missing refresh token from Google
        with (
            patch.object(app, "verify_google_state", return_value="user-1"),
            patch.object(app, "get_google_credentials", return_value=("id", "secret")),
            patch.object(app, "post_form", return_value={"access_token": "acc"}),
            patch.object(app, "google_redirect_uri", return_value="https://example.com/oauth/google/callback"),
        ):
            res_no_refresh = app.google_callback(
                {"queryStringParameters": {"code": "dummy-code", "state": "valid-state"}}
            )
            self.assertEqual(res_no_refresh["statusCode"], 400)
            self.assertIn("did not return a refresh token", json.loads(res_no_refresh["body"])["error"])

        # 6. Upstream network/HTTP error during token exchange
        with (
            patch.object(app, "verify_google_state", return_value="user-1"),
            patch.object(app, "get_google_credentials", return_value=("id", "secret")),
            patch.object(app, "post_form", side_effect=RuntimeError("Connection reset")),
            patch.object(app, "google_redirect_uri", return_value="https://example.com/oauth/google/callback"),
        ):
            res_upstream_err = app.google_callback(
                {"queryStringParameters": {"code": "dummy-code", "state": "valid-state"}}
            )
            self.assertEqual(res_upstream_err["statusCode"], 502)
            self.assertEqual(
                json.loads(res_upstream_err["body"])["error"],
                "Google connection failed. Please return to Hayder and try connecting again.",
            )
            self.assertNotIn("Connection reset", res_upstream_err["body"])

    def test_successful_oauth_callback_response(self):
        secrets = FakeSecretsClient()
        with (
            patch.object(app, "verify_google_state", return_value="user-1"),
            patch.object(app, "get_google_credentials", return_value=("id", "secret")),
            patch.object(
                app,
                "post_form",
                return_value={"access_token": "acc", "refresh_token": "ref"},
            ),
            patch.object(
                app,
                "google_api_get",
                return_value={"emailAddress": "founder@example.com"},
            ),
            patch.object(app, "google_redirect_uri", return_value="https://example.com/oauth/google/callback"),
            patch.object(app, "secrets_client", secrets),
        ):
            event = {
                "queryStringParameters": {"code": "auth-code", "state": "valid-state"},
                "headers": {"accept": "text/html"},
            }
            res = app.google_callback(event)

        self.assertEqual(res["statusCode"], 200)
        self.assertIn("text/html", res["headers"]["content-type"])
        self.assertIn("Google account connected to Hayder", res["body"])
        self.assertIn("founder@example.com", res["body"])
        self.assertIn("Read email, send approved email, and read Calendar events", res["body"])
        self.assertIn("what's on my calendar today", res["body"])
        self.assertIn("/voice", res["body"])

    def test_google_connect_origin_from_headers(self):
        event = {
            "headers": {"host": "voice.hayder.ai"},
        }
        with (
            patch.object(app, "get_google_credentials", return_value=("client", "secret")),
            patch.object(app, "create_google_state", return_value="signed-state"),
        ):
            result = app.google_connect(event, "hayder-user")

        self.assertEqual(result["statusCode"], 200)
        body = json.loads(result["body"])
        query = parse_qs(urlparse(body["authorization_url"]).query)
        self.assertEqual(
            query["redirect_uri"],
            ["https://voice.hayder.ai/oauth/google/callback"],
        )


if __name__ == "__main__":
    unittest.main()
