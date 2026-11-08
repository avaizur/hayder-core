"""
Focused unit tests for Hayder Google sign-in via Cognito Federation (OAuth 2.0 Authorization Code + PKCE).

Validates:
1. template.yaml configuration:
   - Placeholder parameters (no real secrets)
   - HayderUserPoolDomain and HayderGoogleIdentityProvider (openid email profile)
   - HayderUserPoolClient preserves USER_PASSWORD_AUTH & REFRESH_TOKEN_AUTH while enabling code flow + Google IdP
   - CallbackURLs / LogoutURLs include API Gateway /voice and https://hayder.xorwia.com/voice
   - No automatic PreSignUp identity linking trigger configured
2. voice.py PKCE flow & separation from Gmail/Calendar OAuth:
   - Preserves email/password login (#username, #password, #loginButton, /auth/login)
   - Preserves Gmail/Calendar OAuth (#googleButton, /oauth/google/connect)
   - Implements startGoogleSignIn() with S256 PKCE challenge & state in sessionStorage
   - Implements handleGoogleSignInCallback() validating state & code_verifier, exchanging code at /oauth2/token, and storing session tokens
"""

import importlib
import os
import shutil
import subprocess
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
sys.path.insert(0, str(SRC))

voice = importlib.import_module("voice")


class GoogleCognitoPkceSignupTests(unittest.TestCase):

    def test_template_yaml_cognito_google_federation_and_no_auto_linking(self):
        template_text = (ROOT / "template.yaml").read_text(encoding="utf-8")

        # Placeholder parameters without real secrets
        self.assertIn("CognitoDomainPrefix:", template_text)
        self.assertIn('Default: "hayder-auth-placeholder"', template_text)
        self.assertIn("GoogleFederationClientId:", template_text)
        self.assertIn('Default: "GOOGLE_FEDERATION_CLIENT_ID_PLACEHOLDER"', template_text)
        self.assertIn("GoogleFederationClientSecret:", template_text)
        self.assertIn('Default: "GOOGLE_FEDERATION_CLIENT_SECRET_PLACEHOLDER"', template_text)
        self.assertIn("HayderCustomVoiceCallbackUrl:", template_text)
        self.assertIn('Default: "https://hayder.xorwia.com/voice"', template_text)

        # Cognito Domain & Google IdP resources
        self.assertIn("HayderUserPoolDomain:", template_text)
        self.assertIn("Type: AWS::Cognito::UserPoolDomain", template_text)
        self.assertIn("HayderGoogleIdentityProvider:", template_text)
        self.assertIn("Type: AWS::Cognito::UserPoolIdentityProvider", template_text)
        self.assertIn("ProviderName: Google", template_text)
        self.assertIn("ProviderType: Google", template_text)
        self.assertIn('authorize_scopes: "openid email profile"', template_text)

        # UserPoolClient is public (no client secret), preserves password/refresh flows, and adds code OAuth + Google IdP
        self.assertIn("GenerateSecret: false", template_text)
        self.assertNotIn("GenerateSecret: true", template_text)
        self.assertIn("ALLOW_USER_PASSWORD_AUTH", template_text)
        self.assertIn("ALLOW_REFRESH_TOKEN_AUTH", template_text)
        self.assertIn("SupportedIdentityProviders:", template_text)
        self.assertIn("- COGNITO", template_text)
        self.assertIn("- Google", template_text)
        self.assertIn("AllowedOAuthFlowsUserPoolClient: true", template_text)
        self.assertIn("AllowedOAuthFlows:", template_text)
        self.assertIn("- code", template_text)
        self.assertIn('!Sub "https://${HayderApi}.execute-api.${AWS::Region}.amazonaws.com/voice"', template_text)
        self.assertIn("!Ref HayderCustomVoiceCallbackUrl", template_text)

        # Strictly no automatic PreSignUp account linking
        self.assertNotIn("PreSignUp", template_text)
        self.assertNotIn("admin_link_provider_for_user", template_text)
        self.assertNotIn("AdminLinkProviderForUser", template_text)

    def test_voice_page_preserves_password_login_and_gmail_oauth_separation(self):
        res = voice.lambda_handler({"rawPath": "/voice"}, {})
        self.assertEqual(res["statusCode"], 200)
        html = res["body"]

        # Existing email/password sign-in elements
        self.assertIn('id="username"', html)
        self.assertIn('id="password"', html)
        self.assertIn('id="loginButton"', html)
        self.assertIn('"/auth/login"', html)

        # Separate Cognito Google sign-in button in loginCard
        self.assertIn('id="googleSignInButton"', html)
        self.assertIn("Continue with Google", html)

        # Separate workspace Gmail/Calendar OAuth button in assistantCard
        self.assertIn('id="googleButton"', html)
        self.assertIn("/oauth/google/connect", html)

    def test_voice_pkce_redirect_and_callback_flow_in_node(self):
        node_path = shutil.which("node")
        if not node_path:
            self.skipTest("node not installed")

        env_backup = {
            "COGNITO_DOMAIN": os.environ.get("COGNITO_DOMAIN"),
            "COGNITO_CLIENT_ID": os.environ.get("COGNITO_CLIENT_ID"),
        }
        try:
            os.environ["COGNITO_DOMAIN"] = "https://hayder-auth.auth.eu-west-2.amazoncognito.com"
            os.environ["COGNITO_CLIENT_ID"] = "1t0bidostmftdun12kjih0udj5"
            res = voice.lambda_handler({"rawPath": "/voice"}, {})
            html = res["body"]
        finally:
            for k, v in env_backup.items():
                if v is None:
                    os.environ.pop(k, None)
                else:
                    os.environ[k] = v

        start_idx = html.find("const COGNITO_DOMAIN =")
        self.assertNotEqual(start_idx, -1)
        pkce_start_idx = html.find("function stripTrailingSlashes(")
        pkce_end_idx = html.find("if (googleSignInButton) {\n    googleSignInButton.addEventListener(")
        self.assertNotEqual(pkce_start_idx, -1)
        self.assertNotEqual(pkce_end_idx, -1)

        constants_code = html[start_idx:html.find("const loginCard =")].strip()
        pkce_code = html[pkce_start_idx:pkce_end_idx].strip()

        test_js = f"""
const crypto = require("crypto");
{constants_code}

const storage = new Map();
const sessionStorage = {{
    getItem: (k) => (storage.has(k) ? storage.get(k) : null),
    setItem: (k, v) => storage.set(k, String(v)),
    removeItem: (k) => storage.delete(k)
}};

let loginStatus = {{ textContent: "" }};
let googleSignInButton = {{ disabled: false }};
let savedSessions = [];
let assistantShown = false;
let loginShown = false;
let replacedUrl = null;

function saveSession(data) {{ savedSessions.push(data); }}
function clearSession() {{}}
function showAssistant() {{ assistantShown = true; }}
function showLogin() {{ loginShown = true; }}

global.window = {{
    crypto: crypto.webcrypto,
    location: {{
        origin: "https://hayder.xorwia.com",
        pathname: "/voice",
        search: "",
        href: "https://hayder.xorwia.com/voice"
    }},
    history: {{
        replaceState: (_state, _title, url) => {{ replacedUrl = url; }}
    }}
}};
global.TextEncoder = TextEncoder;
global.btoa = (str) => Buffer.from(str, "binary").toString("base64");

{pkce_code}

async function run() {{
    // 1. Test startGoogleSignIn generates PKCE S256 challenge & state
    await startGoogleSignIn();
    const verifier = sessionStorage.getItem("hayder_pkce_verifier");
    const state = sessionStorage.getItem("hayder_oauth_state");
    if (!verifier || verifier.length < 40) throw new Error("Missing or short PKCE verifier");
    if (!state || state.length < 20) throw new Error("Missing or short OAuth state");

    const redirectUrl = new URL(window.location.href);
    if (redirectUrl.origin + redirectUrl.pathname !== "https://hayder-auth.auth.eu-west-2.amazoncognito.com/oauth2/authorize") {{
        throw new Error("Unexpected authorize endpoint: " + window.location.href);
    }}
    if (redirectUrl.searchParams.get("identity_provider") !== "Google") throw new Error("Missing Google provider");
    if (redirectUrl.searchParams.get("response_type") !== "code") throw new Error("Missing code response_type");
    if (redirectUrl.searchParams.get("client_id") !== "1t0bidostmftdun12kjih0udj5") throw new Error("Wrong client_id");
    if (redirectUrl.searchParams.get("redirect_uri") !== "https://hayder.xorwia.com/voice") throw new Error("Wrong redirect_uri");
    if (redirectUrl.searchParams.get("code_challenge_method") !== "S256") throw new Error("Wrong challenge method");
    if (redirectUrl.searchParams.get("state") !== state) throw new Error("State mismatch in redirect URL");

    const expectedChallenge = crypto.createHash("sha256").update(verifier).digest("base64url");
    if (redirectUrl.searchParams.get("code_challenge") !== expectedChallenge) {{
        throw new Error("PKCE S256 challenge mismatch");
    }}

    // 2. Test handleGoogleSignInCallback exchanges code + code_verifier for tokens
    window.location.search = "?code=auth-code-123&state=" + encodeURIComponent(state);
    let tokenRequest = null;
    global.fetch = async (url, opts) => {{
        tokenRequest = {{ url, opts }};
        return {{
            ok: true,
            status: 200,
            json: async () => ({{
                id_token: "cognito-id-jwt",
                refresh_token: "cognito-refresh-jwt",
                expires_in: 3600
            }})
        }};
    }};

    const handled = await handleGoogleSignInCallback();
    if (!handled) throw new Error("Callback was not handled");
    if (replacedUrl !== "/voice") throw new Error("URL query was not cleaned via replaceState");
    if (!tokenRequest || tokenRequest.url !== "https://hayder-auth.auth.eu-west-2.amazoncognito.com/oauth2/token") {{
        throw new Error("Unexpected token URL");
    }}
    const sentParams = new URLSearchParams(tokenRequest.opts.body);
    if (sentParams.get("grant_type") !== "authorization_code") throw new Error("Wrong grant_type");
    if (sentParams.get("code") !== "auth-code-123") throw new Error("Wrong code");
    if (sentParams.get("code_verifier") !== verifier) throw new Error("Wrong code_verifier");
    if (sentParams.get("redirect_uri") !== "https://hayder.xorwia.com/voice") throw new Error("Wrong redirect_uri in token exchange");
    if (savedSessions.length !== 1 || savedSessions[0].id_token !== "cognito-id-jwt") {{
        throw new Error("Session was not saved");
    }}
    if (!assistantShown) throw new Error("Assistant card was not shown");
    if (sessionStorage.getItem("hayder_pkce_verifier") !== null) throw new Error("Verifier not cleared after exchange");

    // 3. Test state mismatch rejection
    sessionStorage.setItem("hayder_pkce_verifier", "v2");
    sessionStorage.setItem("hayder_oauth_state", "expected-state");
    window.location.search = "?code=auth-code-456&state=wrong-state";
    loginShown = false;
    await handleGoogleSignInCallback();
    if (!loginShown || !loginStatus.textContent.includes("invalid OAuth state")) {{
        throw new Error("State mismatch was not rejected: " + loginStatus.textContent);
    }}
    // 4. Test OAuth error query parameter handling
    window.location.search = "?error=access_denied&error_description=User+cancelled";
    loginShown = false;
    await handleGoogleSignInCallback();
    if (!loginShown || !loginStatus.textContent.includes("User cancelled")) {{
        throw new Error("OAuth error parameter was not surfaced: " + loginStatus.textContent);
    }}
}}

run().then(() => console.log("PKCE_OK")).catch((err) => {{
    console.error(err);
    process.exit(1);
}});
"""
        proc = subprocess.run([node_path, "-e", test_js], capture_output=True, text=True)
        self.assertEqual(proc.returncode, 0, msg=f"PKCE JS test failed:\nstdout: {proc.stdout}\nstderr: {proc.stderr}")
        self.assertIn("PKCE_OK", proc.stdout)


if __name__ == "__main__":
    unittest.main()
