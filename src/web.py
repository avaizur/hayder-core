"""
Hayder Phase 1 Public Website & Shared Layouts.

Implements clean, minimal, Google-like public pages for Hayder by Xorwia:
- /hayder (Landing page)
- /hayder/features (Phase 1 capabilities)
- /hayder/how-it-works (6-step architecture & workflow)
- /hayder/security (Google OAuth, approval-before-action, privacy)
- /hayder/pricing (Hayder Pro £19.99/mo, Business plan coming later)
- /hayder/about (Xorwia product, reduce busywork, user control)
- /hayder/support (hayder@xorwia.com, 5 common help areas)
- /privacy (Shared Xorwia privacy policy)
- /terms (Shared Xorwia terms of service)
"""

import html

# ---------------------------------------------------------------------------
# SHARED DESIGN TOKENS & STYLES
# ---------------------------------------------------------------------------

SHARED_CSS = """
:root {
  --bg-page: #ffffff;
  --bg-surface: #f9fafb;
  --bg-card: #ffffff;
  --text-primary: #111827;
  --text-secondary: #4b5563;
  --text-tertiary: #6b7280;
  --text-light: #9ca3af;
  --border-subtle: #e5e7eb;
  --border-strong: #d1d5db;
  --primary-button: #111827;
  --primary-button-hover: #1f2937;
  --google-blue: #1a73e8;
  --pulse-cyan: #00acc1;
  --pulse-violet: #7c3aed;
  --pulse-amber: #f59e0b;
  --pulse-rose: #ef4444;
  --card-shadow: 0 1px 3px rgba(0,0,0,0.04), 0 1px 2px rgba(0,0,0,0.02);
  --elevated-shadow: 0 4px 6px -1px rgba(0,0,0,0.05), 0 2px 4px -2px rgba(0,0,0,0.03);
  --font-stack: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, "Helvetica Neue", Arial, sans-serif;
  --max-width: 1060px;
}

* {
  box-sizing: border-box;
  margin: 0;
  padding: 0;
}

body {
  background-color: var(--bg-page);
  color: var(--text-primary);
  font-family: var(--font-stack);
  font-size: 16px;
  line-height: 1.6;
  -webkit-font-smoothing: antialiased;
  -moz-osx-font-smoothing: grayscale;
  min-height: 100vh;
  display: flex;
  flex-direction: column;
}

a {
  color: inherit;
  text-decoration: none;
}

/* Header & Nav */
header.site-header {
  position: sticky;
  top: 0;
  background: rgba(255, 255, 255, 0.95);
  backdrop-filter: blur(8px);
  border-bottom: 1px solid var(--border-subtle);
  z-index: 100;
}

.header-container {
  max-width: var(--max-width);
  margin: 0 auto;
  padding: 16px 24px;
  display: flex;
  align-items: center;
  justify-content: space-between;
}

.brand-wrapper {
  display: flex;
  align-items: center;
  gap: 12px;
}

.brand-logo {
  display: flex;
  align-items: center;
  gap: 10px;
}

.logo-heartbeat-svg {
  width: 28px;
  height: 28px;
  flex-shrink: 0;
}

.brand-title {
  font-size: 18px;
  font-weight: 700;
  letter-spacing: 0.05em;
  color: var(--text-primary);
}

.brand-badge {
  font-size: 12px;
  font-weight: 500;
  color: var(--text-tertiary);
  background: var(--bg-surface);
  border: 1px solid var(--border-subtle);
  padding: 2px 8px;
  border-radius: 9999px;
}

nav.main-nav {
  display: flex;
  align-items: center;
  gap: 24px;
}

.nav-link {
  font-size: 14px;
  font-weight: 500;
  color: var(--text-secondary);
  transition: color 0.15s ease;
}

.nav-link:hover, .nav-link.active {
  color: var(--text-primary);
}

.nav-cta-group {
  display: flex;
  align-items: center;
  gap: 12px;
}

/* Buttons */
.btn {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  gap: 8px;
  padding: 10px 18px;
  font-size: 14px;
  font-weight: 500;
  border-radius: 8px;
  transition: all 0.15s ease;
  cursor: pointer;
  white-space: nowrap;
}

.btn-primary {
  background: var(--primary-button);
  color: #ffffff;
  border: 1px solid var(--primary-button);
}

.btn-primary:hover {
  background: var(--primary-button-hover);
}

.btn-secondary {
  background: #ffffff;
  color: var(--text-primary);
  border: 1px solid var(--border-strong);
}

.btn-secondary:hover {
  background: var(--bg-surface);
  border-color: var(--text-primary);
}

.btn-google {
  background: #ffffff;
  color: #1f2937;
  border: 1px solid var(--border-strong);
  font-weight: 500;
  box-shadow: 0 1px 2px rgba(0,0,0,0.05);
}

.btn-google:hover {
  background: #f8fafc;
  border-color: #94a3b8;
}

.btn-sm {
  padding: 6px 12px;
  font-size: 13px;
}

.btn-lg {
  padding: 14px 28px;
  font-size: 16px;
  border-radius: 10px;
}

/* Layout Containers */
main.main-content {
  flex: 1 0 auto;
}

.section {
  padding: 80px 24px;
}

.section-hero {
  padding: 96px 24px 72px;
  text-align: center;
}

.container {
  max-width: var(--max-width);
  margin: 0 auto;
}

.container-narrow {
  max-width: 760px;
  margin: 0 auto;
}

/* Typography */
h1.hero-title {
  font-size: 48px;
  font-weight: 700;
  line-height: 1.15;
  letter-spacing: -0.02em;
  color: var(--text-primary);
  margin-bottom: 20px;
}

p.hero-subtitle {
  font-size: 20px;
  line-height: 1.5;
  color: var(--text-secondary);
  margin-bottom: 36px;
  font-weight: 400;
}

h2.section-title {
  font-size: 32px;
  font-weight: 700;
  letter-spacing: -0.015em;
  color: var(--text-primary);
  margin-bottom: 12px;
  text-align: center;
}

p.section-subtitle {
  font-size: 17px;
  color: var(--text-secondary);
  text-align: center;
  max-width: 680px;
  margin: 0 auto 48px;
}

h3.card-title {
  font-size: 19px;
  font-weight: 600;
  color: var(--text-primary);
  margin-bottom: 8px;
}

/* Cards & Grids */
.grid-2 {
  display: grid;
  grid-template-columns: repeat(2, 1fr);
  gap: 24px;
}

.grid-3 {
  display: grid;
  grid-template-columns: repeat(3, 1fr);
  gap: 24px;
}

.card {
  background: var(--bg-card);
  border: 1px solid var(--border-subtle);
  border-radius: 14px;
  padding: 28px;
  box-shadow: var(--card-shadow);
  transition: border-color 0.15s ease, box-shadow 0.15s ease;
}

.card:hover {
  border-color: var(--border-strong);
}

.card-icon-wrap {
  width: 44px;
  height: 44px;
  border-radius: 10px;
  background: var(--bg-surface);
  border: 1px solid var(--border-subtle);
  display: flex;
  align-items: center;
  justify-content: center;
  margin-bottom: 18px;
  font-size: 20px;
}

/* Subtle Multicolour Heartbeat Motif */
.heartbeat-motif {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  position: relative;
}

.heartbeat-pulse-ring {
  position: absolute;
  width: 100%;
  height: 100%;
  border-radius: 50%;
  border: 2px solid var(--google-blue);
  opacity: 0.15;
  animation: pulse-ring 3s cubic-bezier(0.215, 0.61, 0.355, 1) infinite;
}

@keyframes pulse-ring {
  0% { transform: scale(0.85); opacity: 0.4; }
  50% { transform: scale(1.15); opacity: 0.1; }
  100% { transform: scale(0.85); opacity: 0.4; }
}

/* Product UI Preview Card */
.preview-card {
  background: #ffffff;
  border: 1px solid var(--border-subtle);
  border-radius: 18px;
  box-shadow: var(--elevated-shadow);
  overflow: hidden;
  max-width: 840px;
  margin: 0 auto;
  text-align: left;
}

.preview-header {
  padding: 16px 24px;
  background: var(--bg-surface);
  border-bottom: 1px solid var(--border-subtle);
  display: flex;
  align-items: center;
  justify-content: space-between;
}

.preview-dots {
  display: flex;
  gap: 6px;
}

.preview-dot {
  width: 10px;
  height: 10px;
  border-radius: 50%;
  background: var(--border-strong);
}

.preview-title-bar {
  font-size: 13px;
  font-weight: 500;
  color: var(--text-tertiary);
  display: flex;
  align-items: center;
  gap: 8px;
}

.preview-body {
  padding: 28px;
  display: flex;
  flex-direction: column;
  gap: 20px;
}

.preview-briefing-card {
  background: var(--bg-surface);
  border: 1px solid var(--border-subtle);
  border-radius: 12px;
  padding: 20px;
}

.preview-item {
  display: flex;
  align-items: flex-start;
  gap: 14px;
  padding: 12px 0;
  border-bottom: 1px solid var(--border-subtle);
}

.preview-item:last-child {
  border-bottom: none;
  padding-bottom: 0;
}

.preview-item-icon {
  font-size: 18px;
  margin-top: 2px;
}

.approval-stage-card {
  border: 1px solid #fed7aa;
  background: #fffbf5;
  border-radius: 12px;
  padding: 20px;
}

.approval-stage-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 12px;
}

.badge-waiting {
  background: #fef3c7;
  color: #92400e;
  border: 1px solid #fde68a;
  font-size: 12px;
  font-weight: 600;
  padding: 3px 10px;
  border-radius: 9999px;
  text-transform: uppercase;
  letter-spacing: 0.04em;
}

.approval-actions {
  display: flex;
  gap: 10px;
  margin-top: 16px;
}

/* Voice Preview Demo */
.voice-demo-container {
  background: var(--bg-surface);
  border: 1px solid var(--border-subtle);
  border-radius: 16px;
  padding: 36px 28px;
  text-align: center;
  max-width: 680px;
  margin: 0 auto;
}

.voice-core-orb {
  width: 88px;
  height: 88px;
  margin: 0 auto 20px;
  border-radius: 50%;
  background: #ffffff;
  border: 2px solid var(--border-subtle);
  display: flex;
  align-items: center;
  justify-content: center;
  position: relative;
  transition: all 0.3s ease;
}

.voice-state-controls {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
  justify-content: center;
  margin-top: 24px;
}

.state-pill {
  background: #ffffff;
  border: 1px solid var(--border-subtle);
  padding: 6px 14px;
  border-radius: 9999px;
  font-size: 13px;
  font-weight: 500;
  color: var(--text-secondary);
  cursor: pointer;
  transition: all 0.15s ease;
}

.state-pill:hover, .state-pill.active {
  background: var(--primary-button);
  color: #ffffff;
  border-color: var(--primary-button);
}

/* Reassurance & Badges */
.reassurance-strip {
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 28px;
  flex-wrap: wrap;
  margin-top: 28px;
  font-size: 14px;
  color: var(--text-tertiary);
}

.reassurance-item {
  display: inline-flex;
  align-items: center;
  gap: 8px;
}

/* Pricing Card */
.pricing-card {
  border: 2px solid var(--text-primary);
  border-radius: 18px;
  padding: 40px;
  background: #ffffff;
  position: relative;
  box-shadow: var(--elevated-shadow);
}

.pricing-badge {
  position: absolute;
  top: -14px;
  left: 36px;
  background: var(--text-primary);
  color: #ffffff;
  font-size: 12px;
  font-weight: 600;
  padding: 4px 14px;
  border-radius: 9999px;
  letter-spacing: 0.04em;
  text-transform: uppercase;
}

.pricing-price {
  font-size: 44px;
  font-weight: 700;
  color: var(--text-primary);
  margin: 16px 0 4px;
}

.pricing-interval {
  font-size: 16px;
  font-weight: 400;
  color: var(--text-tertiary);
}

.pricing-trial-note {
  font-size: 14px;
  font-weight: 600;
  color: var(--google-blue);
  margin-bottom: 24px;
}

.pricing-features-list {
  list-style: none;
  margin: 28px 0;
  display: flex;
  flex-direction: column;
  gap: 14px;
}

.pricing-feature-item {
  display: flex;
  align-items: flex-start;
  gap: 12px;
  font-size: 15px;
  color: var(--text-secondary);
}

.pricing-feature-check {
  color: var(--google-blue);
  font-weight: bold;
}

.card-disabled {
  background: var(--bg-surface);
  border: 1px dashed var(--border-strong);
  opacity: 0.85;
}

/* FAQ Accordion */
.faq-list {
  display: flex;
  flex-direction: column;
  gap: 16px;
}

.faq-item {
  border: 1px solid var(--border-subtle);
  border-radius: 12px;
  background: #ffffff;
  padding: 24px;
}

.faq-question {
  font-size: 17px;
  font-weight: 600;
  color: var(--text-primary);
  margin-bottom: 8px;
}

.faq-answer {
  font-size: 15px;
  color: var(--text-secondary);
  line-height: 1.6;
}

/* Footer */
footer.site-footer {
  background: var(--bg-surface);
  border-top: 1px solid var(--border-subtle);
  padding: 64px 24px 40px;
  margin-top: auto;
}

.footer-container {
  max-width: var(--max-width);
  margin: 0 auto;
}

.footer-grid {
  display: grid;
  grid-template-columns: 2fr 1fr 1fr 1fr;
  gap: 48px;
  margin-bottom: 48px;
}

.footer-col-title {
  font-size: 13px;
  font-weight: 600;
  color: var(--text-primary);
  text-transform: uppercase;
  letter-spacing: 0.05em;
  margin-bottom: 18px;
}

.footer-nav {
  list-style: none;
  display: flex;
  flex-direction: column;
  gap: 12px;
}

.footer-link {
  font-size: 14px;
  color: var(--text-secondary);
  transition: color 0.15s ease;
}

.footer-link:hover {
  color: var(--text-primary);
}

.footer-bottom {
  padding-top: 32px;
  border-top: 1px solid var(--border-subtle);
  display: flex;
  align-items: center;
  justify-content: space-between;
  flex-wrap: wrap;
  gap: 16px;
  font-size: 13px;
  color: var(--text-tertiary);
}

/* Mobile Responsiveness */
@media (max-width: 768px) {
  .header-container {
    flex-direction: column;
    align-items: flex-start;
    gap: 16px;
    padding: 14px 18px;
  }
  nav.main-nav {
    flex-wrap: wrap;
    gap: 16px;
    width: 100%;
  }
  .nav-cta-group {
    width: 100%;
    margin-top: 8px;
  }
  .nav-cta-group .btn {
    flex: 1;
  }
  h1.hero-title {
    font-size: 34px;
  }
  p.hero-subtitle {
    font-size: 17px;
  }
  .section {
    padding: 48px 18px;
  }
  .section-hero {
    padding: 56px 18px 40px;
  }
  .grid-2, .grid-3 {
    grid-template-columns: 1fr;
  }
  .footer-grid {
    grid-template-columns: 1fr;
    gap: 32px;
  }
  .pricing-card {
    padding: 28px 20px;
  }
}
"""

