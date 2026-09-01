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
            Table=lambda name: SimpleNamespace(name=name),
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


if __name__ == "__main__":
    unittest.main()
