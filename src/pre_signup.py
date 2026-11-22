"""
Cognito PreSignUp trigger for secure, fail-closed Google account linking.

Design invariants:
1. Only acts on triggerSource == "PreSignUp_ExternalProvider"; native signups
   (PreSignUp_SignUp / PreSignUp_AdminCreateUser) pass through unchanged.
2. Only supports Google federation with a strictly verified email
   (email_verified == "true"). Unsupported providers and unverified identities
   fail closed.
3. Never links ordinary customers on email match alone. Linking an external
   Google identity to an existing native Cognito user requires an explicit
   allowlisted mapping from the trusted Google provider subject and expected
   Google email to the known CONFIRMED native Cognito user (username, sub, and
   verified native email).
4. Prevents silent cross-email overwrite: because Cognito's Google IdP
   AttributeMapping (required by UsernameAttributes=[email]) maps Google's
   email onto the linked Cognito user on sign-in, cross-email founder linking
   (FOUNDER_GOOGLE_EMAIL != FOUNDER_NATIVE_EMAIL) FAILS CLOSED unless
   ALLOW_FOUNDER_CROSS_EMAIL_LINK="true" is explicitly enabled.
5. Inspects existing federated and native identities across both emails (and
   external username) before assuming first-sign-in linking will work; fails
   closed on any conflict or ambiguity.
6. Preserves normal new-customer Google signups when the Google identity is
   verified and no existing native or federated Cognito account exists.
"""

import hmac
import json
import os
import re

import boto3


SUPPORTED_PROVIDER_PREFIX = "google"
SUPPORTED_PROVIDER_NAME = "Google"
EMAIL_PATTERN = re.compile(r"^[^@\s\"\\]+@[^@\s\"\\]+\.[^@\s\"\\]+$")
MAX_LIST_USERS_PAGES = 10


class AccountLinkingError(Exception):
    """Fail-closed error returned to Cognito to block unsafe sign-in/linking."""


def _get_cognito_client(client=None):
    if client is not None:
        return client
    return boto3.client("cognito-idp")


def _extract_attributes(user_record):
    raw_attrs = (
        user_record.get("UserAttributes")
        if "UserAttributes" in user_record
        else user_record.get("Attributes")
    ) or []
    result = {}
    for item in raw_attrs:
        name = item.get("Name")
        if name:
            result[name] = item.get("Value")
    return result


def _is_strictly_true(value):
    if isinstance(value, bool):
        return value is True
    if isinstance(value, str):
        return value.strip().lower() == "true"
    return False


def _normalize_email(raw_email):
    if not isinstance(raw_email, str):
        return None
    cleaned = raw_email.strip().lower()
    if not cleaned or not EMAIL_PATTERN.match(cleaned):
        return None
    return cleaned


def _is_placeholder(value):
    if not isinstance(value, str):
        return True
    cleaned = value.strip()
    if not cleaned:
        return True
    return "PLACEHOLDER" in cleaned.upper()


def _parse_external_username(username):
    """
    Parse Cognito PreSignUp_ExternalProvider userName (<provider>_<provider_sub>).
    Only Google is supported; anything else fails closed.
    """
    if not isinstance(username, str) or "_" not in username:
        raise AccountLinkingError(
            "Unsupported or malformed external identity provider username."
        )

    raw_provider, provider_user_id = username.split("_", 1)
    if raw_provider.strip().lower() != SUPPORTED_PROVIDER_PREFIX:
        raise AccountLinkingError(
            f"Unsupported external identity provider: {raw_provider or 'unknown'}."
        )

    cleaned_sub = provider_user_id.strip()
    if not cleaned_sub or any(ch.isspace() for ch in cleaned_sub):
        raise AccountLinkingError("Missing or invalid Google provider subject.")

    return SUPPORTED_PROVIDER_NAME, cleaned_sub