# ---------------------------------------------------------------------------
# SVG ASSETS & PLACEHOLDERS
# ---------------------------------------------------------------------------

# Temporary Placeholder: Hayder multicolour heartbeat logo to be locked.
# Uses restrained subtle multicolor strokes: blue #1a73e8, cyan #00acc1, violet #7c3aed, amber #f59e0b.
def render_logo_svg(width=28, height=28):
    return f"""<!-- Temporary Placeholder: Hayder multicolour heartbeat logo to be locked -->
<svg class="logo-heartbeat-svg" width="{width}" height="{height}" viewBox="0 0 28 28" fill="none" xmlns="http://www.w3.org/2000/svg" aria-label="Hayder multicolour heartbeat logo">
  <defs>
    <linearGradient id="hayder-grad" x1="0%" y1="0%" x2="100%" y2="100%">
      <stop offset="0%" stop-color="#1a73e8" />
      <stop offset="35%" stop-color="#00acc1" />
      <stop offset="70%" stop-color="#7c3aed" />
      <stop offset="100%" stop-color="#f59e0b" />
    </linearGradient>
  </defs>
  <circle cx="14" cy="14" r="12.5" stroke="url(#hayder-grad)" stroke-width="1.75" fill="none" opacity="0.9" />
  <path d="M6 14.5h3.2l2.3-4.5 3.2 9 2.5-6 1.8 3 1.5-1.5H22" stroke="url(#hayder-grad)" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round" />
</svg>"""

def render_google_icon_svg():
    return """<svg width="18" height="18" viewBox="0 0 18 18" xmlns="http://www.w3.org/2000/svg" aria-hidden="true">
  <path d="M17.64 9.2c0-.637-.057-1.251-.164-1.84H9v3.481h4.844c-.209 1.125-.843 2.078-1.796 2.717v2.258h2.908c1.702-1.567 2.684-3.874 2.684-6.616z" fill="#4285F4"/>
  <path d="M9 18c2.43 0 4.467-.806 5.956-2.18l-2.908-2.259c-.806.54-1.837.86-3.048.86-2.344 0-4.328-1.584-5.036-3.711H.957v2.332A8.997 8.997 0 0 0 9 18z" fill="#34A853"/>
  <path d="M3.964 10.71A5.41 5.41 0 0 1 3.682 9c0-.593.102-1.17.282-1.71V4.958H.957A8.996 8.996 0 0 0 0 9c0 1.452.348 2.827.957 4.042l3.007-2.332z" fill="#FBBC05"/>
  <path d="M9 3.58c1.321 0 2.508.454 3.44 1.345l2.582-2.58C13.463.891 11.426 0 9 0A8.997 8.997 0 0 0 .957 4.958L3.964 7.29C4.672 5.163 6.656 3.58 9 3.58z" fill="#EA4335"/>
</svg>"""

# ---------------------------------------------------------------------------
# SHARED HEADER & FOOTER
# ---------------------------------------------------------------------------

def render_header(current_path="/hayder"):
    nav_links = [
        ("/hayder/features", "Features"),
        ("/hayder/how-it-works", "How It Works"),
        ("/hayder/security", "Security"),
        ("/hayder/pricing", "Pricing"),
        ("/hayder/about", "About"),
        ("/hayder/support", "Support"),
    ]
    links_html = []
    for href, label in nav_links:
        active_class = " active" if current_path == href else ""
        links_html.append(f'<a href="{href}" class="nav-link{active_class}">{label}</a>')

    return f"""<header class="site-header">
  <div class="header-container">
    <div class="brand-wrapper">
      <a href="/hayder" class="brand-logo" aria-label="Hayder home">
        {render_logo_svg(28, 28)}
        <span class="brand-title">HAYDER</span>
      </a>
      <span class="brand-badge">by Xorwia</span>
    </div>
    <nav class="main-nav" aria-label="Main Navigation">
      {''.join(links_html)}
      <div class="nav-cta-group">
        <a href="/voice" class="btn btn-secondary btn-sm" aria-label="Open Voice Assistant">Open Voice</a>
        <a href="/oauth/google/connect" class="btn btn-primary btn-sm" aria-label="Connect Google Account">Connect Google</a>
      </div>
    </nav>
  </div>
</header>"""

