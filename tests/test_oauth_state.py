import hashlib
import importlib
import json
import os
import sys
import time
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
sys.path.insert(0, str(SRC))

os.environ.setdefault("HAYDER_TABLE", "test-memory")
os.environ.setdefault("HAYDER_APPROVAL_TABLE", "test-approvals")
os.environ.setdefault("AWS_LAMBDA_FUNCTION_NAME", "test-function")


class FakeConditionalCheckFailedException(Exception):
    pass


class FakeTable:
    def __init__(self):
        self.items = {}

    def put_item(self, Item):
        key = (Item["user_id"], Item["record_key"])
        self.items[key] = dict(Item)

    def update_item(
        self,
        Key,
        UpdateExpression,
        ConditionExpression=None,
        ExpressionAttributeNames=None,
        ExpressionAttributeValues=None,
    ):
        key = (Key["user_id"], Key["record_key"])
        item = self.items.get(key)

        # Condition: attribute_exists(#rk) AND attribute_not_exists(#consumed_at)
        if item is None:
            raise FakeConditionalCheckFailedException("Item does not exist")

        consumed_attr = (
            ExpressionAttributeNames.get("#consumed_at", "consumed_at")
            if ExpressionAttributeNames
            else "consumed_at"
        )
        if consumed_attr in item:
            raise FakeConditionalCheckFailedException("Item already consumed")

        now_val = (
            ExpressionAttributeValues.get(":now")
            if ExpressionAttributeValues
            else None
        )
        item[consumed_attr] = now_val
        return {"Attributes": item}


class FakeBoto3:
    def resource(self, service):
        return SimpleNamespace(
            Table=lambda name: SimpleNamespace(name=name),
        )

    def client(self, service):
        return SimpleNamespace()


sys.modules.setdefault("boto3", FakeBoto3())
app = importlib.import_module("app")


