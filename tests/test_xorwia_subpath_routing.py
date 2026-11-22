"""
Focused path-routing tests for serving Hayder at https://xorwia.com/hayder
via API Gateway HTTP API base-path mapping (ApiMappingKey="hayder").

Validates:
1. Root /hayder (APIGW base-path-stripped rawPath="/" on xorwia.com and HAYDER_PUBLIC_BASE_URL)
   and all marketing/legal subpages render 200 with /hayder-prefixed links and zero /hayder/hayder duplication
2. /hayder/voice (stripped rawPath="/voice" on xorwia.com and direct rawPath="/hayder/voice")
   wires API calls, Cognito PKCE redirect_uri=https://xorwia.com/hayder/voice, email/password login,
   and Gmail OAuth connect under /hayder/*
3. /hayder/billing/* (checkout, status, success, cancel) resolves Stripe return URLs to
   https://xorwia.com/hayder/billing/{success,cancel} and serves no-store return pages
4. Gmail OAuth connect & callback preserve existing flow with
   redirect_uri=https://xorwia.com/hayder/oauth/google/callback and /hayder/voice return links
5. template.yaml exposes base-path-stripped routes and xorwia.com/hayder callbacks/defaults
"""

import base64
import importlib
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
from urllib.parse import parse_qs, urlparse

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
sys.path.insert(0, str(SRC))

os.environ.setdefault("HAYDER_TABLE", "test-memory")
os.environ.setdefault("HAYDER_APPROVAL_TABLE", "test-approvals")
os.environ.setdefault("AWS_LAMBDA_FUNCTION_NAME", "test-function")
os.environ.setdefault("COGNITO_CLIENT_ID", "test-cognito-client-id")


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
            initiate_auth=Mock(
                return_value={
                    "AuthenticationResult": {
                        "IdToken": "fake-id-token",
                        "RefreshToken": "fake-refresh-token",
                        "ExpiresIn": 3600,
                        "TokenType": "Bearer",
                    }
                }
            ),
            exceptions=SimpleNamespace(
                NotAuthorizedException=Exception,
                UserNotFoundException=Exception,
                UserNotConfirmedException=Exception,
            ),
        )


sys.modules.setdefault("boto3", FakeBoto3())
app = importlib.import_module("app")
auth = importlib.import_module("auth")
voice = importlib.import_module("voice")
web = importlib.import_module("web")


def _make_fake_jwt(sub="sub-subpath-1", email="founder@xorwia.com"):
    header = base64.urlsafe_b64encode(
        json.dumps({"alg": "RS256", "kid": "kid-1", "typ": "JWT"}).encode("utf-8")
    ).decode("utf-8").rstrip("=")
    payload = base64.urlsafe_b64encode(
        json.dumps({"sub": sub, "email": email, "token_use": "id"}).encode("utf-8")
    ).decode("utf-8").rstrip("=")
    sig = base64.urlsafe_b64encode(b"sig-bytes").decode("utf-8").rstrip("=")
    return f"{header}.{payload}.{sig}"


def _xorwia_event(path, *, method="GET", domain="xorwia.com", sub=None, token=None, body=None, headers=None):
    req_headers = dict(headers or {})
    if token:
        req_headers["authorization"] = f"Bearer {token}"
    request_context = {
        "domainName": domain,
        "http": {"method": method},
    }
    if sub:
        request_context["authorizer"] = {
            "jwt": {"claims": {"sub": sub, "email": "founder@xorwia.com"}}
        }
    event = {
        "rawPath": path,
        "requestContext": request_context,
        "headers": req_headers,
    }
    if body is not None:
        event["body"] = json.dumps(body) if isinstance(body, dict) else str(body)
    return event