def render_footer():
    return f"""<footer class="site-footer">
  <div class="footer-container">
    <div class="footer-grid">
      <div>
        <div class="brand-logo" style="margin-bottom: 14px;">
          {render_logo_svg(24, 24)}
          <span class="brand-title" style="font-size: 16px;">HAYDER</span>
          <span class="brand-badge">by Xorwia</span>
        </div>
        <p style="font-size: 14px; color: var(--text-secondary); max-width: 320px; line-height: 1.5; margin-bottom: 16px;">
          Hayder is a personal operations assistant by Xorwia. It remembers, organizes your day, and prepares sensitive actions for explicit human approval.
        </p>
        <p style="font-size: 13px; color: var(--text-tertiary);">
          Support: <a href="mailto:hayder@xorwia.com" style="color: var(--google-blue);">hayder@xorwia.com</a>
        </p>
      </div>

      <div>
        <div class="footer-col-title">Product</div>
        <ul class="footer-nav">
          <li><a href="/hayder/features" class="footer-link">Features</a></li>
          <li><a href="/hayder/how-it-works" class="footer-link">How It Works</a></li>
          <li><a href="/hayder/security" class="footer-link">Security</a></li>
          <li><a href="/hayder/pricing" class="footer-link">Pricing</a></li>
          <li><a href="/voice" class="footer-link">Voice Assistant</a></li>
        </ul>
      </div>

      <div>
        <div class="footer-col-title">Company</div>
        <ul class="footer-nav">
          <li><a href="/hayder/about" class="footer-link">About</a></li>
          <li><a href="/hayder/support" class="footer-link">Support</a></li>
          <li><a href="mailto:hayder@xorwia.com" class="footer-link">Contact</a></li>
        </ul>
      </div>

      <div>
        <div class="footer-col-title">Legal</div>
        <ul class="footer-nav">
          <li><a href="/privacy" class="footer-link">Privacy</a></li>
          <li><a href="/terms" class="footer-link">Terms</a></li>
        </ul>
      </div>
    </div>

    <div class="footer-bottom">
      <div>Hayder is a product by Xorwia. &copy; 2026 Xorwia. All rights reserved.</div>
      <div style="font-size: 12px; color: var(--text-light);">
        Single-account Google integration &middot; Phase 1 release
      </div>
    </div>
  </div>
</footer>"""

def render_html_shell(title, content, current_path="/hayder", extra_head="", extra_scripts=""):
    return f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>{html.escape(title)} — Hayder by Xorwia</title>
  <meta name="description" content="Hayder is the calm operations assistant by Xorwia. Unifies your morning briefing across Gmail and Google Calendar with guaranteed human approval before sensitive actions.">
  <style>
{SHARED_CSS}
  </style>
{extra_head}
</head>
<body>
{render_header(current_path)}
<main class="main-content">
{content}
</main>
{render_footer()}
{extra_scripts}
</body>
</html>"""

# ---------------------------------------------------------------------------
# PAGE 1: /hayder (HOME / LANDING PAGE)
# ---------------------------------------------------------------------------

def render_home_page():
    content = f"""
<section class="section-hero">
  <div class="container-narrow">
    <div style="display: inline-flex; align-items: center; gap: 8px; background: var(--bg-surface); border: 1px solid var(--border-subtle); padding: 6px 14px; border-radius: 9999px; font-size: 13px; font-weight: 500; color: var(--text-secondary); margin-bottom: 24px;">
      <span style="width: 8px; height: 8px; border-radius: 50%; background: var(--google-blue);"></span>
      Hayder by Xorwia &middot; Phase 1
    </div>

    <h1 class="hero-title">The operations assistant that prepares. You approve.</h1>
    <p class="hero-subtitle">
      Hayder unifies your daily briefing across Gmail and Google Calendar. It organizes your morning, drafts replies, and prepares sensitive actions for your explicit approval—so you never lose context or send the wrong message.
    </p>

    <div style="display: flex; gap: 14px; justify-content: center; flex-wrap: wrap; margin-bottom: 24px;">
      <a href="/oauth/google/connect" class="btn btn-google btn-lg" aria-label="Connect with Google">
        {render_google_icon_svg()}
        Connect with Google
      </a>
      <a href="/voice" class="btn btn-primary btn-lg" aria-label="Open Voice Assistant">
        Try Voice Assistant
      </a>
    </div>

    <div class="reassurance-strip">
      <span class="reassurance-item">
        <svg width="16" height="16" viewBox="0 0 16 16" fill="currentColor" style="color: var(--google-blue);"><path d="M13.78 4.22a.75.75 0 0 1 0 1.06l-7.25 7.25a.75.75 0 0 1-1.06 0L2.22 9.28a.75.75 0 0 1 1.06-1.06L6 10.94l6.72-6.72a.75.75 0 0 1 1.06 0z"/></svg>
        Single verified Google account
      </span>
      <span class="reassurance-item">
        <svg width="16" height="16" viewBox="0 0 16 16" fill="currentColor" style="color: var(--google-blue);"><path d="M13.78 4.22a.75.75 0 0 1 0 1.06l-7.25 7.25a.75.75 0 0 1-1.06 0L2.22 9.28a.75.75 0 0 1 1.06-1.06L6 10.94l6.72-6.72a.75.75 0 0 1 1.06 0z"/></svg>
        Strict approval before action
      </span>
      <span class="reassurance-item">
        <svg width="16" height="16" viewBox="0 0 16 16" fill="currentColor" style="color: var(--google-blue);"><path d="M13.78 4.22a.75.75 0 0 1 0 1.06l-7.25 7.25a.75.75 0 0 1-1.06 0L2.22 9.28a.75.75 0 0 1 1.06-1.06L6 10.94l6.72-6.72a.75.75 0 0 1 1.06 0z"/></svg>
        Zero autonomous email sends
      </span>
    </div>
  </div>
</section>

<!-- Product UI Preview -->
<section class="section" style="padding-top: 0;">
  <div class="container">
    <div class="preview-card">
      <div class="preview-header">
        <div class="preview-dots">
          <div class="preview-dot"></div>
          <div class="preview-dot"></div>
          <div class="preview-dot"></div>
        </div>
        <div class="preview-title-bar">
          {render_logo_svg(16, 16)}
          <span>Hayder Operational Surface &middot; Active Daily Briefing</span>
        </div>
        <div style="font-size: 12px; color: var(--text-tertiary); font-weight: 500;">
          user@example.com
        </div>
      </div>

      <div class="preview-body">
        <div class="preview-briefing-card">
          <div style="display: flex; align-items: center; justify-content: space-between; margin-bottom: 12px;">
            <div style="font-size: 14px; font-weight: 600; color: var(--text-primary);">Morning Focus &middot; Today</div>
            <div style="font-size: 12px; color: var(--text-tertiary);">Generated 08:30 AM</div>
          </div>
          <div class="preview-item">
            <span class="preview-item-icon">📩</span>
            <div style="font-size: 14px;">
              <strong style="color: var(--text-primary);">2 priority emails waiting:</strong> Alex requested project review by 2 PM; Sarah confirmed partnership call for Thursday.
            </div>
          </div>
          <div class="preview-item">
            <span class="preview-item-icon">📅</span>
            <div style="font-size: 14px;">
              <strong style="color: var(--text-primary);">Next meeting at 11:00 AM:</strong> Q3 Strategic Roadmap with Engineering (45m).
            </div>
          </div>
          <div class="preview-item">
            <span class="preview-item-icon">📝</span>
            <div style="font-size: 14px;">
              <strong style="color: var(--text-primary);">Open commitment:</strong> "Send revised invoice to client" is due today.
            </div>
          </div>
        </div>

        <div class="approval-stage-card">
          <div class="approval-stage-header">
            <div style="display: flex; align-items: center; gap: 8px;">
              <span style="font-size: 14px; font-weight: 600; color: #92400e;">⚠️ Action Staged for Human Approval</span>
            </div>
            <span class="badge-waiting">WAITING_APPROVAL</span>
          </div>

          <div style="font-size: 13px; color: var(--text-secondary); margin-bottom: 12px; background: #ffffff; border: 1px solid #fed7aa; border-radius: 8px; padding: 12px;">
            <div><strong>To:</strong> alex@company.com</div>
            <div><strong>Subject:</strong> Re: Project Checkpoint &amp; Milestone Timeline</div>
            <div style="margin-top: 6px; color: var(--text-tertiary);">"Hi Alex, the project checkpoint has been recorded and the next milestone is scheduled for Friday. Let me know if you need anything further."</div>
          </div>

          <div style="display: flex; align-items: center; justify-content: space-between; flex-wrap: gap;">
            <span style="font-size: 12px; color: #92400e;">Hayder will never dispatch this message without your explicit approval click.</span>
            <div class="approval-actions">
              <span class="btn btn-secondary btn-sm" style="color: var(--pulse-rose); border-color: #fecdd3;">Reject</span>
              <span class="btn btn-primary btn-sm" style="background: #15803d; border-color: #15803d;">Approve &amp; Send</span>
            </div>
          </div>
        </div>
      </div>
    </div>
  </div>
