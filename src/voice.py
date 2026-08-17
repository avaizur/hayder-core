def lambda_handler(event, context):
    html = r"""<!DOCTYPE html>
<html lang="en">

<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">

<title>Hayder</title>

<style>

body {
    margin: 0;
    font-family: Arial, sans-serif;
    background: #080b12;
    color: white;
    min-height: 100vh;
}

.wrap {
    max-width: 760px;
    margin: auto;
    padding: 40px 20px;
}

h1 {
    font-size: 38px;
    margin-bottom: 5px;
}

.subtitle {
    color: #9ca3af;
    margin-bottom: 30px;
}

.card {
    background: #141923;
    border: 1px solid #252c39;
    padding: 24px;
    border-radius: 18px;
    margin-bottom: 20px;
}

input,
textarea {
    width: 100%;
    box-sizing: border-box;
    padding: 14px;
    margin-top: 10px;
    margin-bottom: 10px;
    border-radius: 10px;
    border: 1px solid #374151;
    background: #0d1119;
    color: white;
    font-size: 16px;
}

button {
    width: 100%;
    padding: 16px;
    margin-top: 10px;
    border: 0;
    border-radius: 10px;
    cursor: pointer;
    font-size: 17px;
}

.primary {
    background: #2563eb;
    color: white;
}

.voice {
    background: #7c3aed;
    color: white;
}

.secondary {
    background: #263244;
    color: white;
}

.danger {
    background: #3f1d25;
    color: white;
}

.hidden {
    display: none;
}

#status {
    margin-top: 15px;
    color: #93c5fd;
}

#heard,
#reply {
    margin-top: 15px;
    padding: 15px;
    border-radius: 10px;
    background: #1e2532;
    white-space: pre-wrap;
}

.core {
    width: 110px;
    height: 110px;
    margin: 20px auto 30px;
    border-radius: 50%;
    border: 2px solid #6b7280;
    display: flex;
    align-items: center;
    justify-content: center;
    font-size: 38px;
    animation: breathe 3s ease-in-out infinite;
}

.core.listening {
    animation: listening 0.9s ease-in-out infinite;
}

.core.thinking {
    animation: thinking 0.7s linear infinite;
}

@keyframes breathe {
    0%,100% { transform: scale(0.95); opacity: .65; }
    50% { transform: scale(1.05); opacity: 1; }
}

@keyframes listening {
    0%,100% { transform: scale(0.9); }
    50% { transform: scale(1.15); }
}

@keyframes thinking {
    from { transform: rotate(0deg); }
    to { transform: rotate(360deg); }
}

</style>
</head>

<body>

<div class="wrap">

<h1>HAYDER</h1>

<div class="subtitle">
Secure personal operations assistant
</div>

<div id="core" class="core">
●
</div>


<div id="loginCard" class="card">

<h2>Sign in</h2>

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


<div id="assistantCard" class="card hidden">

<div id="sessionStatus">
Signed in
</div>

<textarea
    id="command"
    placeholder="Ask Hayder something..."></textarea>

<button
    id="micButton"
    class="voice">
🎤 Speak to Hayder
</button>

<button
    id="sendButton"
    class="primary">
Send command
</button>

<button
    id="googleButton"
    class="secondary">
🔗 Connect Google Gmail + Calendar
</button>

<button
    id="logoutButton"
    class="danger">
Sign out
</button>

<div id="status">
Ready
</div>

<div id="heard"></div>

<div id="reply"></div>

</div>

</div>


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
}


function showLogin() {

    assistantCard.classList.add(
        "hidden"
    );

    loginCard.classList.remove(
        "hidden"
    );
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

    function speakChunk(index) {

        if (index >= chunks.length) {
            return;
        }

        const utterance =
            new SpeechSynthesisUtterance(
                chunks[index]
            );

        utterance.rate = 0.96;
        utterance.pitch = 1;

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

            throw new Error(
                data.reply
                || data.error
                || "Hayder request failed."
            );
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


googleButton.addEventListener(
    "click",
    async function() {

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
        }
    }
);


logoutButton.addEventListener(
    "click",
    function() {

        window.speechSynthesis.cancel();

        clearSession();

        showLogin();
    }
);


sendButton.addEventListener(
    "click",
    function() {

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

        sendToHayder(
            message
        );
    }
);


micButton.addEventListener(
    "click",
    function() {

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


        recognition.lang =
            "en-GB";

        recognition.interimResults =
            false;

        recognition.maxAlternatives =
            1;


        core.className =
            "core listening";

        statusBox.textContent =
            "Listening...";


        recognition.start();


        recognition.onresult =
            function(event) {

                const message =
                    event.results[0][0]
                    .transcript;


                commandBox.value =
                    message;


                heardBox.textContent =
                    "You:\n"
                    + message;


                sendToHayder(
                    message
                );
            };


        recognition.onerror =
            function(event) {

                core.className =
                    "core";

                statusBox.textContent =
                    "Microphone error: "
                    + event.error;
            };


        recognition.onend =
            function() {

                if (
                    statusBox.textContent
                    === "Listening..."
                ) {

                    core.className =
                        "core";

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
            "content-type":
                "text/html; charset=utf-8",
            "cache-control":
                "no-store",
        },
        "body": html,
    }
