"""
Focused unit tests for Hayder -> Xorwia Stripe Checkout integration (HAYDER_PRO).

Validates:
1. Verified Cognito login required for POST /billing/checkout and GET /billing/status
2. Server-to-server delegation to Xorwia POST /api/create-checkout-session for HAYDER_PRO
3. Browser-supplied user IDs, prices, product names, return URLs, and Stripe URLs are never trusted
4. Strict validation of upstream Stripe Checkout redirect URLs (https://checkout.stripe.com only)
5. Safe error handling without leaking upstream secrets or raw errors
6. Pricing page (£9.99 monthly / £99 annual, proposed) and return pages (/billing/success, /billing/cancel)
7. Plan selection preserved across email/password and Cognito Google PKCE sign-in
8. Preservation of existing Google sign-in, Gmail/Calendar OAuth, and zero duplicate Stripe integration
"""

import base64
import io
import json
import os
import shutil
import subprocess
import sys
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch
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


def _make_fake_jwt(sub="sub-user-123", email="user@example.com"):
    header = base64.urlsafe_b64encode(
        json.dumps({"alg": "RS256", "kid": "test-kid", "typ": "JWT"}).encode("utf-8")
    ).decode("utf-8").rstrip("=")
    payload = base64.urlsafe_b64encode(
        json.dumps({"sub": sub, "email": email, "token_use": "id"}).encode("utf-8")
    ).decode("utf-8").rstrip("=")
    sig = base64.urlsafe_b64encode(b"fake-signature-bytes").decode("utf-8").rstrip("=")
    return f"{header}.{payload}.{sig}"


def _make_checkout_event(
    *,
    method="POST",
    path="/billing/checkout",
    sub="sub-user-123",
    email="user@example.com",
    body=None,
    token=None,
    include_auth_claims=True,
    domain_name="hayder.xorwia.com",
    headers=None,
):
    event_headers = dict(headers or {})
    if token is not None:
        event_headers["authorization"] = f"Bearer {token}"

    request_context = {"http": {"method": method}}
    if domain_name is not None:
        request_context["domainName"] = domain_name
    if include_auth_claims:
        request_context["authorizer"] = {
            "jwt": {
                "claims": {
                    "sub": sub,
                    "email": email,
                }
            }
        }

    event = {
        "rawPath": path,
        "requestContext": request_context,
        "headers": event_headers,
    }
    if body is not None:
        event["body"] = json.dumps(body) if isinstance(body, (dict, list)) else str(body)
    return event


