import json
import os

import boto3


COGNITO_CLIENT_ID = os.environ["COGNITO_CLIENT_ID"]

cognito = boto3.client("cognito-idp")


def response(status_code, body):
    return {
        "statusCode": status_code,
        "headers": {
            "content-type": "application/json",
            "cache-control": "no-store",
        },
        "body": json.dumps(body),
    }


def get_body(event):
    try:
        return json.loads(event.get("body") or "{}")
    except json.JSONDecodeError:
        return {}


def login(payload):
    username = payload.get("username", "").strip()
    password = payload.get("password", "")

    if not username or not password:
        return response(
            400,
            {"error": "Email and password are required"},
        )

    try:
        result = cognito.initiate_auth(
            ClientId=COGNITO_CLIENT_ID,
            AuthFlow="USER_PASSWORD_AUTH",
            AuthParameters={
                "USERNAME": username,
                "PASSWORD": password,
            },
        )

        auth = result.get("AuthenticationResult", {})

        if not auth.get("IdToken"):
            return response(
                401,
                {"error": "Login did not return an ID token"},
            )

        return response(
            200,
            {
                "id_token": auth["IdToken"],
                "refresh_token": auth.get("RefreshToken"),
                "expires_in": auth.get("ExpiresIn", 3600),
                "token_type": auth.get("TokenType", "Bearer"),
            },
        )

    except cognito.exceptions.NotAuthorizedException:
        return response(
            401,
            {"error": "Incorrect email or password"},
        )

    except cognito.exceptions.UserNotFoundException:
        return response(
            401,
            {"error": "Incorrect email or password"},
        )

    except cognito.exceptions.UserNotConfirmedException:
        return response(
            403,
            {"error": "Account is not confirmed"},
        )

    except Exception as exc:
        print("[AUTH LOGIN ERROR]", str(exc))

        return response(
            500,
            {"error": "Hayder login failed"},
        )


def refresh(payload):
    refresh_token = payload.get("refresh_token", "").strip()

    if not refresh_token:
        return response(
            400,
            {"error": "Refresh token is required"},
        )

    try:
        result = cognito.initiate_auth(
            ClientId=COGNITO_CLIENT_ID,
            AuthFlow="REFRESH_TOKEN_AUTH",
            AuthParameters={
                "REFRESH_TOKEN": refresh_token,
            },
        )

        auth = result.get("AuthenticationResult", {})

        if not auth.get("IdToken"):
            return response(
                401,
                {"error": "Session could not be refreshed"},
            )

        return response(
            200,
            {
                "id_token": auth["IdToken"],
                "expires_in": auth.get("ExpiresIn", 3600),
                "token_type": auth.get("TokenType", "Bearer"),
            },
        )

    except cognito.exceptions.NotAuthorizedException:
        return response(
            401,
            {
                "error": (
                    "Session expired. Please sign in again."
                )
            },
        )

    except Exception as exc:
        print("[AUTH REFRESH ERROR]", str(exc))

        return response(
            500,
            {"error": "Hayder could not refresh the session"},
        )


def lambda_handler(event, context):
    method = (
        event.get("requestContext", {})
        .get("http", {})
        .get("method", "")
    )

    path = event.get("rawPath", "")

    if method != "POST":
        return response(
            405,
            {"error": "Method not allowed"},
        )

    payload = get_body(event)

    if path == "/auth/login":
        return login(payload)

    if path == "/auth/refresh":
        return refresh(payload)

    return response(
        404,
        {"error": "Route not found"},
    )