class XorwiaSubpathRoutingTests(unittest.TestCase):

    def test_root_hayder_via_apigw_basepath_mapping_renders_home_with_prefixed_links(self):
        # API Gateway HTTP API (PFV 2.0) strips ApiMappingKey="hayder" -> rawPath="/"
        for domain in ("xorwia.com", "www.xorwia.com"):
            with self.subTest(domain=domain):
                res = voice.lambda_handler(_xorwia_event("/", domain=domain), {})
                self.assertEqual(res["statusCode"], 200)
                html = res["body"]
                self.assertIn("Your day, prepared.", html)
                self.assertIn('href="/hayder"', html)
                self.assertIn('href="/hayder/features"', html)
                self.assertIn('href="/hayder/pricing"', html)
                self.assertIn('href="/hayder/voice"', html)
                self.assertIn('href="/hayder/privacy"', html)
                self.assertIn('href="/hayder/terms"', html)
                self.assertNotIn('href="/hayder/hayder', html)
                self.assertNotIn('href="/voice"', html)
                self.assertNotIn('href="/privacy"', html)
                self.assertNotIn('href="/terms"', html)

        # Also works via HAYDER_PUBLIC_BASE_URL even without domainName in event
        with patch.dict(os.environ, {"HAYDER_PUBLIC_BASE_URL": "https://xorwia.com/hayder"}):
            res = voice.lambda_handler({"rawPath": "/"}, {})
        self.assertEqual(res["statusCode"], 200)
        self.assertIn('href="/hayder/voice"', res["body"])

    def test_stripped_marketing_and_legal_routes_under_xorwia_basepath(self):
        stripped_routes = [
            "/",
            "/features",
            "/how-it-works",
            "/security",
            "/pricing",
            "/about",
            "/support",
            "/privacy",
            "/terms",
            "/hayder/privacy",
            "/hayder/terms",
        ]
        for route in stripped_routes:
            with self.subTest(route=route):
                res = voice.lambda_handler(_xorwia_event(route), {})
                self.assertEqual(res["statusCode"], 200)
                html = res["body"]
                self.assertIn('href="/hayder/voice"', html)
                self.assertIn('href="/hayder/privacy"', html)
                self.assertIn('href="/hayder/terms"', html)
                self.assertNotIn('href="/hayder/hayder', html)

    def test_hayder_voice_routes_and_client_js_under_xorwia_subpath(self):
        # Both APIGW-stripped (/voice on xorwia.com) and direct (/hayder/voice) render Voice page
        for raw_path in ("/voice", "/hayder/voice"):
            with self.subTest(raw_path=raw_path):
                res = voice.lambda_handler(_xorwia_event(raw_path), {})
                self.assertEqual(res["statusCode"], 200)
                html = res["body"]
                self.assertIn('const HAYDER_BASE_PATH = "/hayder";', html)
                self.assertIn('href="/hayder/voice"', html)
                self.assertIn('href="/hayder/pricing"', html)
                self.assertIn('href="/hayder/privacy"', html)
                self.assertIn('href="/hayder/terms"', html)
                self.assertNotIn('href="/voice"', html)

        node_path = shutil.which("node")
        if not node_path:
            self.skipTest("node not installed")

        with patch.dict(
            os.environ,
            {
                "COGNITO_DOMAIN": "https://hayder-auth.auth.eu-west-2.amazoncognito.com",
                "COGNITO_CLIENT_ID": "1t0bidostmftdun12kjih0udj5",
                "HAYDER_PUBLIC_BASE_URL": "https://xorwia.com/hayder",
            },
        ):
            voice_html = voice.lambda_handler(_xorwia_event("/voice"), {})["body"]
            pricing_html = voice.lambda_handler(_xorwia_event("/pricing"), {})["body"]
            success_html = voice.lambda_handler(_xorwia_event("/billing/success"), {})["body"]

        voice_script = voice_html.split("<script>", 1)[1].rsplit("</script>", 1)[0].rsplit("restoreSession();", 1)[0]
        pricing_script = pricing_html.split("<script>", 1)[1].rsplit("</script>", 1)[0]
        success_script = success_html.split("<script>", 1)[1].rsplit("</script>", 1)[0].rsplit("checkBillingActivation(1);", 1)[0]

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