</section>

<!-- Heartbeat Motif & Voice Interaction Preview -->
<section class="section" style="background: var(--bg-surface); border-top: 1px solid var(--border-subtle); border-bottom: 1px solid var(--border-subtle);">
  <div class="container">
    <h2 class="section-title">A calm, human-like voice experience</h2>
    <p class="section-subtitle">
      Hayder speaks and listens with natural cadence. The subtle multicolour heartbeat reflects Hayder's exact operational state.
    </p>

    <div class="voice-demo-container">
      <div id="demoCore" class="voice-core-orb">
        <div id="demoPulseRing" class="heartbeat-pulse-ring"></div>
        {render_logo_svg(36, 36)}
      </div>

      <div id="demoStateLabel" style="font-size: 14px; font-weight: 600; color: var(--text-primary); margin-bottom: 4px;">
        State: Idle
      </div>
      <div id="demoStateDesc" style="font-size: 13px; color: var(--text-tertiary); margin-bottom: 18px;">
        Calm resting breath. Ready to listen or process instructions.
      </div>

      <div style="margin-bottom: 24px;">
        <button id="demoAudioBtn" class="btn btn-secondary btn-sm" style="display: inline-flex; gap: 8px;">
          <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><polygon points="11 5 6 9 2 9 2 15 6 15 11 19 11 5"></polygon><path d="M19.07 4.93a10 10 0 0 1 0 14.14M15.54 8.46a5 5 0 0 1 0 7.07"></path></svg>
          Hear Hayder's Voice Sample
        </button>
      </div>

      <div style="font-size: 12px; font-weight: 600; text-transform: uppercase; letter-spacing: 0.05em; color: var(--text-tertiary); margin-bottom: 10px;">
        Interactive Voice State Preview
      </div>
      <div class="voice-state-controls">
        <button class="state-pill active" onclick="setDemoState('idle')">1. Idle</button>
        <button class="state-pill" onclick="setDemoState('listening')">2. Listening</button>
        <button class="state-pill" onclick="setDemoState('thinking')">3. Thinking</button>
        <button class="state-pill" onclick="setDemoState('speaking')">4. Speaking</button>
        <button class="state-pill" onclick="setDemoState('reconnect')">5. Reconnect Required</button>
        <button class="state-pill" onclick="setDemoState('error')">6. Error</button>
      </div>

      <div style="margin-top: 32px; padding-top: 24px; border-top: 1px solid var(--border-subtle);">
        <a href="/voice" class="btn btn-primary" style="width: 100%; max-width: 320px;">
          Launch Hayder Voice Assistant &rarr;
        </a>
      </div>
    </div>
  </div>
</section>

<!-- Core Benefits -->
<section class="section">
  <div class="container">
    <h2 class="section-title">Built for absolute control and clarity</h2>
    <p class="section-subtitle">
      Eliminate context fragmentation without surrendering human agency.
    </p>

    <div class="grid-2">
      <div class="card">
        <div class="card-icon-wrap">☀️</div>
        <h3 class="card-title">Daily Attention Briefing</h3>
        <p style="color: var(--text-secondary); font-size: 15px;">
          Synthesizes your priority unread Gmail threads and upcoming Google Calendar schedule into a single, cohesive morning update. No scanning ten tabs to know what matters.
        </p>
      </div>

      <div class="card">
        <div class="card-icon-wrap">🛡️</div>
        <h3 class="card-title">Strict Human Approval</h3>
        <p style="color: var(--text-secondary); font-size: 15px;">
          Read-only contextual awareness is automated, but external actions are staged. Hayder prepares exact drafts; you review and explicitly click Approve before anything is sent.
        </p>
      </div>

      <div class="card">
        <div class="card-icon-wrap">🎙️</div>
        <h3 class="card-title">Consistent Natural Voice</h3>
        <p style="color: var(--text-secondary); font-size: 15px;">
          Interact naturally through browser-native speech recognition and calm voice synthesis. One consistent, professional assistant voice across the entire product.
        </p>
      </div>

      <div class="card">
        <div class="card-icon-wrap">🔒</div>
        <h3 class="card-title">Single-Account Security</h3>
        <p style="color: var(--text-secondary); font-size: 15px;">
          Phase 1 is strictly locked to a single verified Google account per user. This prevents multi-account confusion, credential leakage, and cross-account data commingling.
        </p>
      </div>
    </div>
  </div>
</section>

<!-- Call to Action Banner -->
<section class="section" style="background: var(--bg-surface); border-top: 1px solid var(--border-subtle); text-align: center;">
  <div class="container-narrow">
    <h2 class="section-title" style="margin-bottom: 16px;">Ready to reclaim your morning focus?</h2>
    <p class="section-subtitle" style="margin-bottom: 32px;">
      Get started with Hayder Pro today. Connect your Google account securely in less than a minute.
    </p>
    <div style="display: flex; gap: 14px; justify-content: center; flex-wrap: wrap;">
      <a href="/oauth/google/connect" class="btn btn-google btn-lg" aria-label="Connect with Google">
        {render_google_icon_svg()}
        Connect with Google
      </a>
      <a href="/hayder/pricing" class="btn btn-secondary btn-lg">
        View Pricing Details
      </a>
    </div>
  </div>
</section>
"""

    extra_scripts = """
<script>
const demoStates = {
  idle: {
    label: "State: Idle",
    desc: "Calm resting breath. Ready to listen or process instructions.",
    border: "var(--border-subtle)",
    ringColor: "var(--google-blue)",
    ringAnim: "pulse-ring 3s ease-in-out infinite"
  },
  listening: {
    label: "State: Listening",
    desc: "Microphone active. Hayder is capturing your natural speech.",
    border: "var(--google-blue)",
    ringColor: "var(--pulse-cyan)",
    ringAnim: "pulse-ring 1.2s ease-in-out infinite"
  },
  thinking: {
    label: "State: Thinking",
    desc: "Analyzing context across your Gmail, calendar, and commitments.",
    border: "var(--pulse-violet)",
    ringColor: "var(--pulse-violet)",
    ringAnim: "pulse-ring 0.8s linear infinite"
  },
  speaking: {
    label: "State: Speaking",
    desc: "Hayder is speaking the response with calm, natural cadence.",
    border: "var(--pulse-cyan)",
    ringColor: "var(--google-blue)",
    ringAnim: "pulse-ring 1.5s ease-in-out infinite"
  },
  reconnect: {
    label: "State: Reconnect Required",
    desc: "Google session needs renewal. Clear notification with one-click reconnect.",
    border: "var(--pulse-amber)",
    ringColor: "var(--pulse-amber)",
    ringAnim: "none"
  },
  error: {
    label: "State: Error",
    desc: "Network or processing issue encountered. Clean message with retry option.",
    border: "var(--pulse-rose)",
    ringColor: "var(--pulse-rose)",
    ringAnim: "none"
  }
};

function setDemoState(stateKey) {
  const cfg = demoStates[stateKey] || demoStates.idle;
  const core = document.getElementById("demoCore");
  const ring = document.getElementById("demoPulseRing");
  const label = document.getElementById("demoStateLabel");
  const desc = document.getElementById("demoStateDesc");

  core.style.borderColor = cfg.border;
  ring.style.borderColor = cfg.ringColor;
  ring.style.animation = cfg.ringAnim;
  label.textContent = cfg.label;
  desc.textContent = cfg.desc;

  document.querySelectorAll(".state-pill").forEach(pill => {
    pill.classList.remove("active");
  });
  const activeBtn = Array.from(document.querySelectorAll(".state-pill")).find(p => p.textContent.toLowerCase().includes(stateKey));
  if (activeBtn) activeBtn.classList.add("active");
}

document.getElementById("demoAudioBtn").addEventListener("click", () => {
  if (!("speechSynthesis" in window)) {
    alert("Speech synthesis is not available in your browser.");
    return;
  }
  window.speechSynthesis.cancel();
  setDemoState("speaking");
  const text = "Good morning. Here is your daily briefing: you have two unread client emails and your next meeting starts at 2 PM. I have prepared a draft reply for your approval.";
  const utt = new SpeechSynthesisUtterance(text);
  utt.rate = 0.96;
  utt.pitch = 1;
  utt.lang = "en-GB";

  utt.onend = () => {
    setDemoState("idle");
  };
  utt.onerror = () => {
    setDemoState("idle");
  };
  window.speechSynthesis.speak(utt);
});
</script>
"""
    return render_html_shell("Hayder — Operations Assistant by Xorwia", content, current_path="/hayder", extra_scripts=extra_scripts)

# ---------------------------------------------------------------------------
# PAGE 2: /hayder/features
# ---------------------------------------------------------------------------

def render_features_page():
    content = f"""
<section class="section-hero">
  <div class="container-narrow">
    <h1 class="hero-title">Features built for real operational work</h1>
    <p class="hero-subtitle">
      Only capabilities that are active and tested in Phase 1. No hypothetical roadmap claims.
    </p>
  </div>
</section>

