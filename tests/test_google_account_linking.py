"""
Focused security and regression tests for:
1. Secure fail-closed Cognito PreSignUp Google account linking (same-email and
   explicitly opted-in cross-email founder linking).
2. Prevention of silent Cognito AttributeMapping email overwrite unless
   explicitly opted in.
3. Founder HAYDER_PRO entitlement preservation (hayder:<native_sub>).
4. Preservation of email-keyed Hayder memory, approvals, and Gmail OAuth
   records when the founder's JWT email claim changes after cross-email Google login.
"""

import json
import os
import sys
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock, Mock, patch

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
sys.path.insert(0, str(SRC))

os.environ.setdefault("HAYDER_TABLE", "test-memory")
os.environ.setdefault("HAYDER_APPROVAL_TABLE", "test-approvals")
os.environ.setdefault("AWS_LAMBDA_FUNCTION_NAME", "test-function")


class _FakeUserNotFoundException(Exception):
    pass


class _FakeBoto3:
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
            exceptions=SimpleNamespace(
                UserNotFoundException=_FakeUserNotFoundException
            ),
        )


sys.modules.setdefault("boto3", _FakeBoto3())

import app
import pre_signup


FOUNDER_NATIVE_EMAIL = "founder-native@example.com"
FOUNDER_GOOGLE_EMAIL = "founder-google@example.com"
FOUNDER_GOOGLE_SUB = "109876543210987654321"
FOUNDER_NATIVE_USERNAME = "founder-native-uuid-001"
FOUNDER_NATIVE_SUB = "founder-native-sub-001"
POOL_ID = "eu-west-2_HayderTestPool"

SAME_EMAIL_FOUNDER_ENV = {
    "FOUNDER_GOOGLE_SUBJECT": FOUNDER_GOOGLE_SUB,
    "FOUNDER_GOOGLE_EMAIL": FOUNDER_NATIVE_EMAIL,
    "FOUNDER_NATIVE_USERNAME": FOUNDER_NATIVE_USERNAME,
    "FOUNDER_NATIVE_SUB": FOUNDER_NATIVE_SUB,
    "FOUNDER_NATIVE_EMAIL": FOUNDER_NATIVE_EMAIL,
    "ALLOW_FOUNDER_CROSS_EMAIL_LINK": "false",
}

CROSS_EMAIL_FOUNDER_ENV_DEFAULT = {
    "FOUNDER_GOOGLE_SUBJECT": FOUNDER_GOOGLE_SUB,
    "FOUNDER_GOOGLE_EMAIL": FOUNDER_GOOGLE_EMAIL,
    "FOUNDER_NATIVE_USERNAME": FOUNDER_NATIVE_USERNAME,
    "FOUNDER_NATIVE_SUB": FOUNDER_NATIVE_SUB,
    "FOUNDER_NATIVE_EMAIL": FOUNDER_NATIVE_EMAIL,
    "ALLOW_FOUNDER_CROSS_EMAIL_LINK": "false",
}

CROSS_EMAIL_FOUNDER_ENV_ALLOWED = {
    **CROSS_EMAIL_FOUNDER_ENV_DEFAULT,
    "ALLOW_FOUNDER_CROSS_EMAIL_LINK": "true",
}


def _make_pre_signup_event(
    *,
    trigger_source="PreSignUp_ExternalProvider",
    username=f"google_{FOUNDER_GOOGLE_SUB}",
    email=FOUNDER_NATIVE_EMAIL,
    email_verified="true",
    user_pool_id=POOL_ID,
):
    attrs = {}
    if email is not None:
        attrs["email"] = email
    if email_verified is not None:
        attrs["email_verified"] = email_verified
    return {
        "version": "1",
        "region": "eu-west-2",
        "userPoolId": user_pool_id,
        "userName": username,
        "triggerSource": trigger_source,
        "request": {"userAttributes": attrs},
        "response": {
            "autoConfirmUser": False,
            "autoVerifyEmail": False,
            "autoVerifyPhone": False,
        },
    }


