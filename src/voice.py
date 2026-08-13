def lambda_handler(event, context):
    html = r"""<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Hayder Voice</title>

    <style>
        body {
            font-family: Arial, sans-serif;
            max-width: 700px;
            margin: 50px auto;
            padding: 20px;
            background: #111827;
            color: white;
        }

        h1 {
            font-size: 34px;
        }

        .card {
            background: #1f2937;
            padding: 25px;
            border-radius: 16px;
            margin-top: 20px;
        }

        textarea {
            width: 100%;
            min-height: 100px;
            box-sizing: border-box;
            border-radius: 8px;
            padding: 10px;
            margin-bottom: 15px;
        }

        button {
            width: 100%;
            padding: 18px;
            font-size: 20px;
            border: 0;
            border-radius: 10px;
            cursor: pointer;
            margin-top: 10px;
        }

        #micButton {
            background: #2563eb;
            color: white;
        }

        #sendButton {
            background: #059669;
            color: white;
        }

        #status {
            margin-top: 20px;
            font-weight: bold;
        }

        #heard,
        #reply {
            margin-top: 15px;
            padding: 15px;
            background: #374151;
            border-radius: 10px;
            white-space: pre-wrap;
        }
    </style>
</head>

<body>

<h1>🎙️ Hayder Voice</h1>

<p>
Voice → Hayder → AWS read-only → spoken response
</p>

<div class="card">

    <label>
        <strong>Cognito ID Token</strong>
    </label>

    <textarea
        id="token"
        placeholder="Paste your current ID_TOKEN here for this test only">
    </textarea>

    <button id="micButton">
        🎤 Speak to Hayder
    </button>

    <button id="sendButton">
        Send typed command
    </button>

    <textarea
        id="command"
        placeholder="Example: Hayder, check your Lambda.">
    </textarea>

    <div id="status">
        Ready
    </div>

    <div id="heard"></div>

    <div id="reply"></div>

</div>

<script>

const micButton = document.getElementById("micButton");
const sendButton = document.getElementById("sendButton");
const commandBox = document.getElementById("command");
const statusBox = document.getElementById("status");
const heardBox = document.getElementById("heard");
const replyBox = document.getElementById("reply");

async function sendToHayder(message) {

    const token = document.getElementById("token").value.trim();

    if (!token) {
        statusBox.textContent = "Paste your Cognito ID token first.";
        return;
    }

    statusBox.textContent = "Hayder is thinking...";

    try {

        const response = await fetch("/chat", {
            method: "POST",
            headers: {
                "Authorization": "Bearer " + token,
                "Content-Type": "application/json"
            },
            body: JSON.stringify({
                message: message
            })
        });

        const data = await response.json();

        if (!response.ok) {
            statusBox.textContent =
                "Request failed: " +
                JSON.stringify(data);
            return;
        }

        const reply =
            data.reply ||
            "Hayder returned a response.";

        replyBox.textContent =
            "Hayder:\n" + reply;

        statusBox.textContent =
            "Hayder replied.";

        speak(reply);

    } catch (error) {

        statusBox.textContent =
            "Error: " + error.message;
    }
}


function speak(text) {

    if (!("speechSynthesis" in window)) {
        statusBox.textContent =
            "Speech output is not supported by this browser.";
        return;
    }

    window.speechSynthesis.cancel();

    const utterance =
        new SpeechSynthesisUtterance(text);

    utterance.rate = 1;
    utterance.pitch = 1;

    window.speechSynthesis.speak(
        utterance
    );
}


sendButton.addEventListener(
    "click",
    function () {

        const message =
            commandBox.value.trim();

        if (!message) {
            statusBox.textContent =
                "Enter a command first.";
            return;
        }

        heardBox.textContent =
            "You:\n" + message;

        sendToHayder(message);
    }
);


micButton.addEventListener(
    "click",
    function () {

        const SpeechRecognition =
            window.SpeechRecognition ||
            window.webkitSpeechRecognition;

        if (!SpeechRecognition) {

            statusBox.textContent =
                "Voice recognition is not supported by this browser.";

            return;
        }

        const recognition =
            new SpeechRecognition();

        recognition.lang = "en-GB";
        recognition.interimResults = false;
        recognition.maxAlternatives = 1;

        statusBox.textContent =
            "Listening...";

        recognition.start();

        recognition.onresult =
            function (event) {

                const message =
                    event.results[0][0].transcript;

                commandBox.value =
                    message;

                heardBox.textContent =
                    "You:\n" + message;

                statusBox.textContent =
                    "Voice recognised.";

                sendToHayder(message);
            };

        recognition.onerror =
            function (event) {

                statusBox.textContent =
                    "Microphone error: " +
                    event.error;
            };

        recognition.onend =
            function () {

                if (
                    statusBox.textContent ===
                    "Listening..."
                ) {
                    statusBox.textContent =
                        "Stopped listening.";
                }
            };
    }
);

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
