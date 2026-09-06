"""
Unit tests for Hayder Phase 1 public website and voice UX.

Validates:
1. Route availability:
   - /hayder
   - /hayder/features
   - /hayder/how-it-works
   - /hayder/security
   - /hayder/pricing
   - /hayder/about
   - /hayder/support
   - /privacy
   - /terms
   - /voice
2. Brand, product, and legal decisions:
   - Xorwia company/legal entity
   - Support contact hayder@xorwia.com
   - Hayder Pro launch price £19.99/month (billing connected separately at launch)
   - Business plan marked 'Coming later'
   - Absence of unsupported compliance claims (no SOC 2, no GDPR certification badges, no fake end-to-end encryption)
3. Voice UI states:
   - idle, listening, thinking, speaking, reconnect required, error
4. Temporary logo placeholder and multicolour heartbeat motif.
5. Responsive and accessibility considerations.
"""

import importlib
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
sys.path.insert(0, str(SRC))

web = importlib.import_module("web")
voice = importlib.import_module("voice")


class PublicWebsiteAndVoiceTests(unittest.TestCase):

    def test_routes_return_200_and_html(self):
        """All required routes return HTTP 200 with text/html content-type."""
        routes = [
            "/hayder",
            "/hayder/features",
            "/hayder/how-it-works",
            "/hayder/security",
            "/hayder/pricing",
            "/hayder/about",
            "/hayder/support",
            "/privacy",
            "/terms",
            "/voice",
        ]
        for route in routes:
            with self.subTest(route=route):
                res = voice.lambda_handler({"rawPath": route}, {})
                self.assertEqual(res["statusCode"], 200)
                self.assertIn("text/html", res["headers"]["content-type"])
                self.assertTrue(len(res["body"]) > 500)

    def test_default_empty_event_returns_voice_page(self):
        """Empty event dict defaults to voice assistant page for backward compatibility."""
        res = voice.lambda_handler({}, {})
        self.assertEqual(res["statusCode"], 200)
        self.assertIn("text/html", res["headers"]["content-type"])
        self.assertIn("async function sendToHayder(message)", res["body"])

    def test_unknown_route_returns_404(self):
        """Unknown route returns 404 with clean not found page."""
        res = voice.lambda_handler({"rawPath": "/unknown-nonexistent-page"}, {})
        self.assertEqual(res["statusCode"], 404)
        self.assertIn("Page not found", res["body"])

    def test_root_route_not_claimed_by_hayder(self):
        """Root route '/' is not claimed by Hayder (returns 404 to avoid taking over company homepage)."""
        res = voice.lambda_handler({"rawPath": "/"}, {})
        self.assertEqual(res["statusCode"], 404)
        self.assertIn("Page not found", res["body"])

    def test_home_page_elements(self):
        """Landing page contains hero, proposition, Google CTA, preview, benefits, trust reassurance, and heartbeat motif."""
        res = voice.lambda_handler({"rawPath": "/hayder"}, {})
        html = res["body"]

        # Hero & Proposition
        self.assertIn("HAYDER", html)
        self.assertIn("by Xorwia", html)
        self.assertIn("The operations assistant that prepares. You approve.", html)
        self.assertIn("Gmail and Google Calendar", html)

        # Google CTA
        self.assertIn("Connect with Google", html)
        self.assertIn("/oauth/google/connect", html)

        # Product UI Preview
        self.assertIn("WAITING_APPROVAL", html)
        self.assertIn("Action Staged for Human Approval", html)
        self.assertIn("Approve &amp; Send", html)

        # Core Benefits
        self.assertIn("Daily Attention Briefing", html)
        self.assertIn("Strict Human Approval", html)
        self.assertIn("Consistent Natural Voice", html)
        self.assertIn("Single-Account Security", html)

        # Trust / Privacy Reassurance
        self.assertIn("Single verified Google account", html)
        self.assertIn("Zero autonomous email sends", html)

        # Heartbeat motif & Voice preview
        self.assertIn("A calm, human-like voice experience", html)
        self.assertIn("Interactive Voice State Preview", html)
        self.assertIn("Hear Hayder's Voice Sample", html)

    def test_features_page_elements(self):
        """Features page details only active Phase 1 capabilities."""
        res = voice.lambda_handler({"rawPath": "/hayder/features"}, {})
        html = res["body"]

        self.assertIn("Gmail &amp; Email Assistance", html)
        self.assertIn("Google Calendar Awareness", html)
        self.assertIn("Daily Briefing &amp; Attention Engine", html)
        self.assertIn("Human Approval Before Sensitive Actions", html)
        self.assertIn("Calm Voice &amp; Chat Interface", html)
        self.assertIn("Connect with Google", html)

    def test_how_it_works_six_steps(self):
        """How it works details the 6 transparent operational steps."""
        res = voice.lambda_handler({"rawPath": "/hayder/how-it-works"}, {})
        html = res["body"]

        self.assertIn("Connect Google via Official OAuth 2.0", html)
        self.assertIn("Hayder Understands Email &amp; Calendar Context", html)
        self.assertIn("Ask Naturally by Chat or Voice", html)
        self.assertIn("Hayder Prepares Actions", html)
        self.assertIn("User Approves Sensitive Actions", html)
        self.assertIn("Action Executes Safely", html)

    def test_security_page_and_no_unsupported_compliance_claims(self):
        """Security page details honest boundaries without unsupported compliance badges."""
        res = voice.lambda_handler({"rawPath": "/hayder/security"}, {})
        html = res["body"]

        self.assertIn("Google OAuth 2.0 Integration", html)
        self.assertIn("User Control &amp; Revocation", html)
        self.assertIn("The Approval-Before-Action Model", html)
        self.assertIn("Single Google Account Boundary", html)
        self.assertIn("Privacy-Focused Infrastructure", html)
        self.assertIn("hayder@xorwia.com", html)

        # Strictly no unverified claims
        self.assertNotIn("SOC 2 Type II Certified", html)
        self.assertNotIn("GDPR Certified", html)
        self.assertNotIn("end-to-end encryption", html.lower())

    def test_pricing_page_tier_and_trial(self):
        """Pricing specifies £19.99/month, 'Get Started' CTA, Business 'Coming later', and no enforced trial claims."""
        res = voice.lambda_handler({"rawPath": "/hayder/pricing"}, {})
        html = res["body"]

        self.assertIn("&pound;19.99", html)
        self.assertIn("Hayder Pro", html)
        self.assertIn("Hayder Business", html)
        self.assertIn("Coming later", html)
        self.assertIn("Get Started", html)
        self.assertNotIn("14-day free trial", html)
        self.assertNotIn("14-day", html)

    def test_about_page(self):
        """About page states Hayder is a Xorwia product designed to reduce busywork."""
        res = voice.lambda_handler({"rawPath": "/hayder/about"}, {})
        html = res["body"]

        self.assertIn("Hayder is a Xorwia Product", html)
        self.assertIn("Hayder remembers. Hayder prepares. You approve important actions.", html)
        self.assertIn("Context Fragmentation", html)
        self.assertIn("hayder@xorwia.com", html)

    def test_support_page(self):
        """Support page highlights hayder@xorwia.com and the 5 common help areas."""
        res = voice.lambda_handler({"rawPath": "/hayder/support"}, {})
        html = res["body"]

        self.assertIn("hayder@xorwia.com", html)
        self.assertIn("Google Connection &amp; Reconnection", html)
        self.assertIn("Account &amp; Access", html)
        self.assertIn("Email Approvals", html)
        self.assertIn("Voice Interaction &amp; Browser Microphone", html)
        self.assertIn("Privacy &amp; Data Questions", html)

    def test_privacy_and_terms_legal_pages(self):
        """Legal pages cover Google Limited Use compliance, user control, and terms."""
        privacy_res = voice.lambda_handler({"rawPath": "/privacy"}, {})
        self.assertEqual(privacy_res["statusCode"], 200)
        self.assertIn("Google API Services User Data Policy", privacy_res["body"])
        self.assertIn("Limited Use requirements", privacy_res["body"])
        self.assertIn("hayder@xorwia.com", privacy_res["body"])

        terms_res = voice.lambda_handler({"rawPath": "/terms"}, {})
        self.assertEqual(terms_res["statusCode"], 200)
        self.assertIn("Terms of Service", terms_res["body"])
        self.assertIn("&pound;19.99", terms_res["body"])
        self.assertNotIn("14-day free trial", terms_res["body"])
        self.assertNotIn("14-day", terms_res["body"])
        self.assertIn("Subscriptions &amp; Payments", terms_res["body"])

    def test_shared_footer_across_pages(self):
        """Shared footer is present and links to all required routes."""
        res = voice.lambda_handler({"rawPath": "/hayder"}, {})
        html = res["body"]

        required_footer_links = [
            "/hayder/features",
            "/hayder/how-it-works",
            "/hayder/security",
            "/hayder/pricing",
            "/hayder/about",
            "/hayder/support",
            "/privacy",
            "/terms",
        ]
        for link in required_footer_links:
            self.assertIn(f'href="{link}"', html)
        self.assertIn("Hayder is a product by Xorwia", html)

    def test_voice_visual_states_and_elements(self):
        """Voice page implements the 6 visual states and preserves all core DOM IDs."""
        res = voice.lambda_handler({"rawPath": "/voice"}, {})
        html = res["body"]

        # 6 Visual states in CSS
        self.assertIn(".core.idle", html)
        self.assertIn(".core.listening", html)
        self.assertIn(".core.thinking", html)
        self.assertIn(".core.speaking", html)
        self.assertIn(".core.reconnect", html)
        self.assertIn(".core.error", html)

        # Required DOM elements for voice assistant operations
        required_dom_ids = [
            'id="username"',
            'id="password"',
            'id="loginButton"',
            'id="loginStatus"',
            'id="loginCard"',
            'id="assistantCard"',
            'id="sessionStatus"',
            'id="command"',
            'id="micButton"',
            'id="sendButton"',
            'id="googleButton"',
            'id="logoutButton"',
            'id="status"',
            'id="heard"',
            'id="reply"',
            'id="core"',
            'id="reconnectBanner"',
        ]
        for dom_id in required_dom_ids:
            self.assertIn(dom_id, html)

    def test_temporary_logo_placeholder_present(self):
        """Temporary logo placeholder contains comment indicating exact logo still to be locked."""
        res = voice.lambda_handler({"rawPath": "/hayder"}, {})
        html = res["body"]
        self.assertIn("Temporary Placeholder: Hayder multicolour heartbeat logo to be locked", html)

    def test_responsive_meta_and_accessibility(self):
        """Pages contain viewport meta tag and semantic landmarks."""
        for path in ["/hayder", "/voice", "/hayder/pricing"]:
            res = voice.lambda_handler({"rawPath": path}, {})
            html = res["body"]
            self.assertIn('<meta name="viewport" content="width=device-width, initial-scale=1.0">', html)
            self.assertIn("<header", html)
            self.assertIn("<main", html)
            self.assertIn("<footer", html)


if __name__ == "__main__":
    unittest.main()
