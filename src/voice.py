"""
Hayder Voice Assistant & Public Web Route Handler.

Provides the polished, human-like voice experience for Hayder by Xorwia,
with Google-like minimal simplicity, subtle multicolour heartbeat animations,
and clear states for:
1. idle
2. listening
3. thinking
4. speaking
5. reconnect required
6. error

Preserves existing Phase 1 voice functionality and backend routing contracts.
Dispatches public website routes to web.py.
"""

import web

def render_voice_page():
    html = r"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Hayder Voice Assistant — Hayder by Xorwia</title>
<meta name="description" content="Hayder Voice Assistant: Speak or type naturally with guaranteed human approval before sensitive actions.">
<style>
""" + web.SHARED_CSS + r"""

/* Voice-specific Layout & Overrides */
.voice-shell {
    max-width: 720px;
    margin: 40px auto 60px;
    padding: 0 20px;
}

.voice-header-center {
    text-align: center;
    margin-bottom: 28px;
}

.voice-brand-title {
    font-size: 32px;
    font-weight: 700;
    letter-spacing: -0.01em;
    color: var(--text-primary);
    margin-bottom: 6px;
}

.voice-subtitle {
    color: var(--text-secondary);
    font-size: 15px;
}

/* Multicolour Heartbeat Core & 6 Visual States */
.core {
    width: 96px;
    height: 96px;
    margin: 24px auto 32px;
    border-radius: 50%;
    border: 2px solid var(--border-subtle);
    background: #ffffff;
    display: flex;
    align-items: center;
    justify-content: center;
    position: relative;
    box-shadow: 0 2px 8px rgba(0,0,0,0.04);
    transition: border-color 0.3s ease, box-shadow 0.3s ease;
}

.core-pulse-ring {
    position: absolute;
    width: 100%;
    height: 100%;
    border-radius: 50%;
    border: 2px solid var(--google-blue);
    opacity: 0.18;
    pointer-events: none;
    animation: breathe 3.5s ease-in-out infinite;
}

/* 1. Idle */
.core.idle .core-pulse-ring,
.core:not(.listening):not(.thinking):not(.speaking):not(.reconnect):not(.error) .core-pulse-ring {
    animation: breathe 3.5s ease-in-out infinite;
    border-color: var(--google-blue);
}

/* 2. Listening */
.core.listening {
    border-color: var(--google-blue);
    box-shadow: 0 0 0 4px rgba(26, 115, 232, 0.12);
}
.core.listening .core-pulse-ring {
    animation: listening-pulse 1.2s ease-in-out infinite;
    border-color: var(--pulse-cyan);
    opacity: 0.5;
}

/* 3. Thinking */
.core.thinking {
    border-color: var(--pulse-violet);
    box-shadow: 0 0 0 4px rgba(124, 58, 237, 0.12);
}
.core.thinking .core-pulse-ring {
    animation: thinking-spin 1s linear infinite;
    border-color: var(--pulse-violet);
    opacity: 0.55;
}

/* 4. Speaking */
.core.speaking {
    border-color: var(--pulse-cyan);
    box-shadow: 0 0 0 4px rgba(0, 172, 193, 0.15);
}
.core.speaking .core-pulse-ring {
    animation: speaking-wave 1.4s ease-in-out infinite;
    border-color: var(--google-blue);
    opacity: 0.55;
}

/* 5. Reconnect Required */
.core.reconnect {
    border-color: var(--pulse-amber);
    box-shadow: 0 0 0 4px rgba(245, 158, 11, 0.15);
}
.core.reconnect .core-pulse-ring {
    border-color: var(--pulse-amber);
    animation: none;
    opacity: 0.6;
}

/* 6. Error */
.core.error {
    border-color: var(--pulse-rose);
    box-shadow: 0 0 0 4px rgba(239, 68, 68, 0.15);
}
.core.error .core-pulse-ring {
    border-color: var(--pulse-rose);
    animation: none;
    opacity: 0.6;
}

@keyframes breathe {
    0%, 100% { transform: scale(0.95); opacity: 0.15; }
    50% { transform: scale(1.10); opacity: 0.35; }
}

@keyframes listening-pulse {
    0%, 100% { transform: scale(0.92); opacity: 0.25; }
    50% { transform: scale(1.24); opacity: 0.6; }
}