<section class="section" style="padding-top: 0;">
  <div class="container">
    <div class="grid-2" style="gap: 32px;">

      <div class="card">
        <div class="card-icon-wrap">📧</div>
        <h2 class="card-title" style="font-size: 21px; margin-bottom: 12px;">Gmail &amp; Email Assistance</h2>
        <p style="color: var(--text-secondary); margin-bottom: 16px;">
          Hayder securely monitors your single connected Gmail inbox to surface urgent communications and organize your pending replies.
        </p>
        <ul style="list-style: none; display: flex; flex-direction: column; gap: 10px; font-size: 14px; color: var(--text-secondary);">
          <li style="display: flex; gap: 8px;">&bull; <span><strong>Inbox scanning:</strong> Surfaces latest messages and threads requiring follow-up.</span></li>
          <li style="display: flex; gap: 8px;">&bull; <span><strong>Draft preparation:</strong> Prepares precise email draft replies using your existing email context.</span></li>
          <li style="display: flex; gap: 8px;">&bull; <span><strong>Zero autonomous sends:</strong> Every drafted email requires explicit human confirmation before dispatch.</span></li>
        </ul>
      </div>

      <div class="card">
        <div class="card-icon-wrap">📅</div>
        <h2 class="card-title" style="font-size: 21px; margin-bottom: 12px;">Google Calendar Awareness</h2>
        <p style="color: var(--text-secondary); margin-bottom: 16px;">
          Real-time awareness of your daily and upcoming schedule, helping you manage preparation time between commitments.
        </p>
        <ul style="list-style: none; display: flex; flex-direction: column; gap: 10px; font-size: 14px; color: var(--text-secondary);">
          <li style="display: flex; gap: 8px;">&bull; <span><strong>Today's agenda:</strong> Instant overview of today's meetings, start times, and durations.</span></li>
          <li style="display: flex; gap: 8px;">&bull; <span><strong>Next event countdown:</strong> Real-time clarity on how much focus time remains before your next meeting.</span></li>
          <li style="display: flex; gap: 8px;">&bull; <span><strong>Attendee context:</strong> Read-only awareness of meeting descriptions and participants.</span></li>
        </ul>
      </div>

      <div class="card">
        <div class="card-icon-wrap">🌅</div>
        <h2 class="card-title" style="font-size: 21px; margin-bottom: 12px;">Daily Briefing &amp; Attention Engine</h2>
        <p style="color: var(--text-secondary); margin-bottom: 16px;">
          Ask "What needs my attention?" and receive an orchestrated, actionable briefing synthesized across all connected work streams.
        </p>
        <ul style="list-style: none; display: flex; flex-direction: column; gap: 10px; font-size: 14px; color: var(--text-secondary);">
          <li style="display: flex; gap: 8px;">&bull; <span><strong>Unified morning briefing:</strong> Combines inbox urgency, schedule milestones, and active commitments.</span></li>
          <li style="display: flex; gap: 8px;">&bull; <span><strong>Noise reduction:</strong> Distinguishes actionable operational priorities from marketing newsletters and chatter.</span></li>
          <li style="display: flex; gap: 8px;">&bull; <span><strong>Memory checkpoints:</strong> Retains active project checkpoint context so you never restart from scratch.</span></li>
        </ul>
      </div>

      <div class="card">
        <div class="card-icon-wrap">🛡️</div>
        <h2 class="card-title" style="font-size: 21px; margin-bottom: 12px;">Human Approval Before Sensitive Actions</h2>
        <p style="color: var(--text-secondary); margin-bottom: 16px;">
          Hayder's fundamental safety contract: AI prepares, but the human retains complete execution authority.
        </p>
        <ul style="list-style: none; display: flex; flex-direction: column; gap: 10px; font-size: 14px; color: var(--text-secondary);">
          <li style="display: flex; gap: 8px;">&bull; <span><strong>Staged approval state:</strong> Actions enter <code>WAITING_APPROVAL</code> in DynamoDB with recipient and body details.</span></li>
          <li style="display: flex; gap: 8px;">&bull; <span><strong>Explicit decision cards:</strong> Click Approve to execute via Gmail API, or Reject to discard safely.</span></li>
          <li style="display: flex; gap: 8px;">&bull; <span><strong>Verifiable audit record:</strong> Approval records store timestamp and user identity for peace of mind.</span></li>
        </ul>
      </div>

      <div class="card" style="grid-column: 1 / -1;">
        <div class="card-icon-wrap">🎙️</div>
        <h2 class="card-title" style="font-size: 21px; margin-bottom: 12px;">Calm Voice &amp; Chat Interface</h2>
        <p style="color: var(--text-secondary); margin-bottom: 16px;">
          A hands-free, natural voice interaction built into your browser, powered by SpeechRecognition and calibrated speech synthesis.
        </p>
        <div class="grid-3" style="gap: 16px; margin-top: 16px;">
          <div style="background: var(--bg-surface); padding: 16px; border-radius: 10px; border: 1px solid var(--border-subtle);">
            <strong style="display: block; font-size: 14px; margin-bottom: 6px; color: var(--text-primary);">Natural Human Voice</strong>
            <span style="font-size: 13px; color: var(--text-secondary);">Calm, measured speech rate with short sentence chunks for clarity. No robotic welcome persona.</span>
          </div>
          <div style="background: var(--bg-surface); padding: 16px; border-radius: 10px; border: 1px solid var(--border-subtle);">
            <strong style="display: block; font-size: 14px; margin-bottom: 6px; color: var(--text-primary);">Multicolour Heartbeat Feedback</strong>
            <span style="font-size: 13px; color: var(--text-secondary);">Visual status ring transitions seamlessly between idle, listening, thinking, and speaking.</span>
          </div>
          <div style="background: var(--bg-surface); padding: 16px; border-radius: 10px; border: 1px solid var(--border-subtle);">
            <strong style="display: block; font-size: 14px; margin-bottom: 6px; color: var(--text-primary);">Voice or Text Flexibility</strong>
            <span style="font-size: 13px; color: var(--text-secondary);">Speak naturally with your microphone or type precision commands in the same streamlined view.</span>
          </div>
        </div>
      </div>

    </div>

    <div style="margin-top: 56px; text-align: center;">
      <a href="/oauth/google/connect" class="btn btn-google btn-lg" aria-label="Connect with Google">
        {render_google_icon_svg()}
        Connect with Google to Get Started
      </a>
    </div>
  </div>
</section>
"""
    return render_html_shell("Features — Hayder by Xorwia", content, current_path="/hayder/features")

# ---------------------------------------------------------------------------
# PAGE 3: /hayder/how-it-works
# ---------------------------------------------------------------------------

def render_how_it_works_page():
    content = f"""
<section class="section-hero">
  <div class="container-narrow">
    <h1 class="hero-title">How Hayder works</h1>
    <p class="hero-subtitle">
      A transparent walkthrough of how Hayder integrates with your single Google account, analyzes context, and safely executes work under your supervision.
    </p>
  </div>
</section>

<section class="section" style="padding-top: 0;">
  <div class="container-narrow">
    <div style="display: flex; flex-direction: column; gap: 32px;">

      <div class="card" style="display: flex; gap: 24px;">
        <div style="flex-shrink: 0; width: 44px; height: 44px; border-radius: 50%; background: var(--primary-button); color: #ffffff; display: flex; align-items: center; justify-content: center; font-weight: 700;">1</div>
        <div>
          <h2 class="card-title">Connect Google via Official OAuth 2.0</h2>
          <p style="color: var(--text-secondary); font-size: 15px; margin-top: 6px;">
            You authorize Hayder with your single Google account. Google provides an OAuth token granting read-only access to your Gmail messages and Google Calendar events, plus drafting permissions. Hayder never sees or stores your Google password.
          </p>
        </div>
      </div>

      <div class="card" style="display: flex; gap: 24px;">
        <div style="flex-shrink: 0; width: 44px; height: 44px; border-radius: 50%; background: var(--primary-button); color: #ffffff; display: flex; align-items: center; justify-content: center; font-weight: 700;">2</div>
        <div>
          <h2 class="card-title">Hayder Understands Email &amp; Calendar Context</h2>
          <p style="color: var(--text-secondary); font-size: 15px; margin-top: 6px;">
            Hayder reads your recent unread emails, threads awaiting response, and upcoming calendar appointments. It builds a structured operational snapshot of what requires attention, without altering your inbox.
          </p>
        </div>
      </div>

      <div class="card" style="display: flex; gap: 24px;">
        <div style="flex-shrink: 0; width: 44px; height: 44px; border-radius: 50%; background: var(--primary-button); color: #ffffff; display: flex; align-items: center; justify-content: center; font-weight: 700;">3</div>
        <div>
          <h2 class="card-title">Ask Naturally by Chat or Voice</h2>
          <p style="color: var(--text-secondary); font-size: 15px; margin-top: 6px;">
            Ask questions like "What needs my attention?", "What is my next meeting?", or "Draft an email to Alex confirming Friday's deadline". Hayder parses your intent, checks your live data, and drafts the required action.
          </p>
        </div>
      </div>

      <div class="card" style="display: flex; gap: 24px;">
        <div style="flex-shrink: 0; width: 44px; height: 44px; border-radius: 50%; background: var(--primary-button); color: #ffffff; display: flex; align-items: center; justify-content: center; font-weight: 700;">4</div>
        <div>
          <h2 class="card-title">Hayder Prepares Actions</h2>
          <p style="color: var(--text-secondary); font-size: 15px; margin-top: 6px;">
            Rather than sending messages autonomously, Hayder stages the exact payload. It records the action with recipient, subject, and body in a secured DynamoDB approval store with status <code>WAITING_APPROVAL</code>.
          </p>
        </div>
      </div>

      <div class="card" style="display: flex; gap: 24px;">
        <div style="flex-shrink: 0; width: 44px; height: 44px; border-radius: 50%; background: var(--primary-button); color: #ffffff; display: flex; align-items: center; justify-content: center; font-weight: 700;">5</div>
        <div>
          <h2 class="card-title">User Approves Sensitive Actions</h2>
          <p style="color: var(--text-secondary); font-size: 15px; margin-top: 6px;">
            You inspect the staged action card. If the recipient or wording requires modification, you adjust it. When satisfied, you explicitly confirm by clicking Approve or saying "Approve it".
          </p>
        </div>
      </div>

      <div class="card" style="display: flex; gap: 24px;">
        <div style="flex-shrink: 0; width: 44px; height: 44px; border-radius: 50%; background: var(--primary-button); color: #ffffff; display: flex; align-items: center; justify-content: center; font-weight: 700;">6</div>
        <div>
          <h2 class="card-title">Action Executes Safely</h2>
          <p style="color: var(--text-secondary); font-size: 15px; margin-top: 6px;">
            Only upon verified user approval does Hayder call the Gmail API to dispatch the message. The approval record is marked <code>COMPLETED</code> and saved to your project history.
          </p>
        </div>
      </div>

    </div>

    <div style="margin-top: 48px; text-align: center;">
      <a href="/oauth/google/connect" class="btn btn-google btn-lg" aria-label="Connect with Google">
        {render_google_icon_svg()}
        Connect with Google
      </a>
    </div>
  </div>