def load_founder_allowlist(env=None):
    """
    Load the explicit founder Google-subject -> native Cognito user mapping.

    Requires all five identity fields when configured:
      - FOUNDER_GOOGLE_SUBJECT
      - FOUNDER_GOOGLE_EMAIL
      - FOUNDER_NATIVE_USERNAME
      - FOUNDER_NATIVE_SUB
      - FOUNDER_NATIVE_EMAIL
    Partial or malformed configuration fails closed.
    Returns None if all five fields are unset/placeholder.
    """
    source = os.environ if env is None else env
    raw_google_sub = (source.get("FOUNDER_GOOGLE_SUBJECT") or "").strip()
    raw_google_email = (source.get("FOUNDER_GOOGLE_EMAIL") or "").strip()
    raw_native_username = (source.get("FOUNDER_NATIVE_USERNAME") or "").strip()
    raw_native_sub = (source.get("FOUNDER_NATIVE_SUB") or "").strip()
    raw_native_email = (source.get("FOUNDER_NATIVE_EMAIL") or "").strip()

    configured_values = [
        raw_google_sub,
        raw_google_email,
        raw_native_username,
        raw_native_sub,
        raw_native_email,
    ]
    if all(_is_placeholder(v) for v in configured_values):
        return None

    if any(_is_placeholder(v) for v in configured_values):
        raise AccountLinkingError(
            "Incomplete founder account linking configuration; refusing to link."
        )

    google_email = _normalize_email(raw_google_email)
    native_email = _normalize_email(raw_native_email)
    if not google_email or not native_email:
        raise AccountLinkingError(
            "Invalid founder email configuration; refusing to link."
        )

    return {
        "google_subject": raw_google_sub,
        "google_email": google_email,
        "native_username": raw_native_username,
        "native_sub": raw_native_sub,
        "native_email": native_email,
        "is_cross_email": not hmac.compare_digest(google_email, native_email),
        "allow_cross_email": _is_strictly_true(
            source.get("ALLOW_FOUNDER_CROSS_EMAIL_LINK")
        ),
    }


def _is_user_not_found(exc, cognito_client):
    not_found_cls = getattr(
        getattr(cognito_client, "exceptions", None),
        "UserNotFoundException",
        None,
    )
    if not_found_cls and isinstance(exc, not_found_cls):
        return True
    response = getattr(exc, "response", None)
    if isinstance(response, dict):
        code = (response.get("Error") or {}).get("Code")
        if code == "UserNotFoundException":
            return True
    return False


def _admin_get_user_optional(cognito_client, user_pool_id, username):
    try:
        return cognito_client.admin_get_user(
            UserPoolId=user_pool_id,
            Username=username,
        )
    except Exception as exc:
        if _is_user_not_found(exc, cognito_client):
            return None
        raise


def _list_users_by_email(cognito_client, user_pool_id, normalized_email):
    matched = []
    pagination_token = None
    for _ in range(MAX_LIST_USERS_PAGES):
        kwargs = {
            "UserPoolId": user_pool_id,
            "Filter": f'email = "{normalized_email}"',
        }
        if pagination_token:
            kwargs["PaginationToken"] = pagination_token

        page = cognito_client.list_users(**kwargs)
        for user in page.get("Users") or []:
            attrs = _extract_attributes(user)
            user_email = _normalize_email(attrs.get("email"))
            if user_email == normalized_email:
                matched.append(user)

        pagination_token = page.get("PaginationToken")
        if not pagination_token:
            return matched

    raise AccountLinkingError(
        "Too many matching Cognito users for email; refusing ambiguous link."
    )


def _parse_user_identities(user_record):
    attrs = _extract_attributes(user_record)
    raw_identities = attrs.get("identities")
    if not raw_identities:
        return []
    try:
        parsed = json.loads(raw_identities)
    except (TypeError, ValueError) as exc:
        raise AccountLinkingError(
            "Malformed Cognito identities attribute on existing user."
        ) from exc
    if not isinstance(parsed, list):
        raise AccountLinkingError(
            "Unexpected Cognito identities structure on existing user."
        )
    return parsed


def _is_external_provider_user(user_record):
    if (user_record.get("UserStatus") or "").upper() == "EXTERNAL_PROVIDER":
        return True
    username = (user_record.get("Username") or "").lower()
    return username.startswith(f"{SUPPORTED_PROVIDER_PREFIX}_")


def _partition_email_matches(cognito_client, user_pool_id, normalized_email, provider_user_id):
    email_matches = _list_users_by_email(
        cognito_client,
        user_pool_id,
        normalized_email,
    )

    native_users = []
    federated_users = []
    for user in email_matches:
        if _is_external_provider_user(user):
            federated_users.append(user)
        else:
            native_users.append(user)

    linked_google_holders = []
    for user in native_users:
        for identity in _parse_user_identities(user):
            if not isinstance(identity, dict):
                raise AccountLinkingError("Malformed identity entry on native user.")
            if (
                str(identity.get("providerName") or "").lower()
                == SUPPORTED_PROVIDER_PREFIX
                and str(identity.get("userId") or "").strip() == provider_user_id
            ):
                linked_google_holders.append(user)

    return {
        "federated_users_for_email": federated_users,
        "native_users_for_email": native_users,
        "linked_google_holders": linked_google_holders,
    }