@keyframes thinking-spin {
    from { transform: rotate(0deg) scale(1.05); }
    to { transform: rotate(360deg) scale(1.05); }
}

@keyframes speaking-wave {
    0%, 100% { transform: scale(0.96); opacity: 0.25; }
    35% { transform: scale(1.18); opacity: 0.6; }
    70% { transform: scale(1.04); opacity: 0.4; }
}

/* Form Inputs & Buttons */
input, textarea {
    width: 100%;
    box-sizing: border-box;
    padding: 13px 16px;
    margin-top: 10px;
    margin-bottom: 12px;
    border-radius: 10px;
    border: 1px solid var(--border-strong);
    background: #ffffff;
    color: var(--text-primary);
    font-family: inherit;
    font-size: 15px;
    outline: none;
    transition: border-color 0.15s ease, box-shadow 0.15s ease;
}

input:focus, textarea:focus {
    border-color: var(--google-blue);
    box-shadow: 0 0 0 3px rgba(26, 115, 232, 0.15);
}

textarea {
    resize: vertical;
    min-height: 80px;
}

button {
    width: 100%;
    padding: 13px 18px;
    margin-top: 10px;
    border: 0;
    border-radius: 8px;
    cursor: pointer;
    font-family: inherit;
    font-size: 15px;
    font-weight: 500;
    transition: all 0.15s ease;
    display: inline-flex;
    align-items: center;
    justify-content: center;
    gap: 8px;
}

.primary {
    background: var(--primary-button);
    color: #ffffff;
}
.primary:hover {
    background: var(--primary-button-hover);
}

.voice {
    background: var(--google-blue);
    color: #ffffff;
}
.voice:hover {
    background: #1557b0;
}
.voice.recording {
    background: #ea4335;
    animation: mic-pulse 1s infinite alternate;
}

@keyframes mic-pulse {
    from { opacity: 0.9; }
    to { opacity: 1; transform: scale(1.01); }
}

.secondary {
    background: #ffffff;
    color: var(--text-primary);
    border: 1px solid var(--border-strong);
}
.secondary:hover {
    background: var(--bg-surface);
    border-color: var(--text-primary);
}

.danger {
    background: #fee2e2;
    color: #991b1b;
    border: 1px solid #fecdd3;
}
.danger:hover {
    background: #fecaca;
}

.hidden {
    display: none !important;
}

/* Status & Conversation Bubbles */
#status {
    margin-top: 18px;
    padding: 10px 14px;
    border-radius: 8px;
    background: var(--bg-surface);
    border: 1px solid var(--border-subtle);
    font-size: 14px;
    color: var(--text-secondary);
    font-weight: 500;
    text-align: center;
}

#heard,
#reply {
    margin-top: 16px;
    padding: 16px;
    border-radius: 12px;
    font-size: 15px;
    line-height: 1.55;
    white-space: pre-wrap;
    word-break: break-word;
}

#heard {
    background: #f1f5f9;
    color: var(--text-primary);
    border-left: 3px solid var(--text-light);
}

#reply {
    background: #eff6ff;
    color: #1e3a8a;
    border-left: 3px solid var(--google-blue);
}

#loginStatus {
    margin-top: 12px;
    font-size: 14px;
    color: var(--pulse-rose);
    text-align: center;
}

.reconnect-banner {
    background: #fffbeb;
    border: 1px solid #fcd34d;
    color: #92400e;
    padding: 14px 18px;
    border-radius: 10px;
    margin-bottom: 20px;
    font-size: 14px;
    display: flex;
    align-items: center;
    justify-content: space-between;
    gap: 12px;
}

.reconnect-btn {
    background: #f59e0b;
    color: #ffffff;
    padding: 6px 14px;
    border-radius: 6px;
    font-size: 13px;
    font-weight: 600;
    cursor: pointer;
    border: none;
    white-space: nowrap;
    width: auto;
    margin-top: 0;
}
</style>
</head>

<body>

""" + web.render_header(current_path="/voice") + r"""

