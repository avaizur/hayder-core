import io
import json
import os
import sys
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock, Mock, patch
from urllib.error import HTTPError, URLError

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
        return SimpleNamespace(
            get_secret_value=Mock(return_value={"SecretString": "mock-secret"}),
            get_function_configuration=Mock(return_value={}),
        )


sys.modules.setdefault("boto3", FakeBoto3())
import app
import voice


class BillingEntitlementSliceTests(unittest.TestCase):
    def setUp(self):
        self.mock_table = Mock()
        self.mock_table.get_item.return_value = {}
        self.mock_table.put_item.return_value = {}
        self.mock_table.query.return_value = {"Items": []}
        self.mock_approval_table = Mock()
        self.mock_approval_table.get_item.return_value = {}
        self.mock_approval_table.put_item.return_value = {}
        self.mock_approval_table.query.return_value = {"Items": []}

    def _make_auth_event(
        self,
        method="POST",
        path="/chat",
        sub="sub-alice-123",
        email="alice@example.com",
        body=None,
        headers=None,
        query_params=None,
    ):
        event = {
            "rawPath": path,
            "requestContext": {
                "http": {"method": method},
                "authorizer": {
                    "jwt": {
                        "claims": {
                            "sub": sub,
                            "email": email,
                        }
                    }
                },
            },
        }
        if body is not None:
            event["body"] = json.dumps(body) if isinstance(body, (dict, list)) else str(body)
        if headers is not None:
            event["headers"] = headers
        if query_params is not None:
            event["queryStringParameters"] = query_params
        return event

    def test_entitled_user_can_use_chat(self):
        """Entitled user with active HAYDER_PRO can use /chat."""
        event = self._make_auth_event(
            method="POST",
            path="/chat",
            sub="user-sub-001",
            email="entitled@example.com",
            body={"message": "Draft an email to myself saying test billing"},
        )

        with patch.object(app, "check_hayder_pro", return_value=True) as mock_check, \
             patch.object(app, "chat", return_value=app.response(200, {"assistant": "Hayder", "reply": "Done"})) as mock_chat:

            result = app.lambda_handler(event, None)

        mock_check.assert_called_once_with("hayder:user-sub-001")
        mock_chat.assert_called_once_with(
            "entitled@example.com",
            {"message": "Draft an email to myself saying test billing"},
            event=event,
        )
        self.assertEqual(result["statusCode"], 200)
        body = json.loads(result["body"])
        self.assertEqual(body["reply"], "Done")

    def test_unpaid_user_receives_403_subscription_required(self):
        """Unpaid user receives structured HTTP 403 SUBSCRIPTION_REQUIRED."""
        event = self._make_auth_event(
            method="POST",
            path="/chat",
            sub="user-sub-unpaid",
            email="unpaid@example.com",
            body={"message": "What needs my attention?"},
        )

        with patch.object(app, "check_hayder_pro", return_value=False) as mock_check, \
             patch.object(app, "chat") as mock_chat:

            result = app.lambda_handler(event, None)

        mock_check.assert_called_once_with("hayder:user-sub-unpaid")
        mock_chat.assert_not_called()

        self.assertEqual(result["statusCode"], 403)
        self.assertEqual(result["headers"]["content-type"], "application/json")
        body = json.loads(result["body"])
        self.assertEqual(
            body,
            {
                "error": "SUBSCRIPTION_REQUIRED",
                "entitlement": "HAYDER_PRO",
            },
        )

    def test_unauthenticated_behaviour_remains_unchanged(self):
        """Unauthenticated requests to /chat return 401 without checking entitlement."""
        event = {
            "rawPath": "/chat",
            "requestContext": {
                "http": {"method": "POST"},
            },
            "body": json.dumps({"message": "Hello without auth"}),
        }

        with patch.object(app, "check_hayder_pro") as mock_check, \
             patch.object(app, "chat") as mock_chat:

            result = app.lambda_handler(event, None)

        mock_check.assert_not_called()
        mock_chat.assert_not_called()
        self.assertEqual(result["statusCode"], 401)
        body = json.loads(result["body"])
        self.assertEqual(body.get("error"), "Authenticated user not found")

    def test_public_health_route_unaffected(self):
        """Public /health route returns 200 and is not gated."""
        event = {
            "rawPath": "/health",
            "requestContext": {
                "http": {"method": "GET"},
            },
        }

        with patch.object(app, "check_hayder_pro") as mock_check:
            result = app.lambda_handler(event, None)

        mock_check.assert_not_called()
        self.assertEqual(result["statusCode"], 200)
        body = json.loads(result["body"])
        self.assertEqual(body, {"status": "ok", "service": "hayder-core"})

    def test_google_connect_onboarding_route_unaffected_for_unpaid_user(self):
        """Google OAuth /oauth/google/connect onboarding must NOT be gated by HAYDER_PRO."""
        event = self._make_auth_event(
            method="GET",
            path="/oauth/google/connect",
            sub="unpaid-onboarding-sub",
            email="onboarding@example.com",
            headers={"host": "api.hayder.test"},
        )

        with patch.object(app, "check_hayder_pro", return_value=False) as mock_billing, \
             patch.object(app, "get_google_credentials", return_value=("fake-client-id", "fake-secret")):

            result = app.lambda_handler(event, None)

        # check_hayder_pro must NOT be called for Google OAuth connect onboarding
        mock_billing.assert_not_called()
        self.assertEqual(result["statusCode"], 200)
        body = json.loads(result["body"])
        self.assertEqual(body.get("tool"), "google_connect")
        self.assertIn("authorization_url", body)
        self.assertTrue(body["authorization_url"].startswith("https://accounts.google.com/o/oauth2/v2/auth"))
        self.assertIn("client_id=fake-client-id", body["authorization_url"])

    def test_public_pages_and_voice_unaffected(self):
        """Public pages (/hayder, /hayder/pricing, /privacy, /terms) and /voice remain unaffected."""
        for route in ("/voice", "/hayder", "/hayder/pricing", "/privacy", "/terms"):
            res = voice.lambda_handler({"rawPath": route}, {})
            self.assertEqual(res["statusCode"], 200)
            self.assertIn("text/html", res["headers"]["content-type"])

    def test_external_user_id_derived_from_cognito_sub_not_browser(self):
        """
        Stable external user ID is derived strictly server-side from Cognito claims (sub),
        and cannot be spoofed or overridden by browser headers, query parameters, or body.
        """
        # 1. Normal derivation
        event = self._make_auth_event(sub="sub-verified-42", email="verified@example.com")
        self.assertEqual(app.get_external_user_id(event), "hayder:sub-verified-42")

        # 2. Browser attempts to spoof via queryStringParameters, headers, and body
        attacker_event = {
            "rawPath": "/chat",
            "requestContext": {
                "http": {"method": "POST"},
                "authorizer": {
                    "jwt": {
                        "claims": {
                            "sub": "real-verified-sub",
                            "email": "real@example.com",
                        }
                    }
                },
            },
            "headers": {
                "x-external-user-id": "hayder:attacker-paid-sub",
                "x-sub": "attacker-paid-sub",
            },
            "queryStringParameters": {
                "external_user_id": "hayder:attacker-paid-sub",
                "sub": "attacker-paid-sub",
                "user_id": "attacker-paid-sub",
            },
            "body": json.dumps({
                "message": "Hi",
                "external_user_id": "hayder:attacker-paid-sub",
                "sub": "attacker-paid-sub",
            }),
        }

        # get_external_user_id ignores all attacker parameters
        derived_id = app.get_external_user_id(attacker_event)
        self.assertEqual(derived_id, "hayder:real-verified-sub")

        # In lambda_handler, check_hayder_pro receives only the authentic derived external user ID
        with patch.object(app, "check_hayder_pro", return_value=True) as mock_check, \
             patch.object(app, "chat", return_value=app.response(200, {"ok": True})):
            app.lambda_handler(attacker_event, None)

        mock_check.assert_called_once_with("hayder:real-verified-sub")

    def test_email_is_metadata_not_immutable_identity(self):
        """Verify email in Cognito claims is not used to construct external_user_id."""
        claims = {
            "email": "user@example.com",
            "sub": "uuid-9999-8888",
        }
        event = {
            "requestContext": {
                "authorizer": {
                    "jwt": {
                        "claims": claims,
                    }
                }
            }
        }
        self.assertEqual(app.get_external_user_id(event), "hayder:uuid-9999-8888")
        self.assertNotIn("user@example.com", app.get_external_user_id(event))

    def test_missing_sub_returns_none_for_external_user_id(self):
        """When Cognito sub is absent, get_external_user_id returns None."""
        event = {
            "requestContext": {
                "authorizer": {
                    "jwt": {
                        "claims": {
                            "email": "no-sub@example.com",
                        }
                    }
                }
            }
        }
        self.assertIsNone(app.get_external_user_id(event))

    def test_xorwia_billing_client_url_construction_and_headers(self):
        """XorwiaBillingClient builds correct URL and headers for entitlement check."""
        client = app.XorwiaBillingClient(
            base_url="https://billing.xorwia.test",
            service_secret="service-secret-token",
        )

        fake_resp = io.BytesIO(b'{"entitled": true, "status": "active", "product": "HAYDER_PRO"}')
        fake_resp.getcode = lambda: 200

        with patch("urllib.request.urlopen", return_value=fake_resp) as mock_urlopen:
            result = client.check_entitlement(
                external_user_id="hayder:sub-123",
                product="HAYDER_PRO",
            )

        self.assertTrue(result)
        mock_urlopen.assert_called_once()
        req = mock_urlopen.call_args[0][0]
        self.assertEqual(
            req.full_url,
            "https://billing.xorwia.test/api/billing/entitlement",
        )
        self.assertEqual(req.get_method(), "POST")
        self.assertEqual(req.get_header("Authorization"), "Bearer service-secret-token")
        self.assertEqual(req.get_header("Content-type"), "application/json")
        self.assertEqual(req.get_header("Accept"), "application/json")
        self.assertFalse(req.has_header("X-api-key"))
        self.assertNotIn("x-api-key", [k.lower() for k in req.headers])
        self.assertEqual(
            json.loads(req.data.decode("utf-8")),
            {
                "external_user_id": "hayder:sub-123",
                "product": "HAYDER_PRO",
            },
        )

    def test_xorwia_billing_client_response_variations(self):
        """XorwiaBillingClient only allows literal boolean entitled=true to grant access."""
        client = app.XorwiaBillingClient(
            base_url="https://billing.xorwia.test",
            service_secret="service-secret-token",
        )

        test_cases = [
            (b'{"entitled": true, "status": "active", "product": "HAYDER_PRO"}', 200, True),
            (b'{"entitled": true}', 200, True),
            (b'{"entitled": false, "status": "none", "product": "HAYDER_PRO"}', 200, False),
            (b'{"entitled": false}', 200, False),
            (b'{"entitled": "true"}', 200, False),
            (b'{"entitled": 1}', 200, False),
            (b'{"entitled": 0}', 200, False),
            (b'{"status": "active"}', 200, False),
            (b'{"active": true}', 200, False),
            (b'{"status": "trialing"}', 200, False),
            (b'{"entitlements": ["HAYDER_PRO"]}', 200, False),
            (b'{}', 200, False),
            (b'invalid json', 200, False),
        ]

        for payload, status, expected in test_cases:
            with self.subTest(payload=payload, expected=expected):
                fake_resp = io.BytesIO(payload)
                fake_resp.getcode = lambda s=status: s
                with patch("urllib.request.urlopen", return_value=fake_resp):
                    res = client.check_entitlement("hayder:user-test", "HAYDER_PRO")
                    self.assertEqual(res, expected)

    def test_xorwia_billing_client_http_errors_fail_closed(self):
        """HTTP errors (401, 402, 403, 404, 500, network error) fail closed to False."""
        client = app.XorwiaBillingClient(
            base_url="https://billing.xorwia.test",
            service_secret="service-secret-token",
        )

        for error_code in (401, 402, 403, 404, 500):
            with self.subTest(error_code=error_code):
                err = HTTPError(
                    url="https://billing.xorwia.test/api/billing/entitlement",
                    code=error_code,
                    msg="Error",
                    hdrs={},
                    fp=io.BytesIO(b'{"error": "not entitled"}'),
                )
                with patch("urllib.request.urlopen", side_effect=err):
                    res = client.check_entitlement("hayder:user-1", "HAYDER_PRO")
                    self.assertFalse(res)

        with patch("urllib.request.urlopen", side_effect=URLError("Connection refused")):
            res = client.check_entitlement("hayder:user-1", "HAYDER_PRO")
            self.assertFalse(res)

    def test_xorwia_billing_client_unconfigured_url_fails_closed(self):
        """When billing API URL is not configured, entitlement check returns False without HTTP call."""
        with patch.dict(os.environ, {"XORWIA_BILLING_BASE_URL": ""}):
            client = app.XorwiaBillingClient(base_url="", service_secret="service-secret-token")
            with patch("urllib.request.urlopen") as mock_urlopen:
                res = client.check_entitlement("hayder:user-1", "HAYDER_PRO")
            self.assertFalse(res)
            mock_urlopen.assert_not_called()

    def test_xorwia_billing_client_missing_service_secret_fails_without_http(self):
        """When service secret cannot be resolved, return False before making HTTP request."""
        client = app.XorwiaBillingClient(
            base_url="https://billing.xorwia.test",
            service_secret=None,
        )

        with patch.object(app, "get_xorwia_billing_service_secret", return_value=None), \
             patch("urllib.request.urlopen") as mock_urlopen:
            result = client.check_entitlement("hayder:user-1", "HAYDER_PRO")

        self.assertFalse(result)
        mock_urlopen.assert_not_called()

    def test_xorwia_billing_service_secret_resolution(self):
        """Service secret is resolved from XORWIA_BILLING_SERVICE_SECRET or Secrets Manager."""
        with patch.dict(os.environ, {"XORWIA_BILLING_SERVICE_SECRET": "test-env-secret"}):
            self.assertEqual(app.get_xorwia_billing_service_secret(), "test-env-secret")

        with patch.dict(os.environ, {"XORWIA_BILLING_SERVICE_SECRET": ""}, clear=True), \
             patch.object(app, "get_secret", return_value="sm-secret") as mock_get_secret:
            self.assertEqual(app.get_xorwia_billing_service_secret(), "sm-secret")
            mock_get_secret.assert_called_with(app.XORWIA_BILLING_SECRET_NAME)

        with patch.dict(os.environ, {"XORWIA_BILLING_SERVICE_SECRET": ""}, clear=True), \
             patch.object(app, "get_secret", side_effect=Exception("not found")):
            self.assertIsNone(app.get_xorwia_billing_service_secret())

    def test_legacy_billing_fallbacks_removed(self):
        """Legacy billing aliases and environment fallbacks are removed."""
        self.assertFalse(hasattr(app, "get_xorwia_billing_api_key"))
        client = app.XorwiaBillingClient(base_url="https://billing.xorwia.test")
        self.assertFalse(hasattr(client, "_resolve_api_key"))
        self.assertFalse(hasattr(client, "api_key"))

        with patch.dict(os.environ, {"XORWIA_BILLING_API_KEY": "legacy-key", "XORWIA_BILLING_SERVICE_SECRET": ""}, clear=True), \
             patch.object(app, "get_secret", side_effect=Exception("not found")):
            self.assertIsNone(app.get_xorwia_billing_service_secret())

    def test_check_hayder_pro_helper_formats_external_user_id(self):
        """check_hayder_pro prepends hayder: prefix if not already present."""
        mock_client = Mock()
        mock_client.check_entitlement.return_value = True

        app.check_hayder_pro("sub-without-prefix", client=mock_client)
        mock_client.check_entitlement.assert_called_with(
            external_user_id="hayder:sub-without-prefix",
            product="HAYDER_PRO",
        )

        app.check_hayder_pro("hayder:already-prefixed", client=mock_client)
        mock_client.check_entitlement.assert_called_with(
            external_user_id="hayder:already-prefixed",
            product="HAYDER_PRO",
        )


if __name__ == "__main__":
    unittest.main()