class CheckoutBackendTests(unittest.TestCase):

    def test_unauthenticated_checkout_rejected_with_401(self):
        event = _make_checkout_event(
            include_auth_claims=False,
            body={"billingInterval": "monthly", "external_user_id": "hayder:spoofed"},
        )
        with patch("urllib.request.urlopen") as mock_urlopen:
            res = app.lambda_handler(event, None)

        self.assertEqual(res["statusCode"], 401)
        mock_urlopen.assert_not_called()

    def test_missing_or_mismatched_bearer_token_rejected_with_401(self):
        # Missing Authorization header
        event_no_header = _make_checkout_event(
            sub="sub-real-1",
            token=None,
            body={"billingInterval": "monthly"},
        )
        with patch("urllib.request.urlopen") as mock_urlopen:
            res = app.lambda_handler(event_no_header, None)
        self.assertEqual(res["statusCode"], 401)
        mock_urlopen.assert_not_called()

        # Bearer token belonging to a different Cognito sub than authorizer claims
        wrong_sub_token = _make_fake_jwt(sub="sub-attacker-999")
        event_mismatch = _make_checkout_event(
            sub="sub-real-1",
            token=wrong_sub_token,
            body={"billingInterval": "monthly"},
        )
        with patch("urllib.request.urlopen") as mock_urlopen:
            res = app.lambda_handler(event_mismatch, None)
        self.assertEqual(res["statusCode"], 401)
        mock_urlopen.assert_not_called()

    def test_invalid_or_missing_billing_interval_rejected_with_400(self):
        token = _make_fake_jwt(sub="sub-valid-1")
        for bad_body in (
            {},
            {"billingInterval": "weekly"},
            {"billingInterval": "free"},
            {"plan": "lifetime"},
            {"billingInterval": 999},
        ):
            with self.subTest(body=bad_body):
                event = _make_checkout_event(sub="sub-valid-1", token=token, body=bad_body)
                with patch("urllib.request.urlopen") as mock_urlopen:
                    res = app.lambda_handler(event, None)
                self.assertEqual(res["statusCode"], 400)
                mock_urlopen.assert_not_called()

    def test_checkout_delegates_to_xorwia_and_ignores_browser_spoofing(self):
        token = _make_fake_jwt(sub="sub-verified-77", email="alice@example.com")
        event = _make_checkout_event(
            sub="sub-verified-77",
            email="alice@example.com",
            token=token,
            domain_name="hayder.xorwia.com",
            headers={
                "x-forwarded-host": "evil.attacker.com",
                "x-external-user-id": "hayder:spoofed",
            },
            body={
                "billingInterval": "annual",
                "product": "FREE_FOREVER",
                "external_user_id": "hayder:spoofed",
                "user_id": "spoofed",
                "sub": "spoofed",
                "priceId": "price_attacker_1p",
                "amount": 1,
                "url": "https://evil.attacker.com/fake-stripe",
                "stripe_url": "https://evil.attacker.com/fake-stripe",
                "successUrl": "https://evil.attacker.com/steal",
                "cancelUrl": "https://evil.attacker.com/cancel",
            },
        )

        fake_resp = io.BytesIO(
            json.dumps({
                "id": "cs_test_annual_123",
                "url": "https://checkout.stripe.com/c/pay/cs_test_annual_123",
            }).encode("utf-8")
        )
        fake_resp.getcode = lambda: 200

        with patch.dict(
            os.environ,
            {
                "XORWIA_BILLING_BASE_URL": "https://billing.xorwia.test",
                "HAYDER_PUBLIC_BASE_URL": "",
            },
        ), patch("urllib.request.urlopen", return_value=fake_resp) as mock_urlopen:
            res = app.lambda_handler(event, None)

        self.assertEqual(res["statusCode"], 200)
        self.assertEqual(res["headers"].get("cache-control"), "no-store")
        body = json.loads(res["body"])
        self.assertEqual(
            body,
            {
                "id": "cs_test_annual_123",
                "url": "https://checkout.stripe.com/c/pay/cs_test_annual_123",
                "product": "HAYDER_PRO",
                "billing_interval": "annual",
            },
        )

        mock_urlopen.assert_called_once()
        req = mock_urlopen.call_args[0][0]
        self.assertEqual(req.full_url, "https://billing.xorwia.test/api/create-checkout-session")
        self.assertEqual(req.get_method(), "POST")
        self.assertEqual(req.get_header("Authorization"), f"Bearer {token}")

        sent_payload = json.loads(req.data.decode("utf-8"))
        self.assertEqual(
            sent_payload,
            {
                "product": "HAYDER_PRO",
                "billingInterval": "annual",
                "successUrl": "https://hayder.xorwia.com/billing/success",
                "cancelUrl": "https://hayder.xorwia.com/billing/cancel",
            },
        )
        for forbidden_key in ("external_user_id", "user_id", "sub", "priceId", "amount", "url", "stripe_url"):
            self.assertNotIn(forbidden_key, sent_payload)

    def test_checkout_monthly_uses_configured_public_base_url(self):
        token = _make_fake_jwt(sub="sub-monthly-1")
        event = _make_checkout_event(
            sub="sub-monthly-1",
            token=token,
            domain_name="abc123.execute-api.eu-west-2.amazonaws.com",
            body={"billingInterval": "monthly"},
        )

        fake_resp = io.BytesIO(
            json.dumps({
                "id": "cs_test_monthly_456",
                "url": "https://checkout.stripe.com/c/pay/cs_test_monthly_456",
            }).encode("utf-8")
        )
        fake_resp.getcode = lambda: 200

        with patch.dict(
            os.environ,
            {
                "XORWIA_BILLING_BASE_URL": "https://billing.xorwia.test/api/billing/entitlement",
                "HAYDER_PUBLIC_BASE_URL": "https://hayder.xorwia.com",
            },
        ), patch("urllib.request.urlopen", return_value=fake_resp) as mock_urlopen:
            res = app.lambda_handler(event, None)

        self.assertEqual(res["statusCode"], 200)
        req = mock_urlopen.call_args[0][0]
        self.assertEqual(req.full_url, "https://billing.xorwia.test/api/create-checkout-session")
        sent_payload = json.loads(req.data.decode("utf-8"))
        self.assertEqual(sent_payload["billingInterval"], "monthly")
        self.assertEqual(sent_payload["successUrl"], "https://hayder.xorwia.com/billing/success")
        self.assertEqual(sent_payload["cancelUrl"], "https://hayder.xorwia.com/billing/cancel")

    def test_rejects_untrusted_non_stripe_checkout_urls_from_upstream(self):
        token = _make_fake_jwt(sub="sub-url-check")
        bad_urls = [
            "https://evil.example.com/checkout",
            "http://checkout.stripe.com/c/pay/cs_123",
            "https://checkout.stripe.com.evil.com/c/pay/cs_123",
            "https://checkout.stripe.com:abc/c/pay/cs_123",
            "https://checkout.stripe.com:8443/c/pay/cs_123",
            "https://user:pass@checkout.stripe.com/c/pay/cs_123",
            "javascript:alert(1)",
            "https://checkout.stripe.com/",
            "",
            None,
        ]
        for bad_url in bad_urls:
            with self.subTest(bad_url=bad_url):
                event = _make_checkout_event(
                    sub="sub-url-check",
                    token=token,
                    body={"billingInterval": "monthly"},
                )
                fake_resp = io.BytesIO(
                    json.dumps({"id": "cs_test_bad", "url": bad_url}).encode("utf-8")
                )
                fake_resp.getcode = lambda: 200
                with patch.dict(
                    os.environ,
                    {"XORWIA_BILLING_BASE_URL": "https://billing.xorwia.test"},
                ), patch("urllib.request.urlopen", return_value=fake_resp):
                    res = app.lambda_handler(event, None)
                self.assertEqual(res["statusCode"], 502)
                self.assertNotIn("evil", res["body"])

    def test_upstream_errors_do_not_leak_secrets_and_map_cleanly(self):
        token = _make_fake_jwt(sub="sub-err-1")
        event = _make_checkout_event(
            sub="sub-err-1",
            token=token,
            body={"billingInterval": "monthly"},
        )

        # Unconfigured billing URL -> 503 without HTTP call
        with patch.dict(os.environ, {"XORWIA_BILLING_BASE_URL": ""}), \
             patch.object(app, "XORWIA_BILLING_BASE_URL", ""), \
             patch("urllib.request.urlopen") as mock_urlopen:
            res = app.lambda_handler(event, None)
        self.assertEqual(res["statusCode"], 503)
        mock_urlopen.assert_not_called()

        # Non-HTTPS billing URL (e.g. file:// or http://remote) -> 503 without HTTP call
        for unsafe_base in ("file:///etc/passwd", "http://billing.xorwia.test"):
            with patch.dict(os.environ, {"XORWIA_BILLING_BASE_URL": unsafe_base}), \
                 patch("urllib.request.urlopen") as mock_urlopen:
                res = app.lambda_handler(event, None)
            self.assertEqual(res["statusCode"], 503)
            mock_urlopen.assert_not_called()

        # Malformed request host with query/fragment -> 400 without HTTP call
        for bad_host in ("hayder.xorwia.com?evil=1", "hayder.xorwia.com#frag", "hayder.xorwia.com:notaport"):
            bad_host_event = _make_checkout_event(
                sub="sub-err-1",
                token=token,
                domain_name=bad_host,
                body={"billingInterval": "monthly"},
            )
            with patch.dict(
                os.environ,
                {"XORWIA_BILLING_BASE_URL": "https://billing.xorwia.test", "HAYDER_PUBLIC_BASE_URL": ""},
            ), patch("urllib.request.urlopen") as mock_urlopen:
                res = app.lambda_handler(bad_host_event, None)
            self.assertEqual(res["statusCode"], 400)
            mock_urlopen.assert_not_called()

        # Upstream 401 -> 401
        err_401 = HTTPError(
            url="https://billing.xorwia.test/api/create-checkout-session",
            code=401,
            msg="Unauthorized",
            hdrs={},
            fp=io.BytesIO(b'{"error":"secret-token-details"}'),
        )
        with patch.dict(os.environ, {"XORWIA_BILLING_BASE_URL": "https://billing.xorwia.test"}), \
             patch("urllib.request.urlopen", side_effect=err_401):
            res = app.lambda_handler(event, None)
        self.assertEqual(res["statusCode"], 401)
        self.assertNotIn("secret-token-details", res["body"])

        # Upstream 500 -> 502 without leaking secret body
        err_500 = HTTPError(
            url="https://billing.xorwia.test/api/create-checkout-session",
            code=500,
            msg="Server Error",
            hdrs={},
            fp=io.BytesIO(b'{"error":"sk_live_DO_NOT_LEAK"}'),
        )
        with patch.dict(os.environ, {"XORWIA_BILLING_BASE_URL": "https://billing.xorwia.test"}), \
             patch("urllib.request.urlopen", side_effect=err_500):
            res = app.lambda_handler(event, None)
        self.assertEqual(res["statusCode"], 502)
        self.assertNotIn("sk_live_DO_NOT_LEAK", res["body"])

        # Network error -> 502
        with patch.dict(os.environ, {"XORWIA_BILLING_BASE_URL": "https://billing.xorwia.test"}), \
             patch("urllib.request.urlopen", side_effect=URLError("timeout")):
            res = app.lambda_handler(event, None)
        self.assertEqual(res["statusCode"], 502)

    def test_billing_status_requires_auth_and_uses_verified_sub(self):
        unauth_event = _make_checkout_event(
            method="GET",
            path="/billing/status",
            include_auth_claims=False,
        )
        with patch.object(app, "check_hayder_pro") as mock_check:
            res = app.lambda_handler(unauth_event, None)
        self.assertEqual(res["statusCode"], 401)
        mock_check.assert_not_called()

        auth_event = _make_checkout_event(
            method="GET",
            path="/billing/status",
            sub="sub-status-99",
            headers={"x-external-user-id": "hayder:spoofed"},
        )
        with patch.object(app, "check_hayder_pro", return_value=True) as mock_check:
            res = app.lambda_handler(auth_event, None)
        self.assertEqual(res["statusCode"], 200)
        self.assertEqual(json.loads(res["body"]), {"entitled": True, "product": "HAYDER_PRO"})
        mock_check.assert_called_once_with("hayder:sub-status-99", client=None)

    def test_no_duplicate_stripe_integration_in_hayder_core(self):
        for py_file in ("app.py", "auth.py", "voice.py", "web.py"):
            src_text = (SRC / py_file).read_text(encoding="utf-8")
            self.assertNotIn("import stripe", src_text)
            self.assertNotIn("from stripe", src_text)
            self.assertNotIn("sk_live_", src_text)
            self.assertNotIn("sk_test_", src_text)
            self.assertNotIn("price_", src_text)
            self.assertNotIn("api.stripe.com", src_text)

    def test_template_yaml_wires_checkout_and_return_routes_securely(self):
        template_text = (ROOT / "template.yaml").read_text(encoding="utf-8")

        self.assertIn("HayderPublicBaseUrl:", template_text)
        self.assertIn("HAYDER_PUBLIC_BASE_URL: !Ref HayderPublicBaseUrl", template_text)
        self.assertIn("Path: /billing/checkout", template_text)
        self.assertIn("Path: /billing/status", template_text)
        self.assertIn("Path: /billing/success", template_text)
        self.assertIn("Path: /billing/cancel", template_text)

        # Checkout & status routes must NOT bypass DefaultAuthorizer (HayderJwtAuthorizer)
        checkout_block = template_text.split("BillingCheckout:", 1)[1].split("HayderAuthFunction:", 1)[0]
        self.assertNotIn("Authorizer: NONE", checkout_block)