<main class="main-content">
<div class="voice-shell">

  <div class="voice-header-center">
    <h1 class="voice-brand-title">HAYDER</h1>
    <div class="voice-subtitle">
      Secure operations assistant &middot; Phase 1
    </div>
  </div>

  <div id="core" class="core idle">
    <div class="core-pulse-ring"></div>
    """ + web.render_logo_svg(36, 36) + r"""
  </div>

  <div id="reconnectBanner" class="reconnect-banner hidden">
    <span>⚠️ Google reconnection required to access Gmail &amp; Calendar.</span>
    <button id="reconnectBannerBtn" class="reconnect-btn">Reconnect Google</button>
  </div>

  <!-- Sign In Card -->
  <div id="loginCard" class="card">
    <h2 style="font-size: 20px; font-weight: 600; color: var(--text-primary); margin-bottom: 6px;">Sign in</h2>
    <p style="font-size: 14px; color: var(--text-secondary); margin-bottom: 12px;">Sign in to your Hayder account to speak or command.</p>

    <input
        id="username"
        type="email"
        autocomplete="username"
        placeholder="Email">

    <input
        id="password"
        type="password"
        autocomplete="current-password"
        placeholder="Password">

    <button
        class="primary"
        id="loginButton">
      Sign in to Hayder
    </button>

    <div id="loginStatus"></div>
  </div>

  <!-- Active Assistant Card -->
  <div id="assistantCard" class="card hidden">

    <div id="sessionStatus" style="font-size: 13px; font-weight: 500; color: var(--text-tertiary); margin-bottom: 12px; display: flex; align-items: center; justify-content: space-between;">
      <span>Signed in</span>
      <span style="display: inline-flex; align-items: center; gap: 6px;">
        <span style="width: 8px; height: 8px; border-radius: 50%; background: #10b981;"></span>
        Operational
      </span>
    </div>

    <textarea
        id="command"
        placeholder="Ask Hayder something... (e.g. 'What needs my attention?', 'What's on my calendar next?')"></textarea>

    <div style="display: flex; gap: 10px; flex-wrap: wrap;">
      <button
          id="micButton"
          class="voice"
          style="flex: 1 1 200px;">
        🎤 Speak to Hayder
      </button>

      <button
          id="sendButton"
          class="primary"
          style="flex: 1 1 140px;">
        Send command
      </button>
    </div>

    <button
        id="googleButton"
        class="secondary">
      🔗 Connect Google: Gmail read/send + Calendar read
    </button>

    <button
        id="logoutButton"
        class="danger">
      Sign out
    </button>

    <div id="status">Ready</div>

    <div id="heard"></div>

    <div id="reply"></div>

  </div>

</div>
</main>

""" + web.render_footer() + r"""

<script>

const loginCard =
    document.getElementById("loginCard");

const assistantCard =
    document.getElementById("assistantCard");

const loginButton =
    document.getElementById("loginButton");

const googleButton =
    document.getElementById("googleButton");

const logoutButton =
    document.getElementById("logoutButton");

const micButton =
    document.getElementById("micButton");

const sendButton =
    document.getElementById("sendButton");

const usernameBox =
    document.getElementById("username");

const passwordBox =
    document.getElementById("password");

const commandBox =
    document.getElementById("command");

const loginStatus =
    document.getElementById("loginStatus");

const statusBox =
    document.getElementById("status");

const heardBox =
    document.getElementById("heard");

const replyBox =
    document.getElementById("reply");

const core =
    document.getElementById("core");

const reconnectBanner =
    document.getElementById("reconnectBanner");

const reconnectBannerBtn =
    document.getElementById("reconnectBannerBtn");


function setVoiceVisualState(state) {
    if (!core) return;
    core.className = "core " + state;

    if (state === "reconnect") {
        if (reconnectBanner) reconnectBanner.classList.remove("hidden");
    } else {
        if (reconnectBanner && state !== "error") {
            // Keep banner visible if reconnect is needed unless explicitly dismissed
        }
    }

    if (micButton) {
        if (state === "listening") {
            micButton.classList.add("recording");
            micButton.textContent = "🛑 Listening... Click to Stop";
        } else {
            micButton.classList.remove("recording");
            micButton.textContent = "🎤 Speak to Hayder";
        }
    }
}


function saveSession(data) {

    sessionStorage.setItem(
        "hayder_id_token",
        data.id_token
    );

    if (data.refresh_token) {

        sessionStorage.setItem(
            "hayder_refresh_token",
            data.refresh_token
        );
    }

    const expiresAt =
        Date.now()
        + (
            (data.expires_in || 3600)
            * 1000
        );

    sessionStorage.setItem(
        "hayder_expires_at",
        String(expiresAt)
    );
}