class OAuthStateReplayTests(unittest.TestCase):
    def setUp(self):
        self.fake_table = FakeTable()
        self.client_id = "test-client-id"
        self.client_secret = "test-client-secret"

    def _get_creds(self):
        return (self.client_id, self.client_secret)

    def test_state_creation_stores_sha256_hash_only_bound_to_user_id(self):
        with (
            patch.object(app, "get_google_credentials", side_effect=self._get_creds),
            patch.object(app, "table", self.fake_table),
        ):
            state = app.create_google_state("user-123")

        self.assertIsInstance(state, str)
        self.assertIn(".", state)

        # Inspect DynamoDB table items
        self.assertEqual(len(self.fake_table.items), 1)
        stored_key, stored_item = next(iter(self.fake_table.items.items()))

        # Bound to user_id
        self.assertEqual(stored_key[0], "user-123")
        self.assertEqual(stored_item["user_id"], "user-123")

        # Decode payload to extract nonce
        encoded_payload, _ = state.split(".", 1)
        payload = json.loads(app.b64url_decode(encoded_payload).decode("utf-8"))
        raw_nonce = payload["n"]
        expected_hash = hashlib.sha256(raw_nonce.encode("utf-8")).hexdigest()

        # Check record key format and hash storage
        self.assertEqual(stored_key[1], f"OAUTH_STATE#{expected_hash}")
        self.assertEqual(stored_item["record_key"], f"OAUTH_STATE#{expected_hash}")
        self.assertEqual(stored_item["nonce_hash"], expected_hash)

        # Raw nonce must NOT be stored in the item
        self.assertNotIn(raw_nonce, stored_item.values())
        self.assertNotIn("n", stored_item)
        self.assertNotIn("nonce", stored_item)

        # No DynamoDB TTL added
        self.assertNotIn("ttl", stored_item)
        self.assertNotIn("expires_at", stored_item)

    def test_atomic_consumption_once_and_replay_fails(self):
        with (
            patch.object(app, "get_google_credentials", side_effect=self._get_creds),
            patch.object(app, "table", self.fake_table),
        ):
            state = app.create_google_state("user-456")

            # First verification must succeed and consume state
            verified_user = app.verify_google_state(state)
            self.assertEqual(verified_user, "user-456")

            # Stored item now has consumed_at
            item = next(iter(self.fake_table.items.values()))
            self.assertIn("consumed_at", item)
            self.assertIsNotNone(item["consumed_at"])

            # Second verification (replay) must fail
            replayed_user = app.verify_google_state(state)
            self.assertIsNone(replayed_user)

    def test_uncreated_state_cannot_be_consumed(self):
        # Create a properly signed state but do not store it in DynamoDB
        now = int(time.time())
        payload = {"u": "user-789", "t": now, "n": "dummy-nonce"}
        payload_bytes = json.dumps(payload, separators=(",", ":")).encode("utf-8")
        encoded = app.b64url_encode(payload_bytes)
        import hmac

        signature = hmac.new(
            self.client_secret.encode("utf-8"),
            encoded.encode("utf-8"),
            hashlib.sha256,
        ).digest()
        state = encoded + "." + app.b64url_encode(signature)

        with (
            patch.object(app, "get_google_credentials", side_effect=self._get_creds),
            patch.object(app, "table", self.fake_table),
        ):
            # Table is empty, so item doesn't exist
            result = app.verify_google_state(state)
            self.assertIsNone(result)

    def test_expired_state_beyond_10_minutes_fails(self):
        with (
            patch.object(app, "get_google_credentials", side_effect=self._get_creds),
            patch.object(app, "table", self.fake_table),
        ):
            state = app.create_google_state("user-exp")

            # Fast-forward time by 601 seconds (beyond 10 minutes)
            current_time = int(time.time())
            with patch("time.time", return_value=current_time + 601):
                result = app.verify_google_state(state)
                self.assertIsNone(result)

    def test_materially_future_timestamp_rejected(self):
        with (
            patch.object(app, "get_google_credentials", side_effect=self._get_creds),
            patch.object(app, "table", self.fake_table),
        ):
            state = app.create_google_state("user-future")

            # Timestamp in the future by 300 seconds (> 60s skew allowance)
            current_time = int(time.time())
            with patch("time.time", return_value=current_time - 300):
                result = app.verify_google_state(state)
                self.assertIsNone(result)

    def test_clock_skew_within_60_seconds_accepted(self):
        with (
            patch.object(app, "get_google_credentials", side_effect=self._get_creds),
            patch.object(app, "table", self.fake_table),
        ):
            state = app.create_google_state("user-skew")

            # Timestamp slightly ahead by 15 seconds (within 60s clock skew)
            current_time = int(time.time())
            with patch("time.time", return_value=current_time - 15):
                result = app.verify_google_state(state)
                self.assertEqual(result, "user-skew")

    def test_tampered_signature_rejected(self):
        with (
            patch.object(app, "get_google_credentials", side_effect=self._get_creds),
            patch.object(app, "table", self.fake_table),
        ):
            state = app.create_google_state("user-tamper")
            tampered_state = state[:-3] + "xyz"
            result = app.verify_google_state(tampered_state)
            self.assertIsNone(result)

    def test_template_iam_allows_update_item_on_hayder_memory_table(self):
        template_text = (ROOT / "template.yaml").read_text()
        self.assertIn("dynamodb:UpdateItem", template_text)
        # Verify it is in the HayderMemoryTable section
        lines = template_text.splitlines()
        found_memory_table_statement = False
        update_item_found = False
        for i, line in enumerate(lines):
            if "!GetAtt HayderMemoryTable.Arn" in line:
                # Look backwards in this statement block
                stmt_lines = lines[max(0, i - 10) : i + 1]
                for stmt_line in stmt_lines:
                    if "- dynamodb:UpdateItem" in stmt_line:
                        update_item_found = True
                        break
        self.assertTrue(update_item_found)


if __name__ == "__main__":
    unittest.main()