def _make_cognito_user(
    *,
    username=FOUNDER_NATIVE_USERNAME,
    sub=FOUNDER_NATIVE_SUB,
    email=FOUNDER_NATIVE_EMAIL,
    email_verified="true",
    status="CONFIRMED",
    enabled=True,
    identities=None,
    use_admin_attr_key=False,
):
    attrs = [
        {"Name": "sub", "Value": sub},
        {"Name": "email", "Value": email},
        {"Name": "email_verified", "Value": email_verified},
    ]
    if identities is not None:
        attrs.append(
            {
                "Name": "identities",
                "Value": identities
                if isinstance(identities, str)
                else json.dumps(identities),
            }
        )
    key = "UserAttributes" if use_admin_attr_key else "Attributes"
    return {
        "Username": username,
        "UserStatus": status,
        "Enabled": enabled,
        key: attrs,
    }


def _make_cognito_mock(users_by_username=None, users_by_email=None, list_users_result=None):
    users_by_username = users_by_username or {}
    users_by_email = users_by_email or {}
    default_list = list_users_result or []

    client = MagicMock()
    client.exceptions = SimpleNamespace(
        UserNotFoundException=_FakeUserNotFoundException
    )

    def _admin_get_user(UserPoolId, Username):
        if Username in users_by_username:
            return users_by_username[Username]
        raise _FakeUserNotFoundException(f"User {Username} not found")

    def _list_users(UserPoolId, Filter="", PaginationToken=None):
        if users_by_email:
            for email_key, users in users_by_email.items():
                if Filter == f'email = "{email_key}"':
                    return {"Users": users}
            return {"Users": []}
        return {"Users": default_list}

    client.admin_get_user.side_effect = _admin_get_user
    client.list_users.side_effect = _list_users
    client.admin_link_provider_for_user.return_value = {}
    return client