function clearSession() {

    sessionStorage.removeItem(
        "hayder_id_token"
    );

    sessionStorage.removeItem(
        "hayder_refresh_token"
    );

    sessionStorage.removeItem(
        "hayder_expires_at"
    );
}


function showAssistant() {

    loginCard.classList.add(
        "hidden"
    );

    assistantCard.classList.remove(
        "hidden"
    );

    passwordBox.value = "";

    statusBox.textContent =
        "Ready";

    setVoiceVisualState("idle");
}


function showLogin() {

    assistantCard.classList.add(
        "hidden"
    );

    loginCard.classList.remove(
        "hidden"
    );

    setVoiceVisualState("idle");
}


async function login() {

    const username =
        usernameBox.value.trim();

    const password =
        passwordBox.value;

    if (!username || !password) {

        loginStatus.textContent =
            "Enter your email and password.";

        return;
    }

    loginButton.disabled = true;

    loginStatus.textContent =
        "Signing in...";

    try {

        const response =
            await fetch(
                "/auth/login",
                {
                    method: "POST",
                    headers: {
                        "Content-Type":
                            "application/json"
                    },
                    body: JSON.stringify({
                        username: username,
                        password: password
                    })
                }
            );

        const data =
            await response.json();

        if (!response.ok) {

            loginStatus.textContent =
                data.error
                || "Login failed.";

            return;
        }

        saveSession(data);

        loginStatus.textContent = "";

        showAssistant();

    } catch (error) {

        loginStatus.textContent =
            "Login error: "
            + error.message;

    } finally {

        loginButton.disabled =
            false;
    }
}


async function refreshSession() {

    const refreshToken =
        sessionStorage.getItem(
            "hayder_refresh_token"
        );

    if (!refreshToken) {
        return false;
    }

    try {

        const response =
            await fetch(
                "/auth/refresh",
                {
                    method: "POST",
                    headers: {
                        "Content-Type":
                            "application/json"
                    },
                    body: JSON.stringify({
                        refresh_token:
                            refreshToken
                    })
                }
            );

        const data =
            await response.json();

        if (!response.ok) {

            clearSession();

            showLogin();

            return false;
        }

        saveSession({
            id_token:
                data.id_token,

            refresh_token:
                refreshToken,

            expires_in:
                data.expires_in
        });

        return true;

    } catch (error) {

        return false;
    }
}


async function getValidIdToken() {

    let idToken =
        sessionStorage.getItem(
            "hayder_id_token"
        );

    const expiresAt =
        Number(
            sessionStorage.getItem(
                "hayder_expires_at"
            )
            || 0
        );

    const refreshEarly =
        5 * 60 * 1000;

    if (
        !idToken
        ||
        Date.now()
        >= (
            expiresAt
            - refreshEarly
        )
    ) {

        const refreshed =
            await refreshSession();

        if (!refreshed) {

            throw new Error(
                "Please sign in again."
            );
        }

        idToken =
            sessionStorage.getItem(
                "hayder_id_token"
            );
    }

    return idToken;
}


function getCalmVoice() {
    if (!("speechSynthesis" in window)) return null;
    const voices = window.speechSynthesis.getVoices();
    if (!voices || voices.length === 0) return null;

    // Look for calm, natural UK/English voice
    const preferred = voices.find(v =>
        (v.lang === "en-GB" || v.lang.startsWith("en")) &&
        (v.name.includes("Google") || v.name.includes("Natural") || v.name.includes("Neural") || v.name.includes("Daniel") || v.name.includes("Serena"))
    );
    if (preferred) return preferred;

    const enGb = voices.find(v => v.lang === "en-GB");
    if (enGb) return enGb;

    const anyEn = voices.find(v => v.lang.startsWith("en"));
    return anyEn || voices[0];
}