def inspect_existing_identities(
    cognito_client,
    user_pool_id,
    normalized_email,
    external_username,
    provider_user_id,
):
    """
    Inspect the Cognito User Pool for existing native and federated identities
    before deciding whether to allow new signup or perform explicit linking.
    """
    existing_federated_by_username = _admin_get_user_optional(
        cognito_client,
        user_pool_id,
        external_username,
    )

    partitioned = _partition_email_matches(
        cognito_client=cognito_client,
        user_pool_id=user_pool_id,
        normalized_email=normalized_email,
        provider_user_id=provider_user_id,
    )
    partitioned["existing_federated_by_username"] = existing_federated_by_username
    return partitioned


def _validate_target_native_user(
    target_user,
    expected_native_username,
    expected_native_sub,
    expected_native_email,
):
    if not target_user:
        raise AccountLinkingError(
            "Allowlisted native Cognito user was not found."
        )

    actual_username = (target_user.get("Username") or "").strip()
    if actual_username != expected_native_username:
        raise AccountLinkingError(
            "Native Cognito username did not match allowlisted target."
        )

    if target_user.get("Enabled") is not True:
        raise AccountLinkingError(
            "Target native Cognito account is disabled."
        )

    if (target_user.get("UserStatus") or "").upper() != "CONFIRMED":
        raise AccountLinkingError(
            "Target native Cognito account is not CONFIRMED."
        )

    attrs = _extract_attributes(target_user)
    native_email = _normalize_email(attrs.get("email"))
    if not native_email or not hmac.compare_digest(native_email, expected_native_email):
        raise AccountLinkingError(
            "Target native Cognito account email does not match allowlisted native email."
        )

    if not _is_strictly_true(attrs.get("email_verified")):
        raise AccountLinkingError(
            "Target native Cognito account does not have a verified email."
        )

    native_sub = (attrs.get("sub") or "").strip()
    if not native_sub or not hmac.compare_digest(native_sub, expected_native_sub):
        raise AccountLinkingError(
            "Target native Cognito sub does not match allowlisted native sub."
        )

    return _parse_user_identities(target_user)