class SecureGoogleAccountLinkingTests(unittest.TestCase):
    def test_founder_same_email_allowlisted_google_links_and_preserves_entitlement(self):
        native_list_record = _make_cognito_user()
        native_admin_record = _make_cognito_user(use_admin_attr_key=True)
        client = _make_cognito_mock(
            users_by_username={FOUNDER_NATIVE_USERNAME: native_admin_record},
            list_users_result=[native_list_record],
        )
        event = _make_pre_signup_event(email=FOUNDER_NATIVE_EMAIL)

        result = pre_signup.handle_pre_signup(
            event,
            cognito_client=client,
            env=SAME_EMAIL_FOUNDER_ENV,
        )

        self.assertIs(result, event)
        client.admin_link_provider_for_user.assert_called_once_with(
            UserPoolId=POOL_ID,
            DestinationUser={
                "ProviderName": "Cognito",
                "ProviderAttributeValue": FOUNDER_NATIVE_USERNAME,
            },
            SourceUser={
                "ProviderName": "Google",
                "ProviderAttributeName": "Cognito_Subject",
                "ProviderAttributeValue": FOUNDER_GOOGLE_SUB,
            },
        )

    def test_cross_email_founder_linking_fails_closed_by_default_preventing_silent_overwrite(self):
        """
        Cross-email founder linking MUST fail closed unless explicitly opted in,
        preventing silent Cognito AttributeMapping overwrite of the native email.
        """
        native_list_record = _make_cognito_user(email=FOUNDER_NATIVE_EMAIL)
        native_admin_record = _make_cognito_user(
            email=FOUNDER_NATIVE_EMAIL,
            use_admin_attr_key=True,
        )
        client = _make_cognito_mock(
            users_by_username={FOUNDER_NATIVE_USERNAME: native_admin_record},
            users_by_email={
                FOUNDER_NATIVE_EMAIL: [native_list_record],
                FOUNDER_GOOGLE_EMAIL: [],
            },
        )
        event = _make_pre_signup_event(email=FOUNDER_GOOGLE_EMAIL)

        with self.assertRaises(pre_signup.AccountLinkingError) as ctx:
            pre_signup.handle_pre_signup(
                event,
                cognito_client=client,
                env=CROSS_EMAIL_FOUNDER_ENV_DEFAULT,
            )

        self.assertIn("cross-email", str(ctx.exception).lower())
        client.admin_link_provider_for_user.assert_not_called()

    def test_cross_email_founder_linking_succeeds_only_with_explicit_opt_in_and_allowlist(self):
        """
        With explicit opt-in + exact allowlisted Google sub, Google email, native
        username, native sub, and native email, links Google to native user while
        preserving native sub, HAYDER_PRO entitlement, and email-keyed Hayder records.
        """
        native_list_record = _make_cognito_user(email=FOUNDER_NATIVE_EMAIL)
        native_admin_record = _make_cognito_user(
            email=FOUNDER_NATIVE_EMAIL,
            use_admin_attr_key=True,
        )
        client = _make_cognito_mock(
            users_by_username={FOUNDER_NATIVE_USERNAME: native_admin_record},
            users_by_email={
                FOUNDER_NATIVE_EMAIL: [native_list_record],
                FOUNDER_GOOGLE_EMAIL: [],
            },
        )
        event = _make_pre_signup_event(email=FOUNDER_GOOGLE_EMAIL)

        result = pre_signup.handle_pre_signup(
            event,
            cognito_client=client,
            env=CROSS_EMAIL_FOUNDER_ENV_ALLOWED,
        )

        self.assertIs(result, event)
        client.admin_link_provider_for_user.assert_called_once_with(
            UserPoolId=POOL_ID,
            DestinationUser={
                "ProviderName": "Cognito",
                "ProviderAttributeValue": FOUNDER_NATIVE_USERNAME,
            },
            SourceUser={
                "ProviderName": "Google",
                "ProviderAttributeName": "Cognito_Subject",
                "ProviderAttributeValue": FOUNDER_GOOGLE_SUB,
            },
        )

    def test_cross_email_founder_wrong_google_email_fails_closed(self):
        native_admin_record = _make_cognito_user(
            email=FOUNDER_NATIVE_EMAIL,
            use_admin_attr_key=True,
        )
        client = _make_cognito_mock(
            users_by_username={FOUNDER_NATIVE_USERNAME: native_admin_record},
            users_by_email={FOUNDER_NATIVE_EMAIL: [_make_cognito_user()]},
        )
        event = _make_pre_signup_event(
            username=f"google_{FOUNDER_GOOGLE_SUB}",
            email="unexpected-other@example.com",
        )

        with self.assertRaises(pre_signup.AccountLinkingError):
            pre_signup.handle_pre_signup(
                event,
                cognito_client=client,
                env=CROSS_EMAIL_FOUNDER_ENV_ALLOWED,
            )
        client.admin_link_provider_for_user.assert_not_called()

    def test_cross_email_founder_colliding_native_user_on_google_email_fails_closed(self):
        other_native = _make_cognito_user(
            username="other-native-uuid",
            sub="other-native-sub",
            email=FOUNDER_GOOGLE_EMAIL,
        )
        client = _make_cognito_mock(
            users_by_username={
                FOUNDER_NATIVE_USERNAME: _make_cognito_user(use_admin_attr_key=True)
            },
            users_by_email={
                FOUNDER_GOOGLE_EMAIL: [other_native],
                FOUNDER_NATIVE_EMAIL: [_make_cognito_user()],
            },
        )
        event = _make_pre_signup_event(email=FOUNDER_GOOGLE_EMAIL)

        with self.assertRaises(pre_signup.AccountLinkingError):
            pre_signup.handle_pre_signup(
                event,
                cognito_client=client,
                env=CROSS_EMAIL_FOUNDER_ENV_ALLOWED,
            )
        client.admin_link_provider_for_user.assert_not_called()

    def test_cross_email_founder_existing_federated_user_on_native_email_fails_closed(self):
        existing_fed_native = _make_cognito_user(
            username="google_old123",
            sub="old-fed-sub",
            email=FOUNDER_NATIVE_EMAIL,
            status="EXTERNAL_PROVIDER",
        )
        client = _make_cognito_mock(
            users_by_username={
                FOUNDER_NATIVE_USERNAME: _make_cognito_user(use_admin_attr_key=True)
            },
            users_by_email={
                FOUNDER_GOOGLE_EMAIL: [],
                FOUNDER_NATIVE_EMAIL: [_make_cognito_user(), existing_fed_native],
            },
        )
        event = _make_pre_signup_event(email=FOUNDER_GOOGLE_EMAIL)

        with self.assertRaises(pre_signup.AccountLinkingError):
            pre_signup.handle_pre_signup(
                event,
                cognito_client=client,
                env=CROSS_EMAIL_FOUNDER_ENV_ALLOWED,
            )
        client.admin_link_provider_for_user.assert_not_called()

    def test_post_cross_email_jwt_preserves_entitlement_memory_approvals_and_gmail_secret_key(self):
        """
        Even if Cognito's Google AttributeMapping sets JWT claims.email to the
        founder's Google email, Hayder preserves:
          - external_user_id = hayder:<FOUNDER_NATIVE_SUB> (HAYDER_PRO entitlement)
          - canonical user_id = FOUNDER_NATIVE_EMAIL for memory, approvals & Gmail OAuth secret
        """
        post_link_jwt_claims = {
            "sub": FOUNDER_NATIVE_SUB,
            "email": FOUNDER_GOOGLE_EMAIL,
            "identities": json.dumps(
                [{"providerName": "Google", "userId": FOUNDER_GOOGLE_SUB}]
            ),
        }

        def _auth_event(method, path, body=None):
            ev = {
                "rawPath": path,
                "requestContext": {
                    "http": {"method": method},
                    "authorizer": {"jwt": {"claims": post_link_jwt_claims}},
                },
            }
            if body is not None:
                ev["body"] = json.dumps(body)
            return ev

        with patch.dict(
            os.environ,
            {
                "FOUNDER_NATIVE_SUB": FOUNDER_NATIVE_SUB,
                "FOUNDER_NATIVE_EMAIL": FOUNDER_NATIVE_EMAIL,
            },
        ):
            # 1. Canonical user_id stays pinned to FOUNDER_NATIVE_EMAIL
            chat_event = _auth_event("POST", "/chat", {"message": "Good morning"})
            resolved_user_id = app.get_authenticated_user(chat_event)
            self.assertEqual(resolved_user_id, FOUNDER_NATIVE_EMAIL)

            # 2. Gmail OAuth Secrets Manager key matches the original native email hash
            self.assertEqual(
                app.google_user_secret_name(resolved_user_id),
                app.google_user_secret_name(FOUNDER_NATIVE_EMAIL),
            )
            self.assertNotEqual(
                app.google_user_secret_name(resolved_user_id),
                app.google_user_secret_name(FOUNDER_GOOGLE_EMAIL),
            )

            # 3. Xorwia HAYDER_PRO entitlement lookup uses native sub & passes /chat
            self.assertEqual(
                app.get_external_user_id(chat_event),
                f"hayder:{FOUNDER_NATIVE_SUB}",
            )
            with patch.object(
                app, "check_hayder_pro", return_value=True
            ) as mock_entitlement, patch.object(
                app,
                "chat",
                return_value=app.response(200, {"assistant": "Hayder", "reply": "Ready"}),
            ) as mock_chat:
                chat_res = app.lambda_handler(chat_event, None)
            self.assertEqual(chat_res["statusCode"], 200)
            mock_entitlement.assert_called_once_with(f"hayder:{FOUNDER_NATIVE_SUB}")
            mock_chat.assert_called_once_with(
                FOUNDER_NATIVE_EMAIL,
                {"message": "Good morning"},
                event=chat_event,
            )

            # 4. Memory route receives canonical FOUNDER_NATIVE_EMAIL partition key
            mem_event = _auth_event("POST", "/memory/project", {"project": "xorwia"})
            with patch.object(
                app,
                "save_checkpoint",
                return_value=app.response(200, {"saved": True}),
            ) as mock_mem:
                mem_res = app.lambda_handler(mem_event, None)
            self.assertEqual(mem_res["statusCode"], 200)
            mock_mem.assert_called_once_with({"project": "xorwia"}, FOUNDER_NATIVE_EMAIL)

            # 5. Approval route receives canonical FOUNDER_NATIVE_EMAIL partition key
            appr_event = _auth_event("POST", "/approval/create", {"action": "test"})
            with patch.object(
                app,
                "create_approval",
                return_value=app.response(200, {"approval_id": "a1"}),
            ) as mock_appr:
                appr_res = app.lambda_handler(appr_event, None)
            self.assertEqual(appr_res["statusCode"], 200)
            mock_appr.assert_called_once_with(FOUNDER_NATIVE_EMAIL, {"action": "test"})

            # 6. Ordinary non-founder customer still uses their own claims.email
            customer_event = {
                "rawPath": "/chat",
                "requestContext": {
                    "http": {"method": "POST"},
                    "authorizer": {
                        "jwt": {
                            "claims": {
                                "sub": "customer-sub-999",
                                "email": "customer@example.com",
                            }
                        }
                    },
                },
            }
            self.assertEqual(
                app.get_authenticated_user(customer_event),
                "customer@example.com",
            )

    def test_founder_canonical_storage_pin_fails_closed_if_native_email_missing(self):
        founder_event = {
            "rawPath": "/memory/project",
            "requestContext": {
                "http": {"method": "POST"},
                "authorizer": {
                    "jwt": {
                        "claims": {
                            "sub": FOUNDER_NATIVE_SUB,
                            "email": FOUNDER_GOOGLE_EMAIL,
                        }
                    }
                },
            },
            "body": json.dumps({"project": "xorwia"}),
        }
        with patch.dict(
            os.environ,
            {
                "FOUNDER_NATIVE_SUB": FOUNDER_NATIVE_SUB,
                "FOUNDER_NATIVE_EMAIL": "",
            },
        ):
            self.assertIsNone(app.get_authenticated_user(founder_event))
            res = app.lambda_handler(founder_event, None)
        self.assertEqual(res["statusCode"], 401)

    def test_founder_email_match_with_wrong_google_subject_fails_closed(self):
        native_list_record = _make_cognito_user()
        client = _make_cognito_mock(list_users_result=[native_list_record])
        event = _make_pre_signup_event(
            username="google_999999999999999999999",
            email=FOUNDER_NATIVE_EMAIL,
            email_verified="true",
        )

        with self.assertRaises(pre_signup.AccountLinkingError):
            pre_signup.handle_pre_signup(
                event,
                cognito_client=client,
                env=SAME_EMAIL_FOUNDER_ENV,
            )

        client.admin_link_provider_for_user.assert_not_called()

    def test_unlisted_existing_native_user_email_match_fails_closed(self):
        other_native = _make_cognito_user(
            username="native-bob-001",
            sub="native-bob-sub-001",
            email="bob@example.com",
        )
        client = _make_cognito_mock(list_users_result=[other_native])
        event = _make_pre_signup_event(
            username="google_777777777777777777777",
            email="bob@example.com",
            email_verified="true",
        )

        with self.assertRaises(pre_signup.AccountLinkingError):
            pre_signup.handle_pre_signup(
                event,
                cognito_client=client,
                env=CROSS_EMAIL_FOUNDER_ENV_ALLOWED,
            )

        client.admin_link_provider_for_user.assert_not_called()

    def test_normal_new_customer_google_signup_preserved(self):
        client = _make_cognito_mock(list_users_result=[])
        event = _make_pre_signup_event(
            username="google_555555555555555555555",
            email="new.customer@gmail.com",
            email_verified="true",
        )

        result = pre_signup.handle_pre_signup(
            event,
            cognito_client=client,
            env=CROSS_EMAIL_FOUNDER_ENV_ALLOWED,
        )

        self.assertIs(result, event)
        client.admin_link_provider_for_user.assert_not_called()

    def test_unverified_google_email_fails_closed(self):
        client = _make_cognito_mock(list_users_result=[])
        for bad_verified in ("false", "", None):
            event = _make_pre_signup_event(
                username=f"google_{FOUNDER_GOOGLE_SUB}",
                email=FOUNDER_GOOGLE_EMAIL,
                email_verified=bad_verified,
            )
            with self.assertRaises(pre_signup.AccountLinkingError):
                pre_signup.handle_pre_signup(
                    event,
                    cognito_client=client,
                    env=CROSS_EMAIL_FOUNDER_ENV_ALLOWED,
                )
        client.admin_link_provider_for_user.assert_not_called()

    def test_unsupported_external_provider_fails_closed(self):
        client = _make_cognito_mock(list_users_result=[])
        for bad_username in ("facebook_12345", "apple_12345", "malformed", "google_"):
            event = _make_pre_signup_event(
                username=bad_username,
                email="user@example.com",
                email_verified="true",
            )
            with self.assertRaises(pre_signup.AccountLinkingError):
                pre_signup.handle_pre_signup(
                    event,
                    cognito_client=client,
                    env=CROSS_EMAIL_FOUNDER_ENV_ALLOWED,
                )
        client.admin_link_provider_for_user.assert_not_called()

    def test_unconfirmed_or_disabled_or_unverified_native_account_fails_closed(self):
        bad_native_variants = [
            {"status": "UNCONFIRMED"},
            {"status": "FORCE_CHANGE_PASSWORD"},
            {"enabled": False},
            {"email_verified": "false"},
            {"sub": "wrong-native-sub-999"},
            {"email": "other@example.com"},
        ]
        for overrides in bad_native_variants:
            list_user = _make_cognito_user(**overrides)
            admin_user = _make_cognito_user(use_admin_attr_key=True, **overrides)
            client = _make_cognito_mock(
                users_by_username={FOUNDER_NATIVE_USERNAME: admin_user},
                users_by_email={
                    FOUNDER_GOOGLE_EMAIL: [],
                    FOUNDER_NATIVE_EMAIL: [list_user],
                },
            )
            event = _make_pre_signup_event(email=FOUNDER_GOOGLE_EMAIL)
            with self.assertRaises(pre_signup.AccountLinkingError):
                pre_signup.handle_pre_signup(
                    event,
                    cognito_client=client,
                    env=CROSS_EMAIL_FOUNDER_ENV_ALLOWED,
                )
            client.admin_link_provider_for_user.assert_not_called()

    def test_ambiguous_multiple_native_users_for_email_fails_closed(self):
        user_a = _make_cognito_user(username=FOUNDER_NATIVE_USERNAME, sub=FOUNDER_NATIVE_SUB)
        user_b = _make_cognito_user(username="duplicate-native-002", sub="dup-sub-002")
        client = _make_cognito_mock(list_users_result=[user_a, user_b])
        event = _make_pre_signup_event(email=FOUNDER_NATIVE_EMAIL)

        with self.assertRaises(pre_signup.AccountLinkingError):
            pre_signup.handle_pre_signup(
                event,
                cognito_client=client,
                env=SAME_EMAIL_FOUNDER_ENV,
            )
        client.admin_link_provider_for_user.assert_not_called()

    def test_existing_federated_user_by_username_fails_closed(self):
        existing_fed = _make_cognito_user(
            username=f"google_{FOUNDER_GOOGLE_SUB}",
            sub="old-split-google-sub",
            email=FOUNDER_GOOGLE_EMAIL,
            status="EXTERNAL_PROVIDER",
            use_admin_attr_key=True,
        )
        client = _make_cognito_mock(
            users_by_username={f"google_{FOUNDER_GOOGLE_SUB}": existing_fed},
            users_by_email={
                FOUNDER_GOOGLE_EMAIL: [],
                FOUNDER_NATIVE_EMAIL: [_make_cognito_user()],
            },
        )
        event = _make_pre_signup_event(email=FOUNDER_GOOGLE_EMAIL)

        with self.assertRaises(pre_signup.AccountLinkingError):
            pre_signup.handle_pre_signup(
                event,
                cognito_client=client,
                env=CROSS_EMAIL_FOUNDER_ENV_ALLOWED,
            )
        client.admin_link_provider_for_user.assert_not_called()

    def test_native_user_already_linked_to_different_google_subject_fails_closed(self):
        identities = [{"providerName": "Google", "userId": "different-google-sub"}]
        native_list = _make_cognito_user(identities=identities)
        native_admin = _make_cognito_user(identities=identities, use_admin_attr_key=True)
        client = _make_cognito_mock(
            users_by_username={FOUNDER_NATIVE_USERNAME: native_admin},
            users_by_email={
                FOUNDER_GOOGLE_EMAIL: [],
                FOUNDER_NATIVE_EMAIL: [native_list],
            },
        )
        event = _make_pre_signup_event(email=FOUNDER_GOOGLE_EMAIL)

        with self.assertRaises(pre_signup.AccountLinkingError):
            pre_signup.handle_pre_signup(
                event,
                cognito_client=client,
                env=CROSS_EMAIL_FOUNDER_ENV_ALLOWED,
            )
        client.admin_link_provider_for_user.assert_not_called()

    def test_native_user_already_linked_to_same_allowlisted_google_subject_is_idempotent(self):
        identities = [{"providerName": "Google", "userId": FOUNDER_GOOGLE_SUB}]
        native_list = _make_cognito_user(identities=identities)
        native_admin = _make_cognito_user(identities=identities, use_admin_attr_key=True)
        client = _make_cognito_mock(
            users_by_username={FOUNDER_NATIVE_USERNAME: native_admin},
            users_by_email={
                FOUNDER_GOOGLE_EMAIL: [],
                FOUNDER_NATIVE_EMAIL: [native_list],
            },
        )
        event = _make_pre_signup_event(email=FOUNDER_GOOGLE_EMAIL)

        result = pre_signup.handle_pre_signup(
            event,
            cognito_client=client,
            env=CROSS_EMAIL_FOUNDER_ENV_ALLOWED,
        )
        self.assertIs(result, event)
        client.admin_link_provider_for_user.assert_not_called()

    def test_partial_founder_allowlist_configuration_fails_closed(self):
        client = _make_cognito_mock(list_users_result=[_make_cognito_user()])
        event = _make_pre_signup_event(email=FOUNDER_GOOGLE_EMAIL)
        partial_env = {
            **CROSS_EMAIL_FOUNDER_ENV_ALLOWED,
            "FOUNDER_GOOGLE_EMAIL": "",
        }
        with self.assertRaises(pre_signup.AccountLinkingError):
            pre_signup.handle_pre_signup(
                event,
                cognito_client=client,
                env=partial_env,
            )
        client.admin_link_provider_for_user.assert_not_called()

    def test_native_signup_trigger_passes_through_unchanged(self):
        client = _make_cognito_mock()
        event = _make_pre_signup_event(
            trigger_source="PreSignUp_SignUp",
            username="alice@example.com",
            email="alice@example.com",
            email_verified=None,
        )

        result = pre_signup.handle_pre_signup(
            event,
            cognito_client=client,
            env=CROSS_EMAIL_FOUNDER_ENV_ALLOWED,
        )
        self.assertIs(result, event)
        client.list_users.assert_not_called()
        client.admin_get_user.assert_not_called()
        client.admin_link_provider_for_user.assert_not_called()

    def test_template_iam_is_least_privilege_and_cross_email_defaults_closed(self):
        template_text = (ROOT / "template.yaml").read_text(encoding="utf-8")

        self.assertIn("AllowFounderCrossEmailLink:", template_text)
        self.assertIn('Default: "false"', template_text)
        self.assertIn("FOUNDER_NATIVE_SUB: !Ref FounderNativeSub", template_text)
        self.assertIn("FOUNDER_NATIVE_EMAIL: !Ref FounderNativeEmail", template_text)

        policy_start = template_text.index("HayderPreSignUpCognitoPolicy:")
        policy_end = template_text.index("HayderPreSignUpInvokePermission:")
        policy_block = template_text[policy_start:policy_end]

        self.assertIn("- cognito-idp:ListUsers", policy_block)
        self.assertIn("- cognito-idp:AdminGetUser", policy_block)
        self.assertIn("- cognito-idp:AdminLinkProviderForUser", policy_block)
        self.assertIn("Resource: !GetAtt HayderUserPool.Arn", policy_block)
        self.assertNotIn("AdminUpdateUserAttributes", policy_block)
        self.assertNotIn("AdminDeleteUser", policy_block)
        self.assertNotIn("cognito-idp:*", policy_block)


if __name__ == "__main__":
    unittest.main()