</section>
"""
    return render_html_shell("How It Works — Hayder by Xorwia", content, current_path="/hayder/how-it-works")

# ---------------------------------------------------------------------------
# PAGE 4: /hayder/security
# ---------------------------------------------------------------------------

def render_security_page():
    content = f"""
<section class="section-hero">
  <div class="container-narrow">
    <h1 class="hero-title">Security &amp; Privacy</h1>
    <p class="hero-subtitle">
      Architected around user control, minimal privilege, and explicit approval before any external write.
    </p>
  </div>
</section>

<section class="section" style="padding-top: 0;">
  <div class="container-narrow">
    <div style="display: flex; flex-direction: column; gap: 28px;">

      <div class="card">
        <h2 class="card-title" style="margin-bottom: 10px;">Google OAuth 2.0 Integration</h2>
        <p style="color: var(--text-secondary); font-size: 15px; line-height: 1.6;">
          Hayder authenticates through official Google OAuth 2.0 flows. You authenticate directly on Google's domain; your Google credentials and passwords are never handled, seen, or stored by Hayder. Tokens are securely stored in AWS Secrets Manager and refreshed using secure cryptographic tokens.
        </p>
      </div>

      <div class="card">
        <h2 class="card-title" style="margin-bottom: 10px;">User Control &amp; Revocation</h2>
        <p style="color: var(--text-secondary); font-size: 15px; line-height: 1.6;">
          You remain in total control of your data authorizations at all times. You can disconnect your Google account from Hayder at any time, or revoke Hayder's permissions instantly via Google Account Security Settings. When revoked, token access ceases immediately.
        </p>
      </div>

      <div class="card">
        <h2 class="card-title" style="margin-bottom: 10px;">The Approval-Before-Action Model</h2>
        <p style="color: var(--text-secondary); font-size: 15px; line-height: 1.6;">
          Autonomous AI agents making unvetted external writes present severe operational risks. Hayder's architecture strictly separates read analysis from write actions. Email drafting creates a pending approval record. No email is ever sent unless a human explicitly approves the action.
        </p>
      </div>

      <div class="card">
        <h2 class="card-title" style="margin-bottom: 10px;">Single Google Account Boundary</h2>
        <p style="color: var(--text-secondary); font-size: 15px; line-height: 1.6;">
          To eliminate cross-account contamination or inadvertent disclosure, Hayder enforces a strict single Google account policy per user in Phase 1. Multi-account routing is deliberately not supported in this release.
        </p>
      </div>

      <div class="card">
        <h2 class="card-title" style="margin-bottom: 10px;">Privacy-Focused Infrastructure</h2>
        <p style="color: var(--text-secondary); font-size: 15px; line-height: 1.6; margin-bottom: 12px;">
          Hayder is hosted on AWS serverless infrastructure with AWS Cognito user authentication, encrypted DynamoDB data tables at rest, and TLS/HTTPS in transit. We do not sell user data, and we do not use your private emails or calendar data to train public foundation models.
        </p>
        <div style="background: var(--bg-surface); border: 1px solid var(--border-subtle); border-radius: 8px; padding: 14px; font-size: 13px; color: var(--text-tertiary);">
          <strong>Transparent disclosure:</strong> Hayder adheres strictly to Google API Services User Data Policy, including Limited Use requirements. We state our actual AWS and OAuth controls clearly and do not make unverified compliance claims (such as SOC 2 or GDPR certification badges).
        </div>
      </div>

    </div>

    <div style="margin-top: 48px; text-align: center;">
      <p style="font-size: 14px; color: var(--text-tertiary); margin-bottom: 16px;">
        Questions about privacy or security? Contact our security team directly:
      </p>
      <a href="mailto:hayder@xorwia.com?subject=Security%20Inquiry" class="btn btn-secondary">
        Contact hayder@xorwia.com
      </a>
    </div>
  </div>
</section>
"""
    return render_html_shell("Security — Hayder by Xorwia", content, current_path="/hayder/security")

# ---------------------------------------------------------------------------
# PAGE 5: /hayder/pricing
# ---------------------------------------------------------------------------

def render_pricing_page():
    content = f"""
<section class="section-hero">
  <div class="container-narrow">
    <h1 class="hero-title">Simple, transparent pricing</h1>
    <p class="hero-subtitle">
      Experience complete daily operational clarity with guaranteed human approval.
    </p>
  </div>
</section>

<section class="section" style="padding-top: 0;">
  <div class="container">
    <div class="grid-2" style="max-width: 880px; margin: 0 auto; gap: 32px; align-items: stretch;">

      <!-- Hayder Pro Tier (Active Phase 1) -->
      <div class="pricing-card">
        <div class="pricing-badge">Phase 1 Launch</div>
        <h2 style="font-size: 24px; font-weight: 700; color: var(--text-primary);">Hayder Pro</h2>
        <p style="font-size: 15px; color: var(--text-secondary); margin-top: 4px;">
          For founders, leaders, and operators who need complete daily control over communications.
        </p>

        <div class="pricing-price">
          &pound;19.99 <span class="pricing-interval">/ month</span>
        </div>
        <div class="pricing-trial-note">
          Standard subscription &middot; Single Google account
        </div>

        <a href="/oauth/google/connect" class="btn btn-primary btn-lg" style="width: 100%; margin-bottom: 8px;" aria-label="Get Started">
          Get Started
        </a>
        <div style="font-size: 12px; color: var(--text-tertiary); text-align: center; margin-bottom: 24px;">
          Subscription checkout will be connected separately at launch &middot; Connects via Google OAuth
        </div>

        <div style="font-size: 13px; font-weight: 600; text-transform: uppercase; letter-spacing: 0.04em; color: var(--text-primary); margin-bottom: 12px;">
          What's included in Phase 1:
        </div>
        <ul class="pricing-features-list">
          <li class="pricing-feature-item">
            <span class="pricing-feature-check">&check;</span>
            <span><strong>Daily attention briefing:</strong> Prioritized inbox, agenda, and open items</span>
          </li>
          <li class="pricing-feature-item">
            <span class="pricing-feature-check">&check;</span>
            <span><strong>Gmail assistance:</strong> Unread scanning and contextual reply drafting</span>
          </li>
          <li class="pricing-feature-item">
            <span class="pricing-feature-check">&check;</span>
            <span><strong>Calendar awareness:</strong> Real-time schedule and countdown to next event</span>
          </li>
          <li class="pricing-feature-item">
            <span class="pricing-feature-check">&check;</span>
            <span><strong>Guaranteed human approval:</strong> Zero autonomous email dispatch</span>
          </li>
          <li class="pricing-feature-item">
            <span class="pricing-feature-check">&check;</span>
            <span><strong>Natural voice experience:</strong> Calm speech synthesis &amp; recognition</span>
          </li>
          <li class="pricing-feature-item">
            <span class="pricing-feature-check">&check;</span>
            <span><strong>Single Google account:</strong> Secure, isolated OAuth connection</span>
          </li>
          <li class="pricing-feature-item">
            <span class="pricing-feature-check">&check;</span>
            <span><strong>Direct email support:</strong> Help from the team via hayder@xorwia.com</span>
          </li>
        </ul>
      </div>

      <!-- Business Plan (Coming Later) -->
      <div class="card card-disabled" style="display: flex; flex-direction: column; justify-content: space-between; padding: 40px;">
        <div>
          <div style="display: inline-block; background: var(--border-strong); color: var(--text-primary); font-size: 12px; font-weight: 600; padding: 4px 12px; border-radius: 9999px; text-transform: uppercase; margin-bottom: 12px;">
            Coming Later
          </div>
          <h2 style="font-size: 24px; font-weight: 700; color: var(--text-primary);">Hayder Business</h2>
          <p style="font-size: 15px; color: var(--text-secondary); margin-top: 4px;">
            For growing executive teams and organizations needing collaborative workflows.
          </p>

          <div style="font-size: 32px; font-weight: 700; color: var(--text-tertiary); margin: 24px 0;">
            Coming later
          </div>

          <div style="font-size: 13px; font-weight: 600; text-transform: uppercase; letter-spacing: 0.04em; color: var(--text-primary); margin-bottom: 12px;">
            Planned capabilities:
          </div>
          <ul class="pricing-features-list">
            <li class="pricing-feature-item">
              <span style="color: var(--text-tertiary);">&bull;</span>
              <span>Multi-seat team accounts</span>
            </li>
            <li class="pricing-feature-item">
              <span style="color: var(--text-tertiary);">&bull;</span>
              <span>Centralized administrative billing</span>
            </li>
            <li class="pricing-feature-item">
              <span style="color: var(--text-tertiary);">&bull;</span>
              <span>Shared project checkpoints &amp; organizational memory</span>
            </li>
            <li class="pricing-feature-item">
              <span style="color: var(--text-tertiary);">&bull;</span>
              <span>Custom delegation &amp; approval workflows</span>
            </li>
          </ul>
        </div>

        <div style="margin-top: 32px;">
          <a href="mailto:hayder@xorwia.com?subject=Business%20Plan%20Waitlist" class="btn btn-secondary" style="width: 100%;">
            Register Interest for Business Plan
          </a>
        </div>
      </div>

    </div>

    <div style="text-align: center; margin-top: 48px; font-size: 14px; color: var(--text-tertiary);">
      Subscription billed monthly in GBP (&pound;) upon launch checkout. Requires single verified Google account.
    </div>
  </div>
