import io
import json
import sys
import unittest
import urllib.error
from pathlib import Path
from unittest.mock import Mock, patch

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
sys.path.insert(0, str(SRC))

import calendar_tool


class CalendarToolTests(unittest.TestCase):
    def test_missing_access_token(self):
        with self.assertRaises(RuntimeError) as cm:
            calendar_tool.google_calendar_get("https://example.com", None)
        self.assertIn("GOOGLE_AUTH_EXPIRED", str(cm.exception))

        with self.assertRaises(RuntimeError) as cm2:
            calendar_tool.calendar_events("")
        self.assertIn("GOOGLE_AUTH_EXPIRED", str(cm2.exception))

    def test_http_auth_failure_401_and_403(self):
        err_401 = urllib.error.HTTPError(
            url="https://example.com",
            code=401,
            msg="Unauthorized",
            hdrs={},
            fp=io.BytesIO(b'{"error": "unauthorized"}'),
        )
        with patch("urllib.request.urlopen", side_effect=err_401):
            with self.assertRaises(RuntimeError) as cm:
                calendar_tool.calendar_events("valid-token")
            self.assertIn("HTTP 401", str(cm.exception))

        err_403 = urllib.error.HTTPError(
            url="https://example.com",
            code=403,
            msg="Forbidden",
            hdrs={},
            fp=io.BytesIO(b'{"error": "forbidden"}'),
        )
        with patch("urllib.request.urlopen", side_effect=err_403):
            with self.assertRaises(RuntimeError) as cm:
                calendar_tool.calendar_events("valid-token")
            self.assertIn("HTTP 403", str(cm.exception))

    def test_http_404_raises_controlled_error(self):
        err_404 = urllib.error.HTTPError(
            url="https://example.com",
            code=404,
            msg="Not Found",
            hdrs={},
            fp=io.BytesIO(b'{"error": "notFound"}'),
        )
        with patch("urllib.request.urlopen", side_effect=err_404):
            with self.assertRaises(RuntimeError) as cm:
                calendar_tool.calendar_events("valid-token")
            self.assertIn("HTTP 404", str(cm.exception))

    def test_network_service_failure(self):
        with patch(
            "urllib.request.urlopen",
            side_effect=urllib.error.URLError("Connection refused"),
        ):
            with self.assertRaises(RuntimeError) as cm:
                calendar_tool.calendar_events("valid-token")
            self.assertIn("Calendar service unavailable", str(cm.exception))

        with patch(
            "urllib.request.urlopen",
            side_effect=TimeoutError("timed out"),
        ):
            with self.assertRaises(RuntimeError) as cm:
                calendar_tool.calendar_events("valid-token")
            self.assertIn("Calendar service unavailable", str(cm.exception))

    def test_malformed_non_dict_response_and_items(self):
        with patch.object(calendar_tool, "google_calendar_get", return_value=None):
            self.assertEqual(calendar_tool.calendar_events("valid-token"), [])

        with patch.object(calendar_tool, "google_calendar_get", return_value=["not", "a", "dict"]):
            self.assertEqual(calendar_tool.calendar_events("valid-token"), [])

        payload = {
            "items": [
                None,
                "string-item",
                123,
                {
                    "id": "item-1",
                    "summary": "Valid item",
                    "start": None,
                    "end": None,
                },
            ]
        }
        with patch.object(calendar_tool, "google_calendar_get", return_value=payload):
            events = calendar_tool.calendar_events("valid-token")
            self.assertEqual(len(events), 1)
            self.assertEqual(events[0]["id"], "item-1")
            self.assertEqual(events[0]["summary"], "Valid item")
            self.assertIsNone(events[0]["start"])
            self.assertIsNone(events[0]["end"])

    def test_cancelled_event_ignored(self):
        payload = {
            "items": [
                {
                    "id": "ev-1",
                    "summary": "Cancelled meeting",
                    "status": "cancelled",
                    "start": {"dateTime": "2026-09-04T10:00:00Z"},
                },
                {
                    "id": "ev-2",
                    "summary": "Confirmed meeting",
                    "status": "confirmed",
                    "start": {"dateTime": "2026-09-04T11:00:00Z"},
                },
            ]
        }
        with patch.object(calendar_tool, "google_calendar_get", return_value=payload):
            events = calendar_tool.calendar_events("valid-token")
            self.assertEqual(len(events), 1)
            self.assertEqual(events[0]["id"], "ev-2")
            self.assertEqual(events[0]["summary"], "Confirmed meeting")

    def test_missing_summary_handled_safely(self):
        payload = {
            "items": [
                {
                    "id": "ev-no-summary",
                    "start": {"dateTime": "2026-09-04T10:00:00Z"},
                    "end": {"dateTime": "2026-09-04T10:30:00Z"},
                },
                {
                    "id": "ev-none-summary",
                    "summary": None,
                    "start": {"date": "2026-09-04"},
                    "end": {"date": "2026-09-04"},
                },
            ]
        }
        with patch.object(calendar_tool, "google_calendar_get", return_value=payload):
            events = calendar_tool.calendar_events("valid-token")
            self.assertEqual(len(events), 2)
            self.assertEqual(events[0]["summary"], "Untitled event")
            self.assertEqual(events[1]["summary"], "Untitled event")

            summary_text = calendar_tool.spoken_calendar_summary(events, "today")
            self.assertIn("Untitled event", summary_text)
            self.assertNotIn("None", summary_text)


if __name__ == "__main__":
    unittest.main()