def handle_pre_signup(event, cognito_client=None, env=None):
    """
    Core Cognito PreSignUp handler with injectable client/env for unit testing.
    """
    if not isinstance(event, dict):
        raise AccountLinkingError("Invalid Cognito PreSignUp event.")

    trigger_source = event.get("triggerSource")
    if trigger_source != "PreSignUp_ExternalProvider":
        return event

    user_pool_id = (event.get("userPoolId") or "").strip()
    if not user_pool_id:
        raise AccountLinkingError("Missing userPoolId in PreSignUp event.")

    external_username = (event.get("userName") or "").strip()
    provider_name, provider_user_id = _parse_external_username(external_username)

    user_attrs = (event.get("request") or {}).get("userAttributes") or {}
    normalized_google_email = _normalize_email(user_attrs.get("email"))
    if not normalized_google_email:
        raise AccountLinkingError(
            "Verified Google email address is required for sign-in."
        )

    if not _is_strictly_true(user_attrs.get("email_verified")):
        raise AccountLinkingError(
            "Google account email must be verified before sign-in."
        )

    founder_allowlist = load_founder_allowlist(env=env)
    client = _get_cognito_client(cognito_client)

    google_email_inspection = inspect_existing_identities(
        cognito_client=client,
        user_pool_id=user_pool_id,
        normalized_email=normalized_google_email,
        external_username=external_username,
        provider_user_id=provider_user_id,
    )

    if google_email_inspection["existing_federated_by_username"] is not None:
        raise AccountLinkingError(
            "An existing federated Cognito user already exists for this Google identity; "
            "manual identity reconciliation is required."
        )

    if google_email_inspection["federated_users_for_email"]:
        raise AccountLinkingError(
            "An existing federated Cognito user already exists for this email; "
            "refusing ambiguous account linking."
        )

    google_email_native_users = google_email_inspection["native_users_for_email"]
    if len(google_email_native_users) > 1:
        raise AccountLinkingError(
            "Multiple native Cognito accounts share this email; refusing ambiguous link."
        )

    is_allowlisted_founder_google = bool(
        founder_allowlist
        and hmac.compare_digest(
            provider_user_id,
            founder_allowlist["google_subject"],
        )
    )

    # Normal new-customer Google signup: no existing native or federated account
    # and not an allowlisted founder Google subject.
    if not google_email_native_users and not is_allowlisted_founder_google:
        return event

    # Existing native user or allowlisted founder subject: never link on email alone.
    if not is_allowlisted_founder_google:
        raise AccountLinkingError(
            "An existing account uses this email. Automatic email-only Google linking "
            "is disabled; sign in with email and password or use explicit identity linking."
        )

    # Require the incoming verified Google email to match the explicitly allowlisted founder Google email.
    if not hmac.compare_digest(
        normalized_google_email,
        founder_allowlist["google_email"],
    ):
        raise AccountLinkingError(
            "Verified Google email did not match the allowlisted founder Google email."
        )

    expected_native_username = founder_allowlist["native_username"]
    expected_native_sub = founder_allowlist["native_sub"]
    expected_native_email = founder_allowlist["native_email"]

    if founder_allowlist["is_cross_email"]:
        # Fail closed unless cross-email founder linking is explicitly opted in,
        # preventing silent Cognito AttributeMapping overwrite of the native email.
        if not founder_allowlist["allow_cross_email"]:
            raise AccountLinkingError(
                "Cross-email founder linking is disabled by default to prevent Cognito "
                "AttributeMapping from silently overwriting the founder's native email."
            )

        # In cross-email mode, no separate native account may already exist on the Google email.
        if google_email_native_users:
            raise AccountLinkingError(
                "A separate native Cognito account already exists for the founder Google email; "
                "refusing ambiguous cross-email link."
            )

        # Also inspect the founder's native email for duplicate native or federated users.
        native_email_inspection = _partition_email_matches(
            cognito_client=client,
            user_pool_id=user_pool_id,
            normalized_email=expected_native_email,
            provider_user_id=provider_user_id,
        )
        if native_email_inspection["federated_users_for_email"]:
            raise AccountLinkingError(
                "An existing federated Cognito user already exists for the founder native email; "
                "manual reconciliation is required."
            )
        native_email_users = native_email_inspection["native_users_for_email"]
        if len(native_email_users) > 1:
            raise AccountLinkingError(
                "Multiple native Cognito accounts share the founder native email; "
                "refusing ambiguous link."
            )
        if native_email_users:
            matched_username = (native_email_users[0].get("Username") or "").strip()
            if matched_username != expected_native_username:
                raise AccountLinkingError(
                    "Founder native email matched a different native Cognito user than allowlisted."
                )
    else:
        if google_email_native_users:
            matched_username = (google_email_native_users[0].get("Username") or "").strip()
            if matched_username != expected_native_username:
                raise AccountLinkingError(
                    "Email matched a different native Cognito user than the allowlisted founder account."
                )

    target_user = _admin_get_user_optional(
        client,
        user_pool_id,
        expected_native_username,
    )
    existing_identities = _validate_target_native_user(
        target_user=target_user,
        expected_native_username=expected_native_username,
        expected_native_sub=expected_native_sub,
        expected_native_email=expected_native_email,
    )

    # Check if Google is already linked on the target native user.
    for identity in existing_identities:
        if not isinstance(identity, dict):
            raise AccountLinkingError(
                "Malformed identity entry on target native Cognito account."
            )
        if (
            str(identity.get("providerName") or "").lower()
            == SUPPORTED_PROVIDER_PREFIX
        ):
            linked_id = str(identity.get("userId") or "").strip()
            if hmac.compare_digest(linked_id, provider_user_id):
                return event
            raise AccountLinkingError(
                "Target native Cognito account is already linked to a different Google identity."
            )

    client.admin_link_provider_for_user(
        UserPoolId=user_pool_id,
        DestinationUser={
            "ProviderName": "Cognito",
            "ProviderAttributeValue": expected_native_username,
        },
        SourceUser={
            "ProviderName": provider_name,
            "ProviderAttributeName": "Cognito_Subject",
            "ProviderAttributeValue": provider_user_id,
        },
    )

    return event


def lambda_handler(event, context):
    return handle_pre_signup(event)
