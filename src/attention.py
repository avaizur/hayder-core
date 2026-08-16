import json
import urllib.error
import urllib.request

from intent import (
    get_secret,
    OPENAI_MODEL,
    OPENAI_SECRET_NAME,
)

from attention_memory import apply_preferences


HIGH_SIGNALS = [
    "interview",
    "recruiter",
    "representation",
    "action required",
    "payment failed",
    "security alert",
    "deadline",
    "urgent",
    "offer",
    "assessment",
    "meeting",
    "application update",
]

MEDIUM_SIGNALS = [
    "platform engineer",
    "devops",
    "cloud architect",
    "aws",
    "kubernetes",
    "infrastructure engineer",
    "job opportunity",
]

LOW_SIGNALS = [
    "sale",
    "discount",
    "newsletter",
    "unsubscribe",
    "promotion",
    "promo",
    "pokemon",
    "marketing",
]


def heuristic_score(message):
    text = " ".join(
        [
            message.get("from", ""),
            message.get("subject", ""),
            message.get("snippet", ""),
        ]
    ).lower()

    score = 45
    reasons = []

    for signal in HIGH_SIGNALS:
        if signal in text:
            score += 18
            reasons.append(signal)

    for signal in MEDIUM_SIGNALS:
        if signal in text:
            score += 8
            reasons.append(signal)

    for signal in LOW_SIGNALS:
        if signal in text:
            score -= 18
            reasons.append("low:" + signal)

    if "billing" in text or "payment" in text:
        score += 15
        reasons.append("billing/action")

    if "security" in text:
        score += 20
        reasons.append("security")

    if "linkedin job alerts" in text:
        score += 4
        reasons.append("job alert")

    return max(0, min(100, score)), reasons


def extract_output_text(data):
    if data.get("output_text"):
        return data["output_text"].strip()

    parts = []

    for item in data.get("output", []):
        if item.get("type") != "message":
            continue

        for content in item.get("content", []):
            if content.get("type") == "output_text":
                text = content.get("text")

                if text:
                    parts.append(text)

    return "\n".join(parts).strip()


def ai_rank_candidates(candidates):
    if not candidates:
        return {}

    api_key = get_secret(
        OPENAI_SECRET_NAME
    )

    safe_messages = []

    for candidate in candidates:
        safe_messages.append(
            {
                "index": candidate["index"],
                "from": candidate["message"].get("from", ""),
                "subject": candidate["message"].get("subject", ""),
                "snippet": candidate["message"].get("snippet", "")[:350],
                "initial_score": candidate["score"],
            }
        )

    instructions = """
You are Hayder's Attention Engine.

Re-rank only these shortlisted email candidates.

HIGH:
Likely needs attention/action soon, such as recruiter/interview,
security, payment failure, deadline, direct work message.

MEDIUM:
Useful or relevant but not urgent.

LOW:
Newsletter, promotion, entertainment marketing, generic automated mail.

Return ONLY a valid JSON array:

[
  {
    "index": 2,
    "priority": "HIGH",
    "score": 92,
    "reason": "Interview-related message requiring attention."
  }
]

Do not invent facts.
Use only sender, subject and snippet.
"""

    payload = {
        "model": OPENAI_MODEL,
        "instructions": instructions,
        "input": json.dumps(safe_messages),
        "reasoning": {
            "effort": "low"
        },
    }

    request = urllib.request.Request(
        "https://api.openai.com/v1/responses",
        data=json.dumps(payload).encode("utf-8"),
        headers={
            "Authorization": "Bearer " + api_key,
            "Content-Type": "application/json",
        },
        method="POST",
    )

    try:
        with urllib.request.urlopen(
            request,
            timeout=15,
        ) as api_response:
            raw = api_response.read().decode("utf-8")

    except Exception as exc:
        print(
            "[ATTENTION AI ERROR]",
            str(exc),
        )
        return {}

    try:
        data = json.loads(raw)

        text = extract_output_text(data)

        text = (
            text.replace("```json", "")
            .replace("```", "")
            .strip()
        )

        result = json.loads(text)

        output = {}

        for item in result:
            output[int(item["index"])] = item

        return output

    except Exception as exc:
        print(
            "[ATTENTION PARSE ERROR]",
            str(exc),
        )
        return {}


def rank_messages(messages, user_id=None):
    initial = []

    for index, message in enumerate(messages):
        score, reasons = heuristic_score(
            message
        )

        priority = (
            "HIGH"
            if score >= 75
            else "MEDIUM"
            if score >= 50
            else "LOW"
        )

        reason = (
            ", ".join(reasons)
            if reasons
            else "General inbox message"
        )

        if user_id:
            personalised = apply_preferences(
                user_id,
                message,
                score,
                priority,
                reason,
            )

            score = personalised["score"]
            priority = personalised["priority"]
            reason = personalised["reason"]

        initial.append(
            {
                "index": index,
                "message": message,
                "score": score,
                "priority": priority,
                "reason": reason,
            }
        )

    # Sort first using cheap local logic.
    initial.sort(
        key=lambda x: x["score"],
        reverse=True,
    )

    # Only ask AI to refine the top candidates.
    # This avoids sending the entire inbox to the model.
    candidates = [
        item
        for item in initial[:6]
        if item["score"] >= 40
    ]

    ai_results = ai_rank_candidates(
        candidates
    )

    ranked = []

    for item in initial:
        index = item["index"]
        message = item["message"]

        score = item["score"]
        priority = item["priority"]
        reason = item["reason"]

        ai_item = ai_results.get(index)

        if ai_item:
            score = int(
                ai_item.get(
                    "score",
                    score,
                )
            )

            priority = ai_item.get(
                "priority",
                priority,
            )

            reason = ai_item.get(
                "reason",
                reason,
            )

            # Reapply user's explicit preference
            # so AI cannot override it.
            if user_id:
                personalised = apply_preferences(
                    user_id,
                    message,
                    score,
                    priority,
                    reason,
                )

                score = personalised["score"]
                priority = personalised["priority"]
                reason = personalised["reason"]

        ranked.append(
            {
                **message,
                "priority": priority,
                "importance_score": max(
                    0,
                    min(100, score),
                ),
                "reason": reason,
            }
        )

    ranked.sort(
        key=lambda item:
            item["importance_score"],
        reverse=True,
    )

    return ranked


def important_summary(
    messages,
    limit=5,
    user_id=None,
):
    ranked = rank_messages(
        messages,
        user_id=user_id,
    )

    important = [
        item
        for item in ranked
        if item["priority"] in {
            "HIGH",
            "MEDIUM",
        }
    ][:limit]

    if not important:
        return {
            "messages": [],
            "reply": (
                "I checked your inbox. "
                "Nothing looks important enough "
                "to interrupt you about right now."
            ),
        }

    high_count = len(
        [
            item
            for item in important
            if item["priority"] == "HIGH"
        ]
    )

    parts = [
        (
            "I checked your inbox. "
            f"I found {len(important)} messages "
            "worth your attention. "
            f"{high_count} are high priority."
        )
    ]

    for index, item in enumerate(
        important,
        start=1,
    ):
        parts.append(
            f"{index}. "
            f"{item['priority']} priority. "
            f"From {item.get('from', 'unknown sender')}. "
            f"Subject: {item.get('subject', 'no subject')}. "
            f"Reason: {item.get('reason', '')}."
        )

    return {
        "messages": important,
        "reply": " ".join(parts),
    }