function makeEl(id) {{
    const classes = new Set();
    return {{
        id, value: "", textContent: "", disabled: false, style: {{}}, attrs: {{}}, className: "",
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

async function run() {{
    // 1. Voice page under https://xorwia.com/hayder/voice
    const storage = makeStorage();
    const els = {{}};
    for (const id of [
        "loginCard", "assistantCard", "loginButton", "googleSignInButton",
        "googleButton", "logoutButton", "micButton", "sendButton",
        "username", "password", "command", "loginStatus", "status",
        "heard", "reply", "core", "reconnectBanner", "reconnectBannerBtn",
        "checkoutNotice", "checkoutNoticeText", "cancelPendingCheckoutBtn",
        "billingUpgradeBanner"
    ]) els[id] = makeEl(id);

    let replacedUrl = null;
    const win = {{
        crypto: crypto.webcrypto,
        location: {{
            origin: "https://xorwia.com",
            pathname: "/hayder/voice",
            search: "",
            href: "https://xorwia.com/hayder/voice"
        }},
        history: {{ replaceState: (_s, _t, u) => {{ replacedUrl = u; }} }},
        speechSynthesis: {{ cancel: () => {{}}, getVoices: () => [] }}
    }};
    const doc = {{ getElementById: (id) => els[id] || null }};

    const calls = [];
    let fetchImpl = async (url, opts) => {{
        calls.push(url);
        if (url === "/hayder/auth/login") {{
            return {{ ok: true, status: 200, json: async () => ({{ id_token: "id-1", refresh_token: "ref-1", expires_in: 3600 }}) }};
        }}
        if (url === "/hayder/chat") {{
            return {{ ok: true, status: 200, json: async () => ({{ reply: "All clear." }}) }};
        }}
        if (url === "/hayder/oauth/google/connect") {{
            return {{ ok: true, status: 200, json: async () => ({{ authorization_url: "https://accounts.google.com/o/oauth2/v2/auth?state=s1" }}) }};
        }}
        if (url.endsWith("/oauth2/token")) {{
            const body = new URLSearchParams(opts.body);
            if (body.get("redirect_uri") !== "https://xorwia.com/hayder/voice") {{
                throw new Error("Wrong token exchange redirect_uri: " + body.get("redirect_uri"));
            }}
            return {{ ok: true, status: 200, json: async () => ({{ id_token: "google-id", refresh_token: "google-ref", expires_in: 3600 }}) }};
        }}
        throw new Error("Unexpected voice fetch URL: " + url);
    }};

    const voiceApi = new Function(
        "window", "document", "sessionStorage", "fetch", "URL", "URLSearchParams", "TextEncoder", "btoa",
        {json.dumps(voice_script)} + "\\nreturn {{ startGoogleSignIn, handleGoogleSignInCallback, login, sendToHayder, triggerGoogleConnect }};"
    )(win, doc, storage, (...a) => fetchImpl(...a), URL, URLSearchParams, TextEncoder, (s) => Buffer.from(s, "binary").toString("base64"));

    // Cognito PKCE authorize + callback redirect_uri
    await voiceApi.startGoogleSignIn();
    const authUrl = new URL(win.location.href);
    if (authUrl.searchParams.get("redirect_uri") !== "https://xorwia.com/hayder/voice") {{
        throw new Error("Wrong Cognito authorize redirect_uri: " + authUrl.searchParams.get("redirect_uri"));
    }}
    const st = storage.getItem("hayder_oauth_state");
    win.location.search = "?code=abc&state=" + encodeURIComponent(st);
    await voiceApi.handleGoogleSignInCallback();
    if (replacedUrl !== "/hayder/voice") throw new Error("Expected replaceState /hayder/voice, got " + replacedUrl);

    // Email/password login, chat, and Gmail OAuth connect all hit /hayder/*
    els.username.value = "user@xorwia.com";
    els.password.value = "secret123";
    await voiceApi.login();
    await voiceApi.sendToHayder("brief me");
    await voiceApi.triggerGoogleConnect();
    for (const expected of ["/hayder/auth/login", "/hayder/chat", "/hayder/oauth/google/connect"]) {{
        if (!calls.includes(expected)) throw new Error("Missing call to " + expected + "; got " + JSON.stringify(calls));
    }}

    // 2. Pricing page under https://xorwia.com/hayder/pricing
    const pStorage = makeStorage();
    const pWin = {{ location: {{ href: "https://xorwia.com/hayder/pricing" }} }};
    const pDoc = {{ getElementById: () => makeEl("checkoutStatus"), querySelectorAll: () => [] }};
    const pCalls = [];
    const pricingApi = new Function(
        "window", "document", "sessionStorage", "fetch", "URL",
        {json.dumps(pricing_script)} + "\\nreturn {{ startPricingCheckout }};"
    )(pWin, pDoc, pStorage, async (url) => {{
        pCalls.push(url);
        return {{ ok: true, status: 200, json: async () => ({{ id: "cs_1", url: "https://checkout.stripe.com/c/pay/cs_1" }}) }};
    }}, URL);

    await pricingApi.startPricingCheckout("monthly");
    if (pWin.location.href !== "/hayder/voice?checkout=monthly") {{
        throw new Error("Expected /hayder/voice?checkout=monthly, got " + pWin.location.href);
    }}
    pStorage.setItem("hayder_id_token", "tok");
    pStorage.setItem("hayder_expires_at", String(Date.now() + 3600000));
    await pricingApi.startPricingCheckout("annual");
    if (pCalls[0] !== "/hayder/billing/checkout") {{
        throw new Error("Expected /hayder/billing/checkout, got " + pCalls[0]);
    }}

    // 3. Billing success page polls /hayder/billing/status
    const sStorage = makeStorage();
    sStorage.setItem("hayder_id_token", "tok");
    sStorage.setItem("hayder_expires_at", String(Date.now() + 3600000));
    const sCalls = [];
    const sDoc = {{ getElementById: (id) => makeEl(id) }};
    const successApi = new Function(
        "document", "sessionStorage", "fetch", "setTimeout", "clearTimeout",
        {json.dumps(success_script)} + "\\nreturn {{ checkBillingActivation }};"
    )(sDoc, sStorage, async (url) => {{
        sCalls.push(url);
        return {{ ok: true, status: 200, json: async () => ({{ entitled: true }}) }};
    }}, () => 1, () => {{}});
    await successApi.checkBillingActivation(1);
    if (sCalls[0] !== "/hayder/billing/status") {{
        throw new Error("Expected /hayder/billing/status, got " + sCalls[0]);
    }}
}}

run().then(() => console.log("SUBPATH_JS_OK")).catch((e) => {{ console.error(e); process.exit(1); }});
"""
        proc = subprocess.run([node_path, "-e", test_js], capture_output=True, text=True)
        self.assertEqual(proc.returncode, 0, msg=f"Subpath JS failed:\n{proc.stdout}\n{proc.stderr}")
        self.assertIn("SUBPATH_JS_OK", proc.stdout)

    def test_hayder_billing_checkout_status_and_return_pages(self):
        token = _make_fake_jwt(sub="sub-bill-1")
        fake_resp = io.BytesIO(
            json.dumps({
                "id": "cs_subpath_1",
                "url": "https://checkout.stripe.com/c/pay/cs_subpath_1",
            }).encode("utf-8")
        )
        fake_resp.getcode = lambda: 200

        # Case A: APIGW-stripped /billing/checkout on xorwia.com without env var
        event_stripped = _xorwia_event(
            "/billing/checkout",
            method="POST",
            domain="xorwia.com",
            sub="sub-bill-1",
            token=token,
            body={"billingInterval": "monthly"},
        )
        with patch.dict(
            os.environ,
            {"XORWIA_BILLING_BASE_URL": "https://xorwia.com", "HAYDER_PUBLIC_BASE_URL": ""},
        ), patch("urllib.request.urlopen", return_value=fake_resp) as mock_urlopen:
            res = app.lambda_handler(event_stripped, None)
        self.assertEqual(res["statusCode"], 200)
        sent = json.loads(mock_urlopen.call_args[0][0].data.decode("utf-8"))
        self.assertEqual(sent["successUrl"], "https://xorwia.com/hayder/billing/success")
        self.assertEqual(sent["cancelUrl"], "https://xorwia.com/hayder/billing/cancel")

        # Case B: Prefixed /hayder/billing/checkout with HAYDER_PUBLIC_BASE_URL="https://xorwia.com/hayder"
        fake_resp2 = io.BytesIO(
            json.dumps({
                "id": "cs_subpath_2",
                "url": "https://checkout.stripe.com/c/pay/cs_subpath_2",
            }).encode("utf-8")
        )
        fake_resp2.getcode = lambda: 200
        event_prefixed = _xorwia_event(
            "/hayder/billing/checkout",
            method="POST",
            domain="is9bdp47z3.execute-api.eu-west-2.amazonaws.com",
            sub="sub-bill-1",
            token=token,
            body={"billingInterval": "annual"},
        )
        with patch.dict(
            os.environ,
            {
                "XORWIA_BILLING_BASE_URL": "https://xorwia.com",
                "HAYDER_PUBLIC_BASE_URL": "https://xorwia.com/hayder",
            },
        ), patch("urllib.request.urlopen", return_value=fake_resp2) as mock_urlopen2:
            res2 = app.lambda_handler(event_prefixed, None)
        self.assertEqual(res2["statusCode"], 200)
        sent2 = json.loads(mock_urlopen2.call_args[0][0].data.decode("utf-8"))
        self.assertEqual(sent2["successUrl"], "https://xorwia.com/hayder/billing/success")
        self.assertEqual(sent2["cancelUrl"], "https://xorwia.com/hayder/billing/cancel")

        # Reject unsafe HAYDER_PUBLIC_BASE_URL paths (traversal, double-slash, query)
        for bad_base in (
            "https://xorwia.com/hayder/../evil",
            "https://xorwia.com//hayder",
            "https://xorwia.com/hayder?x=1",
        ):
            with patch.dict(
                os.environ,
                {"XORWIA_BILLING_BASE_URL": "https://xorwia.com", "HAYDER_PUBLIC_BASE_URL": bad_base},
            ), patch("urllib.request.urlopen") as mock_bad:
                bad_res = app.lambda_handler(event_stripped, None)
            self.assertEqual(bad_res["statusCode"], 500)
            mock_bad.assert_not_called()

        # /billing/status and /hayder/billing/status both work
        for status_path in ("/billing/status", "/hayder/billing/status"):
            status_event = _xorwia_event(status_path, method="GET", sub="sub-bill-1")
            with patch.object(app, "check_hayder_pro", return_value=True):
                st_res = app.lambda_handler(status_event, None)
            self.assertEqual(st_res["statusCode"], 200)
            self.assertEqual(json.loads(st_res["body"])["entitled"], True)

        # /billing/success, /hayder/billing/success, /billing/cancel, /hayder/billing/cancel
        for page_path in (
            "/billing/success",
            "/hayder/billing/success",
            "/billing/cancel",
            "/hayder/billing/cancel",
        ):
            page_res = voice.lambda_handler(_xorwia_event(page_path), {})
            self.assertEqual(page_res["statusCode"], 200)
            self.assertEqual(page_res["headers"]["cache-control"], "no-store")
            self.assertIn('href="/hayder/voice"', page_res["body"])
            self.assertNotIn('href="/voice"', page_res["body"])

    def test_gmail_oauth_connect_and_callback_under_xorwia_subpath(self):
        # Connect uses https://xorwia.com/hayder/oauth/google/callback
        connect_event = _xorwia_event("/oauth/google/connect", method="GET", sub="sub-gmail-1")
        with patch.dict(os.environ, {"HAYDER_PUBLIC_BASE_URL": "https://xorwia.com/hayder"}), \
             patch.object(app, "get_google_credentials", return_value=("cid", "csec")), \
             patch.object(app, "create_google_state", return_value="signed-state"):
            res = app.lambda_handler(connect_event, None)
        self.assertEqual(res["statusCode"], 200)
        body = json.loads(res["body"])
        qs = parse_qs(urlparse(body["authorization_url"]).query)
        self.assertEqual(qs["redirect_uri"], ["https://xorwia.com/hayder/oauth/google/callback"])

        # Callback (both stripped and /hayder-prefixed) exchanges with same redirect_uri and links to /hayder/voice
        for cb_path in ("/oauth/google/callback", "/hayder/oauth/google/callback"):
            cb_event = _xorwia_event(cb_path, method="GET", headers={"accept": "text/html"})
            cb_event["queryStringParameters"] = {"code": "g-code", "state": "signed-state"}
            with patch.dict(os.environ, {"HAYDER_PUBLIC_BASE_URL": ""}), \
                 patch.object(app, "verify_google_state", return_value="sub-gmail-1"), \
                 patch.object(app, "get_google_credentials", return_value=("cid", "csec")), \
                 patch.object(
                     app,
                     "post_form",
                     return_value={"access_token": "at-1", "refresh_token": "rt-1"},
                 ) as mock_post, \
                 patch.object(app, "google_api_get", return_value={"emailAddress": "founder@gmail.com"}), \
                 patch.object(app, "store_google_refresh_token"):
                cb_res = app.lambda_handler(cb_event, None)
            self.assertEqual(cb_res["statusCode"], 200)
            self.assertEqual(
                mock_post.call_args[0][1]["redirect_uri"],
                "https://xorwia.com/hayder/oauth/google/callback",
            )
            self.assertIn('href="/hayder/voice"', cb_res["body"])
            self.assertNotIn('href="/voice"', cb_res["body"])

        # Browser error callback also links back to /hayder/voice
        err_event = _xorwia_event("/oauth/google/callback", method="GET", headers={"accept": "text/html"})
        err_event["queryStringParameters"] = {"error": "access_denied"}
        err_res = app.lambda_handler(err_event, None)
        self.assertEqual(err_res["statusCode"], 400)
        self.assertIn('href="/hayder/voice"', err_res["body"])

    def test_auth_lambda_accepts_both_stripped_and_hayder_prefixed_paths(self):
        fake_cognito = SimpleNamespace(
            initiate_auth=Mock(
                return_value={
                    "AuthenticationResult": {
                        "IdToken": "fake-id-token",
                        "RefreshToken": "fake-refresh-token",
                        "ExpiresIn": 3600,
                        "TokenType": "Bearer",
                    }
                }
            ),
            exceptions=SimpleNamespace(
                NotAuthorizedException=Exception,
                UserNotFoundException=Exception,
                UserNotConfirmedException=Exception,
            ),
        )
        with patch.object(auth, "cognito", fake_cognito):
            for login_path in ("/auth/login", "/hayder/auth/login"):
                res = auth.lambda_handler(
                    _xorwia_event(
                        login_path,
                        method="POST",
                        body={"username": "founder@xorwia.com", "password": "pw"},
                    ),
                    None,
                )
                self.assertEqual(res["statusCode"], 200)
                self.assertEqual(json.loads(res["body"])["id_token"], "fake-id-token")

            for refresh_path in ("/auth/refresh", "/hayder/auth/refresh"):
                res = auth.lambda_handler(
                    _xorwia_event(
                        refresh_path,
                        method="POST",
                        body={"refresh_token": "ref-tok"},
                    ),
                    None,
                )
                self.assertEqual(res["statusCode"], 200)
                self.assertEqual(json.loads(res["body"])["id_token"], "fake-id-token")

    def test_template_yaml_configures_basepath_routes_and_xorwia_callbacks(self):
        template_text = (ROOT / "template.yaml").read_text(encoding="utf-8")

        self.assertIn('Default: "https://xorwia.com/hayder"', template_text)
        self.assertIn('Default: "https://xorwia.com/hayder/voice"', template_text)
        self.assertIn('"https://www.xorwia.com/hayder/voice"', template_text)
        for route in (
            "Path: /",
            "Path: /features",
            "Path: /how-it-works",
            "Path: /security",
            "Path: /pricing",
            "Path: /about",
            "Path: /support",
            "Path: /voice",
            "Path: /billing/checkout",
            "Path: /billing/status",
            "Path: /billing/success",
            "Path: /billing/cancel",
        ):
            self.assertIn(route, template_text)

        # HAYDER_PUBLIC_BASE_URL wired to both HayderCoreFunction and HayderVoiceFunction
        self.assertEqual(template_text.count("HAYDER_PUBLIC_BASE_URL: !Ref HayderPublicBaseUrl"), 2)

    def test_direct_execute_api_host_stays_unprefixed_even_when_public_base_url_is_set(self):
        exec_host = "is9bdp47z3.execute-api.eu-west-2.amazonaws.com"
        with patch.dict(os.environ, {"HAYDER_PUBLIC_BASE_URL": "https://xorwia.com/hayder"}):
            # Voice page on execute-api must keep HAYDER_BASE_PATH="" so /auth/login, /chat, /voice work
            voice_res = voice.lambda_handler(_xorwia_event("/voice", domain=exec_host), {})
            self.assertEqual(voice_res["statusCode"], 200)
            self.assertIn('const HAYDER_BASE_PATH = "";', voice_res["body"])
            self.assertIn('href="/voice"', voice_res["body"])

            # Root "/" on execute-api still returns 404 (not claimed)
            root_res = voice.lambda_handler(_xorwia_event("/", domain=exec_host), {})
            self.assertEqual(root_res["statusCode"], 404)

            # Gmail OAuth on execute-api keeps direct execute-api callback and /voice link
            connect_event = _xorwia_event("/oauth/google/connect", method="GET", domain=exec_host, sub="sub-exec-1")
            with patch.object(app, "get_google_credentials", return_value=("cid", "csec")), \
                 patch.object(app, "create_google_state", return_value="signed-state"):
                conn_res = app.lambda_handler(connect_event, None)
            self.assertEqual(conn_res["statusCode"], 200)
            qs = parse_qs(urlparse(json.loads(conn_res["body"])["authorization_url"]).query)
            self.assertEqual(qs["redirect_uri"], [f"https://{exec_host}/oauth/google/callback"])

            err_cb = _xorwia_event(
                "/oauth/google/callback",
                method="GET",
                domain=exec_host,
                headers={"accept": "text/html"},
            )
            err_cb["queryStringParameters"] = {"error": "access_denied"}
            cb_res = app.lambda_handler(err_cb, None)
            self.assertEqual(cb_res["statusCode"], 400)
            self.assertIn('href="/voice"', cb_res["body"])


if __name__ == "__main__":
    unittest.main()