function speak(text) {

    if (!("speechSynthesis" in window)) {
        return;
    }

    window.speechSynthesis.cancel();

    // Clean text that speech engines sometimes handle badly.
    let cleanText = text
        .replace(/<[^>]*>/g, " ")
        .replace(/\s+/g, " ")
        .trim();

    // Split the reply into short sentences/chunks.
    let sentences = cleanText.match(
        /[^.!?]+[.!?]+|[^.!?]+$/g
    ) || [cleanText];

    let chunks = [];
    let current = "";

    for (const sentence of sentences) {

        if (
            (current + " " + sentence).length
            > 220
        ) {

            if (current.trim()) {
                chunks.push(
                    current.trim()
                );
            }

            current = sentence;

        } else {

            current +=
                " " + sentence;
        }
    }

    if (current.trim()) {
        chunks.push(
            current.trim()
        );
    }

        if (index >= chunks.length) {
            const replyText = (replyBox ? replyBox.textContent : "").toLowerCase();
            if (replyText.includes("reconnect") || replyText.includes("not connected")) {
                setVoiceVisualState("reconnect");
            } else {
                setVoiceVisualState("idle");
            }
            if (statusBox && statusBox.textContent === "Hayder is speaking...") {
                statusBox.textContent = "Ready";
            }
            return;
        }

        const utterance =
            new SpeechSynthesisUtterance(
                chunks[index]
            );

        const calmVoice = getCalmVoice();
        if (calmVoice) {
            utterance.voice = calmVoice;
        }
        utterance.rate = 0.96;
        utterance.pitch = 1.0;

        utterance.onstart =
            function () {
                setVoiceVisualState("speaking");
                if (statusBox) statusBox.textContent = "Hayder is speaking...";
            };

        utterance.onend =
            function () {
                speakChunk(
                    index + 1
                );
            };

        utterance.onerror =
            function () {
                // Continue rather than losing the
                // rest of Hayder's reply.
                speakChunk(
                    index + 1
                );
            };

        window.speechSynthesis.speak(
            utterance
        );
    }

    speakChunk(0);
}


async function sendToHayder(message) {

    core.className =
        "core thinking";

    statusBox.textContent =
        "Hayder is working...";

    try {

        let token =
            await getValidIdToken();

        let response =
            await fetch(
                "/chat",
                {
                    method: "POST",
                    headers: {
                        "Authorization":
                            "Bearer "
                            + token,

                        "Content-Type":
                            "application/json"
                    },

                    body: JSON.stringify({
                        message: message
                    })
                }
            );


        if (response.status === 401) {

            const refreshed =
                await refreshSession();

            if (!refreshed) {

                throw new Error(
                    "Session expired. "
                    + "Please sign in again."
                );
            }

            token =
                await getValidIdToken();

            response =
                await fetch(
                    "/chat",
                    {
                        method: "POST",

                        headers: {
                            "Authorization":
                                "Bearer "
                                + token,

                            "Content-Type":
                                "application/json"
                        },

                        body: JSON.stringify({
                            message: message
                        })
                    }
                );
        }


        const data =
            await response.json();


        if (!response.ok) {

            const hasReply =
                Boolean(
                    data
                    && typeof data.reply === "string"
                    && data.reply.trim()
                );

            if (!hasReply) {

                throw new Error(
                    (data && data.error)
                    || "Hayder request failed."
                );
            }
        }


        const reply =
            data.reply
            || "Hayder completed the request.";


        replyBox.textContent =
            "Hayder:\n"
            + reply;


        statusBox.textContent =
            data.tool
            ? "Tool: " + data.tool
            : "Hayder replied";


        speak(reply);

    } catch (error) {

        statusBox.textContent =
            error.message;

        if (
            error.message.includes(
                "sign in"
            )
        ) {

            clearSession();

            showLogin();
        }

    } finally {

        core.className =
            "core";
    }
}


loginButton.addEventListener(
    "click",
    login
);


passwordBox.addEventListener(
    "keydown",
    function(event) {

        if (
            event.key
            === "Enter"
        ) {

            login();
        }
    }
);


async function triggerGoogleConnect() {
    statusBox.textContent =
        "Preparing Google connection...";

    try {

        const token =
            await getValidIdToken();

        const response =
            await fetch(
                "/oauth/google/connect",
                {
                    method: "GET",
                    headers: {
                        "Authorization":
                            "Bearer " + token
                    }
                }
            );

        const data =
            await response.json();

        if (!response.ok) {
            throw new Error(
                data.error
                || data.message
                || "Google connection failed."
            );
        }

        if (!data.authorization_url) {
            throw new Error(
                "Google authorization URL was not returned."
            );
        }

        window.location.href =
            data.authorization_url;

    } catch (error) {

        statusBox.textContent =
            error.message;

        setVoiceVisualState("error");
    }
}