</section>
"""
    return render_html_shell("Pricing — Hayder by Xorwia", content, current_path="/hayder/pricing")

# ---------------------------------------------------------------------------
# PAGE 6: /hayder/about
# ---------------------------------------------------------------------------

def render_about_page():
    content = f"""
<section class="section-hero">
  <div class="container-narrow">
    <h1 class="hero-title">About Hayder</h1>
    <p class="hero-subtitle">
      Hayder is a personal operations assistant built by Xorwia to reduce cognitive overhead and help operators stay firmly in control.
    </p>
  </div>
</section>

<section class="section" style="padding-top: 0;">
  <div class="container-narrow">
    <div style="display: flex; flex-direction: column; gap: 32px; font-size: 16px; color: var(--text-secondary); line-height: 1.7;">

      <div class="card">
        <h2 class="card-title" style="margin-bottom: 12px;">Hayder is a Xorwia Product</h2>
        <p style="margin-bottom: 12px;">
          <strong>Xorwia</strong> is the technology and legal entity behind Hayder. We build focused software systems engineered to solve operational friction without adding unneeded complexity or noisy abstractions.
        </p>
        <p>
          In Phase 1, Hayder is delivered directly under Xorwia's URL structure at <code>xorwia.com/hayder</code>, supported directly by the core engineering team.
        </p>
      </div>

      <div class="card">
        <h2 class="card-title" style="margin-bottom: 12px;">The Problem: Context Fragmentation</h2>
        <p style="margin-bottom: 12px;">
          Founders, executives, and leaders spend their mornings jumping between inbox triage, calendar adjustments, and task managers. By the time deep work begins, cognitive fatigue has already set in.
        </p>
        <p>
          Generic AI tools often swing between two extremes: passive chatbots that require repetitive prompting, or reckless autonomous agents that make assumptions and send unreviewed emails.
        </p>
      </div>

      <div class="card">
        <h2 class="card-title" style="margin-bottom: 12px;">Our Guiding Principle</h2>
        <blockquote style="font-size: 18px; font-style: italic; color: var(--text-primary); border-left: 3px solid var(--google-blue); padding-left: 18px; margin: 16px 0;">
          "Hayder remembers. Hayder prepares. You approve important actions."
        </blockquote>
        <p>
          We believe artificial intelligence should handle the heavy lifting of gathering context, correlating commitments, and drafting actions—while leaving ultimate execution authority with the human operator.
        </p>
      </div>

      <div class="card">
        <h2 class="card-title" style="margin-bottom: 12px;">Google-Like Simplicity</h2>
        <p>
          We reject bloated dashboards, confusing multi-tier navigation, and generic SaaS templates. Hayder offers a calm, minimal white surface with restrained colour and generous whitespace, so you can focus entirely on what matters today.
        </p>
      </div>

      <div style="text-align: center; margin-top: 24px;">
        <p style="font-size: 14px; color: var(--text-tertiary); margin-bottom: 12px;">
          For partnership or company inquiries, reach us at:
        </p>
        <a href="mailto:hayder@xorwia.com" class="btn btn-secondary">
          hayder@xorwia.com
        </a>
      </div>

    </div>
  </div>
</section>
"""
    return render_html_shell("About — Hayder by Xorwia", content, current_path="/hayder/about")

# ---------------------------------------------------------------------------
# PAGE 7: /hayder/support
# ---------------------------------------------------------------------------

def render_support_page():
    content = f"""
<section class="section-hero">
  <div class="container-narrow">
    <h1 class="hero-title">Support &amp; Help</h1>
    <p class="hero-subtitle">
      Direct assistance for your Hayder account and Google integration. Reach our core team at <a href="mailto:hayder@xorwia.com" style="color: var(--google-blue); font-weight: 500;">hayder@xorwia.com</a>.
    </p>
  </div>
</section>

<section class="section" style="padding-top: 0;">
  <div class="container-narrow">

    <div class="card" style="background: var(--bg-surface); text-align: center; padding: 36px 24px; margin-bottom: 48px;">
      <div style="font-size: 32px; margin-bottom: 12px;">✉️</div>
      <h2 style="font-size: 20px; font-weight: 700; color: var(--text-primary); margin-bottom: 6px;">
        Direct Email Support
      </h2>
      <p style="font-size: 15px; color: var(--text-secondary); margin-bottom: 18px;">
        We respond to all user inquiries directly. No automated chatbots or outsourced ticket queues.
      </p>
      <a href="mailto:hayder@xorwia.com" class="btn btn-primary btn-lg">
        Email hayder@xorwia.com
      </a>
    </div>

    <h2 class="section-title" style="text-align: left; font-size: 24px; margin-bottom: 24px;">
      Common Help Areas
    </h2>

    <div class="faq-list">

      <div class="faq-item">
        <h3 class="faq-question">1. Google Connection &amp; Reconnection</h3>
        <p class="faq-answer">
          <strong>Connecting:</strong> Click "Connect with Google" from the navigation bar or voice page to link your Google account.<br>
          <strong>Reconnection required:</strong> Google OAuth refresh tokens can expire or be revoked if security settings change. If Hayder displays a "Reconnect Required" notice, click the reconnect button to refresh your Google session securely without losing your Hayder account history.
        </p>
      </div>

      <div class="faq-item">
        <h3 class="faq-question">2. Account &amp; Access</h3>
        <p class="faq-answer">
          Hayder uses secure AWS Cognito authentication. You sign in with your email address and password. If you need to update credentials or encounter access issues, email us at <a href="mailto:hayder@xorwia.com" style="color: var(--google-blue);">hayder@xorwia.com</a>.
        </p>
      </div>

      <div class="faq-item">
        <h3 class="faq-question">3. Email Approvals</h3>
        <p class="faq-answer">
          When Hayder prepares an email, it places the action in a <code>WAITING_APPROVAL</code> stage. You will see the recipient, subject, and body clearly presented. The email is never sent until you explicitly click "Approve" or say "Approve it". You can reject any draft at any time.
        </p>
      </div>

      <div class="faq-item">
        <h3 class="faq-question">4. Voice Interaction &amp; Browser Microphone</h3>
        <p class="faq-answer">
          Hayder's voice experience uses browser-native speech recognition. Ensure you have granted microphone access to the site in your browser permissions (Chrome, Safari, Edge, or Firefox). For optimal audio playback, ensure speech synthesis is unmuted on your device.
        </p>
      </div>

      <div class="faq-item">
        <h3 class="faq-question">5. Privacy &amp; Data Questions</h3>
        <p class="faq-answer">
          Hayder only accesses data necessary to provide your briefing and draft assistance under Google's Limited Use policy. You can disconnect your Google account at any time, which terminates access immediately.
        </p>
      </div>

    </div>

    <div style="margin-top: 48px; text-align: center;">
      <a href="/hayder" class="btn btn-secondary">
        &larr; Return to Hayder Overview
      </a>
    </div>

  </div>
</section>
"""
    return render_html_shell("Support — Hayder by Xorwia", content, current_path="/hayder/support")

# ---------------------------------------------------------------------------
# PAGE 8: /privacy (SHARED LEGAL PAGE)
# NOTE: This document requires final business and legal review before
# commercial launch. Do not display "draft" prominently to public users.
# Do not invent unverified company details.
# ---------------------------------------------------------------------------

def render_privacy_page():
    content = f"""
<section class="section-hero" style="padding-bottom: 40px;">
  <div class="container-narrow">
    <h1 class="hero-title">Privacy Policy</h1>
    <p class="hero-subtitle">
      Last updated: September 2026 &middot; Xorwia
    </p>
  </div>
</section>