class CheckoutFrontendAndFlowTests(unittest.TestCase):

    def test_pricing_and_return_pages_render_correctly(self):
        pricing = voice.lambda_handler({"rawPath": "/hayder/pricing"}, {})
        self.assertEqual(pricing["statusCode"], 200)
        html = pricing["body"]
        self.assertIn("&pound;9.99", html)
        self.assertIn("&pound;99", html)
        self.assertIn("Proposed", html)
        self.assertIn('id="checkoutMonthlyBtn"', html)
        self.assertIn('id="checkoutAnnualBtn"', html)
        self.assertIn('data-billing-interval="monthly"', html)
        self.assertIn('data-billing-interval="annual"', html)
        self.assertIn("/billing/checkout", html)
        self.assertNotIn("checkout.stripe.com/c/pay/", html)

        success = voice.lambda_handler({"rawPath": "/billing/success"}, {})
        self.assertEqual(success["statusCode"], 200)
        self.assertEqual(success["headers"]["cache-control"], "no-store")
        self.assertIn("/billing/status", success["body"])
        self.assertIn("Hayder Pro", success["body"])

        cancel = voice.lambda_handler({"rawPath": "/billing/cancel"}, {})
        self.assertEqual(cancel["statusCode"], 200)
        self.assertEqual(cancel["headers"]["cache-control"], "no-store")
        self.assertIn("No charge was made", cancel["body"])
        self.assertIn("/hayder/pricing", cancel["body"])

    def test_plan_preservation_across_login_and_checkout_redirect_in_node(self):
        node_path = shutil.which("node")
        if not node_path:
            self.skipTest("node not installed")

        env_backup = {
            "COGNITO_DOMAIN": os.environ.get("COGNITO_DOMAIN"),
            "COGNITO_CLIENT_ID": os.environ.get("COGNITO_CLIENT_ID"),
        }
        try:
            os.environ["COGNITO_DOMAIN"] = "https://hayder-auth.auth.eu-west-2.amazoncognito.com"
            os.environ["COGNITO_CLIENT_ID"] = "client-id-123"
            pricing_html = voice.lambda_handler({"rawPath": "/hayder/pricing"}, {})["body"]
            voice_html = voice.lambda_handler({"rawPath": "/voice"}, {})["body"]
        finally:
            for k, v in env_backup.items():
                if v is None:
                    os.environ.pop(k, None)
                else:
                    os.environ[k] = v

        # Extract pricing script
        pricing_script = pricing_html.split("<script>", 1)[1].rsplit("</script>", 1)[0]

        # Extract voice checkout + PKCE snippets
        voice_script = voice_html.split("<script>", 1)[1].rsplit("</script>", 1)[0]
        # Strip only the final `restoreSession();` auto-invocation so we control calls in Node
        voice_script_controlled = voice_script.rsplit("restoreSession();", 1)[0]

        test_js = f"""
const crypto = require("crypto");

function makeStorage() {{
    const map = new Map();
    return {{
        getItem: (k) => (map.has(k) ? map.get(k) : null),
        setItem: (k, v) => map.set(k, String(v)),
        removeItem: (k) => map.delete(k)
    }};
}}

function makeElement(id) {{
    const classes = new Set();
    return {{
        id,
        value: "",
        textContent: "",
        disabled: false,
        style: {{}},
        attrs: {{}},
        className: "",
        classList: {{
            add: (c) => classes.add(c),
            remove: (c) => classes.delete(c),
            contains: (c) => classes.has(c)
        }},
        setAttribute: function(k, v) {{ this.attrs[k] = v; }},
        getAttribute: function(k) {{ return this.attrs[k] || null; }},
        addEventListener: function() {{}}
    }};
}}

async function runPricingTests() {{
    const sessionStorage = makeStorage();
    const statusBox = makeElement("checkoutStatus");
    const buttons = [makeElement("checkoutMonthlyBtn"), makeElement("checkoutAnnualBtn")];
    const windowObj = {{
        location: {{ href: "https://hayder.xorwia.com/hayder/pricing" }}
    }};
    const documentObj = {{
        getElementById: (id) => (id === "checkoutStatus" ? statusBox : null),
        querySelectorAll: () => buttons
    }};

    let fetchCalls = [];
    let fetchHandler = async () => {{ throw new Error("unexpected fetch"); }};

    const fn = new Function(
        "window", "document", "sessionStorage", "fetch", "URL",
        {json.dumps(pricing_script)} + "\\nreturn {{ startPricingCheckout, isValidStripeCheckoutUrl }};"
    );
    const api = fn(windowObj, documentObj, sessionStorage, (...args) => {{
        fetchCalls.push(args);
        return fetchHandler(...args);
    }}, URL);

    // 1. Unauthenticated click saves plan and redirects to /voice?checkout=annual
    await api.startPricingCheckout("annual");
    if (sessionStorage.getItem("hayder_pending_checkout_plan") !== "annual") {{
        throw new Error("Pending annual plan not stored");
    }}
    if (windowObj.location.href !== "/voice?checkout=annual") {{
        throw new Error("Expected redirect to /voice?checkout=annual, got " + windowObj.location.href);
    }}
    if (fetchCalls.length !== 0) {{
        throw new Error("Unauthenticated click should not call /billing/checkout");
    }}

    // 2. Authenticated click calls POST /billing/checkout and redirects to Stripe Checkout
    sessionStorage.setItem("hayder_id_token", "cognito-jwt-valid");
    sessionStorage.setItem("hayder_expires_at", String(Date.now() + 3600 * 1000));
    fetchHandler = async (url, opts) => ({{
        ok: true,
        status: 200,
        json: async () => ({{
            id: "cs_test_monthly_1",
            url: "https://checkout.stripe.com/c/pay/cs_test_monthly_1"
        }})
    }});
    await api.startPricingCheckout("monthly");
    if (fetchCalls.length !== 1 || fetchCalls[0][0] !== "/billing/checkout") {{
        throw new Error("Expected POST /billing/checkout");
    }}
    if (fetchCalls[0][1].headers.Authorization !== "Bearer cognito-jwt-valid") {{
        throw new Error("Missing Authorization bearer header");
    }}
    if (JSON.parse(fetchCalls[0][1].body).billingInterval !== "monthly") {{
        throw new Error("Wrong billingInterval sent");
    }}
    if (windowObj.location.href !== "https://checkout.stripe.com/c/pay/cs_test_monthly_1") {{
        throw new Error("Did not redirect to Stripe Checkout");
    }}

    // 3. Reject non-Stripe redirect URL returned by API
    windowObj.location.href = "https://hayder.xorwia.com/hayder/pricing";
    fetchHandler = async () => ({{
        ok: true,
        status: 200,
        json: async () => ({{
            id: "cs_evil",
            url: "https://evil.example.com/phish"
        }})
    }});
    await api.startPricingCheckout("monthly");
    if (windowObj.location.href !== "https://hayder.xorwia.com/hayder/pricing") {{
        throw new Error("Redirected to untrusted URL!");
    }}
    if (!statusBox.textContent.includes("invalid checkout")) {{
        throw new Error("Expected invalid checkout error, got: " + statusBox.textContent);
    }}
}}

async function runVoiceLoginPreservationTests() {{
    const sessionStorage = makeStorage();
    const elements = {{}};
    const ids = [
        "loginCard", "assistantCard", "loginButton", "googleSignInButton",
        "googleButton", "logoutButton", "micButton", "sendButton",
        "username", "password", "command", "loginStatus", "status",
        "heard", "reply", "core", "reconnectBanner", "reconnectBannerBtn",
        "checkoutNotice", "checkoutNoticeText", "cancelPendingCheckoutBtn",
        "billingUpgradeBanner"
    ];
    for (const id of ids) elements[id] = makeElement(id);

    let replacedUrl = null;
    const windowObj = {{
        crypto: crypto.webcrypto,
        location: {{
            origin: "https://hayder.xorwia.com",
            pathname: "/voice",
            search: "?checkout=annual",
            href: "https://hayder.xorwia.com/voice?checkout=annual"
        }},
        history: {{
            replaceState: (_s, _t, url) => {{ replacedUrl = url; }}
        }},
        speechSynthesis: {{
            cancel: () => {{}},
            getVoices: () => []
        }}
    }};
    const documentObj = {{
        getElementById: (id) => elements[id] || null
    }};

    let fetchCalls = [];
    let fetchHandler = async () => {{ throw new Error("unexpected fetch"); }};

    const fn = new Function(
        "window", "document", "sessionStorage", "fetch", "URL", "URLSearchParams", "TextEncoder", "btoa",
        {json.dumps(voice_script_controlled)} + "\\nreturn {{ restoreSession, startGoogleSignIn, handleGoogleSignInCallback, login, getPendingCheckoutPlan }};"
    );
    const api = fn(
        windowObj,
        documentObj,
        sessionStorage,
        (...args) => {{
            fetchCalls.push(args);
            return fetchHandler(...args);
        }},
        URL,
        URLSearchParams,
        TextEncoder,
        (str) => Buffer.from(str, "binary").toString("base64")
    );

    // 1. Arrive at /voice?checkout=annual unauthenticated -> captures plan and shows notice
    await api.restoreSession();
    if (api.getPendingCheckoutPlan() !== "annual") {{
        throw new Error("Pending plan not captured from query");
    }}
    if (replacedUrl !== "/voice") {{
        throw new Error("Query param not cleaned");
    }}
    if (elements.checkoutNotice.classList.contains("hidden")) {{
        throw new Error("Checkout notice should be visible");
    }}

    // 2. Start Google Cognito PKCE sign-in -> pending plan survives in sessionStorage
    windowObj.location.search = "";
    await api.startGoogleSignIn();
    const savedState = sessionStorage.getItem("hayder_oauth_state");
    if (sessionStorage.getItem("hayder_pending_checkout_plan") !== "annual") {{
        throw new Error("Pending plan lost during Google PKCE start");
    }}

    // 3. Return from Cognito Google PKCE callback -> exchanges code AND resumes annual checkout
    windowObj.location.search = "?code=google-auth-code&state=" + encodeURIComponent(savedState);
    fetchHandler = async (url, opts) => {{
        if (url.endsWith("/oauth2/token")) {{
            return {{
                ok: true,
                status: 200,
                json: async () => ({{
                    id_token: "cognito-google-jwt",
                    refresh_token: "cognito-google-refresh",
                    expires_in: 3600
                }})
            }};
        }}
        if (url === "/billing/checkout") {{
            const payload = JSON.parse(opts.body);
            if (payload.billingInterval !== "annual") {{
                throw new Error("Expected annual checkout after Google login, got " + payload.billingInterval);
            }}
            if (opts.headers.Authorization !== "Bearer cognito-google-jwt") {{
                throw new Error("Wrong Authorization header on checkout after Google login");
            }}
            return {{
                ok: true,
                status: 200,
                json: async () => ({{
                    id: "cs_after_google",
                    url: "https://checkout.stripe.com/c/pay/cs_after_google"
                }})
            }};
        }}
        throw new Error("Unexpected URL: " + url);
    }};

    await api.handleGoogleSignInCallback();
    if (windowObj.location.href !== "https://checkout.stripe.com/c/pay/cs_after_google") {{
        throw new Error("Did not redirect to Stripe Checkout after Google login: " + windowObj.location.href);
    }}
    if (sessionStorage.getItem("hayder_pending_checkout_plan") !== null) {{
        throw new Error("Pending plan not cleared after redirect");
    }}

    // 4. Email/password login also resumes pending monthly checkout
    sessionStorage.setItem("hayder_pending_checkout_plan", "monthly");
    elements.username.value = "founder@example.com";
    elements.password.value = "test-pass-123";
    fetchHandler = async (url, opts) => {{
        if (url === "/auth/login") {{
            return {{
                ok: true,
                status: 200,
                json: async () => ({{
                    id_token: "cognito-pw-jwt",
                    refresh_token: "cognito-pw-refresh",
                    expires_in: 3600
                }})
            }};
        }}
        if (url === "/billing/checkout") {{
            const payload = JSON.parse(opts.body);
            if (payload.billingInterval !== "monthly") {{
                throw new Error("Expected monthly checkout after password login");
            }}
            return {{
                ok: true,
                status: 200,
                json: async () => ({{
                    id: "cs_after_pw",
                    url: "https://checkout.stripe.com/c/pay/cs_after_pw"
                }})
            }};
        }}
        throw new Error("Unexpected URL: " + url);
    }};
    await api.login();
    if (windowObj.location.href !== "https://checkout.stripe.com/c/pay/cs_after_pw") {{
        throw new Error("Did not redirect to Stripe Checkout after password login");
    }}
}}

Promise.all([runPricingTests(), runVoiceLoginPreservationTests()])
    .then(() => console.log("CHECKOUT_FLOW_OK"))
    .catch((err) => {{
        console.error(err);
        process.exit(1);
    }});
"""
        proc = subprocess.run([node_path, "-e", test_js], capture_output=True, text=True)
        self.assertEqual(
            proc.returncode,
            0,
            msg=f"Checkout JS flow test failed:\nstdout: {proc.stdout}\nstderr: {proc.stderr}",
        )
        self.assertIn("CHECKOUT_FLOW_OK", proc.stdout)


if __name__ == "__main__":
    unittest.main()