googleButton.addEventListener(
    "click",
    triggerGoogleConnect
);

if (reconnectBannerBtn) {
    reconnectBannerBtn.addEventListener(
        "click",
        triggerGoogleConnect
    );
}


logoutButton.addEventListener(
    "click",
    function() {

        window.speechSynthesis.cancel();

        clearSession();

        showLogin();
    }
);


function checkAndUpdateVisualState() {
    const replyText = (replyBox ? replyBox.textContent : "").toLowerCase();
    const statusText = (statusBox ? statusBox.textContent : "").toLowerCase();
    if (replyText.includes("reconnect") || replyText.includes("not connected")) {
        setVoiceVisualState("reconnect");
    } else if (statusText.includes("error") || statusText.includes("failed") || statusText.includes("timeout")) {
        setVoiceVisualState("error");
    }
}

sendButton.addEventListener(
    "click",
    async function() {

        const message =
            commandBox.value.trim();

        if (!message) {

            statusBox.textContent =
                "Enter a command first.";

            return;
        }

        heardBox.textContent =
            "You:\n"
            + message;

        await sendToHayder(
            message
        );
        checkAndUpdateVisualState();
    }
);


let activeRecognition = null;

micButton.addEventListener(
    "click",
    function() {

        if (activeRecognition) {
            activeRecognition.stop();
            activeRecognition = null;
            setVoiceVisualState("idle");
            statusBox.textContent = "Ready";
            return;
        }

        const SpeechRecognition =
            window.SpeechRecognition
            ||
            window.webkitSpeechRecognition;


        if (!SpeechRecognition) {

            statusBox.textContent =
                "Voice recognition "
                + "is not supported "
                + "by this browser.";

            return;
        }


        const recognition =
            new SpeechRecognition();

        activeRecognition = recognition;

        recognition.lang =
            "en-GB";

        recognition.interimResults =
            false;

        recognition.maxAlternatives =
            1;


        core.className =
            "core listening";

        setVoiceVisualState("listening");

        statusBox.textContent =
            "Listening...";


        recognition.start();


        recognition.onresult =
            async function(event) {

                const message =
                    event.results[0][0]
                    .transcript;


                commandBox.value =
                    message;


                heardBox.textContent =
                    "You:\n"
                    + message;


                activeRecognition = null;

                await sendToHayder(
                    message
                );
                checkAndUpdateVisualState();
            };


        recognition.onerror =
            function(event) {

                core.className =
                    "core";

                activeRecognition = null;

                setVoiceVisualState("error");

                statusBox.textContent =
                    "Microphone error: "
                    + event.error;
            };


        recognition.onend =
            function() {

                activeRecognition = null;

                if (
                    statusBox.textContent
                    === "Listening..."
                ) {

                    core.className =
                        "core";

                    setVoiceVisualState("idle");

                    statusBox.textContent =
                        "Ready";
                }
            };
    }
);


async function restoreSession() {

    const refreshToken =
        sessionStorage.getItem(
            "hayder_refresh_token"
        );

    if (!refreshToken) {

        showLogin();

        return;
    }

    const ok =
        await refreshSession();

    if (ok) {

        showAssistant();

    } else {

        showLogin();
    }
}


restoreSession();

</script>

</body>
</html>
"""

    return {
        "statusCode": 200,
        "headers": {
            "content-type": "text/html; charset=utf-8",
            "cache-control": "no-store",
        },
        "body": html,
    }


def lambda_handler(event, context):
    """
    Main entrypoint for public web pages and voice assistant.
    Dispatches by rawPath:
      /voice -> render_voice_page()
      /hayder, /hayder/features, /hayder/how-it-works, etc. -> web.render_page()
    """
    path = ""
    if isinstance(event, dict):
        path = (
            event.get("rawPath")
            or (event.get("requestContext") or {}).get("http", {}).get("path")
            or event.get("path")
            or ""
        )

    # Clean query strings if present
    if "?" in path:
        path = path.split("?", 1)[0]

    # If path is specified and not the dedicated voice page, dispatch to web module
    if path and path not in ("/voice", "/voice/"):
        return web.render_page(path)

    # Default (or /voice) returns the dedicated voice assistant page
    return render_voice_page()