<section class="section" style="padding-top: 0;">
  <div class="container-narrow" style="font-size: 15px; color: var(--text-secondary); line-height: 1.7;">

    <div class="card" style="margin-bottom: 24px;">
      <h2 class="card-title">1. Introduction &amp; Entity</h2>
      <p>
        This Privacy Policy describes how Xorwia ("Xorwia", "we", "us", or "our") collects, uses, and protects information when you use Hayder ("the Service"), accessible at xorwia.com/hayder.
      </p>
    </div>

    <div class="card" style="margin-bottom: 24px;">
      <h2 class="card-title">2. Information We Collect</h2>
      <p style="margin-bottom: 12px;">
        <strong>Account Information:</strong> When you register, we collect your email address and authentication credentials managed securely via AWS Cognito.
      </p>
      <p style="margin-bottom: 12px;">
        <strong>Google User Data:</strong> When you choose to connect your Google account via OAuth 2.0, Hayder requests access to:
      </p>
      <ul style="margin-left: 20px; margin-bottom: 12px;">
        <li>Gmail read-only metadata and messages to compile your daily attention briefing.</li>
        <li>Gmail send/draft permissions solely to stage and dispatch emails you explicitly approve.</li>
        <li>Google Calendar read-only access to display today's upcoming meetings and schedule.</li>
      </ul>
      <p>
        <strong>Operational Checkpoints:</strong> Project checkpoints and staged approval records saved to DynamoDB to maintain ongoing context.
      </p>
    </div>

    <div class="card" style="margin-bottom: 24px;">
      <h2 class="card-title">3. Google API Limited Use Disclosure</h2>
      <p style="margin-bottom: 12px;">
        Hayder's use and transfer to any other app of information received from Google APIs will adhere to the <strong>Google API Services User Data Policy</strong>, including the Limited Use requirements.
      </p>
      <p style="margin-bottom: 12px;">
        Specifically:
      </p>
      <ul style="margin-left: 20px;">
        <li>We only use Google data to provide user-facing features that are prominent in the Hayder user interface.</li>
        <li>We do not transfer your Google data to third parties unless necessary to provide or improve these features, comply with applicable law, or as part of a merger.</li>
        <li>We do not use or transfer your Google data for serving ads, including retargeting, personalized, or interest-based advertising.</li>
        <li>We do not allow humans to read your data unless you have given explicit permission for specific messages or to resolve security investigations.</li>
        <li>We do not use Google user data to train generalized AI or ML models.</li>
      </ul>
    </div>

    <div class="card" style="margin-bottom: 24px;">
      <h2 class="card-title">4. Data Security</h2>
      <p>
        All communications utilize TLS/HTTPS in transit. Tokens and credentials are encrypted at rest using AWS Secrets Manager. User accounts are isolated and strictly bounded to a single verified Google account.
      </p>
    </div>

    <div class="card" style="margin-bottom: 24px;">
      <h2 class="card-title">5. Your Rights &amp; Revocation</h2>
      <p style="margin-bottom: 12px;">
        You have the right to access, rectify, or delete your personal data. You may disconnect your Google account from Hayder at any time or revoke access via <a href="https://myaccount.google.com/permissions" target="_blank" rel="noopener" style="color: var(--google-blue);">Google Security Permissions</a>.
      </p>
      <p>
        To request data deletion or account closure, contact us at <a href="mailto:hayder@xorwia.com" style="color: var(--google-blue);">hayder@xorwia.com</a>.
      </p>
    </div>

    <div class="card">
      <h2 class="card-title">6. Contact Information</h2>
      <p>
        For inquiries regarding this Privacy Policy:
      </p>
      <p style="margin-top: 8px;">
        <strong>Xorwia &middot; Hayder Operations</strong><br>
        Email: <a href="mailto:hayder@xorwia.com" style="color: var(--google-blue);">hayder@xorwia.com</a>
      </p>
    </div>

  </div>
</section>
"""
    return render_html_shell("Privacy Policy — Xorwia", content, current_path="/privacy")

# ---------------------------------------------------------------------------
# PAGE 9: /terms (SHARED LEGAL PAGE)
# NOTE: This document requires final business and legal review before
# commercial launch. Do not display "draft" prominently to public users.
# Do not invent unverified company details.
# ---------------------------------------------------------------------------

def render_terms_page():
    content = f"""
<section class="section-hero" style="padding-bottom: 40px;">
  <div class="container-narrow">
    <h1 class="hero-title">Terms of Service</h1>
    <p class="hero-subtitle">
      Last updated: September 2026 &middot; Xorwia
    </p>
  </div>
</section>

<section class="section" style="padding-top: 0;">
  <div class="container-narrow" style="font-size: 15px; color: var(--text-secondary); line-height: 1.7;">

    <div class="card" style="margin-bottom: 24px;">
      <h2 class="card-title">1. Agreement to Terms</h2>
      <p>
        These Terms of Service ("Terms") govern your use of Hayder ("the Service"), operated by Xorwia ("Xorwia", "we", "us"). By accessing or using the Service, you agree to be bound by these Terms.
      </p>
    </div>

    <div class="card" style="margin-bottom: 24px;">
      <h2 class="card-title">2. Nature of the Service &amp; Human Approval</h2>
      <p style="margin-bottom: 12px;">
        Hayder is an AI-assisted operational workflow tool. Hayder provides briefing summaries and drafts prospective actions for your review.
      </p>
      <p>
        <strong>Your Responsibility:</strong> You are solely responsible for reviewing and confirming any staged actions (including email recipients, subjects, and text) before approving execution. Xorwia is not responsible for the consequences of actions you explicitly approve.
      </p>
    </div>

    <div class="card" style="margin-bottom: 24px;">
      <h2 class="card-title">3. Subscriptions &amp; Payments</h2>
      <p style="margin-bottom: 12px;">
        <strong>Hayder Pro:</strong> Priced at &pound;19.99 per month. Commercial subscription checkout and billing will be connected separately upon formal product launch.
      </p>
      <p style="margin-bottom: 12px;">
        <strong>Account Connection:</strong> Connecting your Google account via OAuth does not initiate an active paid subscription or billing trial at this time.
      </p>
      <p>
        <strong>Cancellation:</strong> When commercial subscriptions are activated, you may cancel your subscription at any time, effective at the end of the current billing period.
      </p>
    </div>

    <div class="card" style="margin-bottom: 24px;">
      <h2 class="card-title">4. Acceptable Use</h2>
      <p style="margin-bottom: 12px;">
        You agree not to use Hayder to send unsolicited bulk communications (spam), engage in fraudulent or unlawful activities, or attempt to circumvent security boundaries.
      </p>
      <p>
        Hayder is strictly limited to a single Google account connection per user in Phase 1.
      </p>
    </div>

    <div class="card" style="margin-bottom: 24px;">
      <h2 class="card-title">5. Limitation of Liability</h2>
      <p>
        The Service is provided "as is" and "as available". To the maximum extent permitted by law, Xorwia shall not be liable for any indirect, incidental, special, or consequential damages resulting from your use of the Service.
      </p>
    </div>

    <div class="card">
      <h2 class="card-title">6. Governing Law &amp; Contact</h2>
      <p>
        These Terms shall be governed by and construed in accordance with the laws of the United Kingdom. For questions regarding these Terms, contact:
      </p>
      <p style="margin-top: 8px;">
        <strong>Xorwia &middot; Legal</strong><br>
        Email: <a href="mailto:hayder@xorwia.com" style="color: var(--google-blue);">hayder@xorwia.com</a>
      </p>
    </div>

  </div>
</section>
"""
    return render_html_shell("Terms of Service — Xorwia", content, current_path="/terms")

# ---------------------------------------------------------------------------
# ROUTE DISPATCHER
# ---------------------------------------------------------------------------

ROUTES = {
    "/hayder": render_home_page,
    "/hayder/": render_home_page,
    "/hayder/features": render_features_page,
    "/hayder/features/": render_features_page,
    "/hayder/how-it-works": render_how_it_works_page,
    "/hayder/how-it-works/": render_how_it_works_page,
    "/hayder/security": render_security_page,
    "/hayder/security/": render_security_page,
    "/hayder/pricing": render_pricing_page,
    "/hayder/pricing/": render_pricing_page,
    "/hayder/about": render_about_page,
    "/hayder/about/": render_about_page,
    "/hayder/support": render_support_page,
    "/hayder/support/": render_support_page,
    "/privacy": render_privacy_page,
    "/privacy/": render_privacy_page,
    "/terms": render_terms_page,
    "/terms/": render_terms_page,
}

def render_page(path):
    """
    Renders the appropriate page based on path.
    Returns standard Lambda proxy response dict.
    """
    normalized_path = path.rstrip("/") if path != "/" else "/"
    renderer = ROUTES.get(path) or ROUTES.get(normalized_path)

    if renderer:
        return {
            "statusCode": 200,
            "headers": {
                "content-type": "text/html; charset=utf-8",
                "cache-control": "public, max-age=300",
            },
            "body": renderer(),
        }

    # Clean 404 fallback
    content = f"""
<section class="section-hero">
  <div class="container-narrow">
    <h1 class="hero-title">Page not found</h1>
    <p class="hero-subtitle">The page you are looking for does not exist.</p>
    <a href="/hayder" class="btn btn-primary">Return to Hayder Home</a>
  </div>
</section>
"""
    return {
        "statusCode": 404,
        "headers": {
            "content-type": "text/html; charset=utf-8",
            "cache-control": "no-store",
        },
        "body": render_html_shell("Page Not Found", content, current_path=path),
    }
