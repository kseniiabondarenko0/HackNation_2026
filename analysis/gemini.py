"""Gemini Developer API, FREE tier only (REST over httpx). No billing, no paid tools."""
from django.conf import settings

from . import llmbase
from .llmbase import LLMError

NAME = "gemini"


def cfg():
    return settings.GEMINI


def configured():
    return bool(cfg()["API_KEY"])


def model():
    return cfg()["MODEL"]


def _parse(response):
    try:
        data = response.json()
        usage = data.get("usageMetadata") or {}
        cand = (data.get("candidates") or [{}])[0]
        text = "".join(p.get("text", "") for p in (cand.get("content") or {}).get("parts", []))
    except (ValueError, AttributeError, TypeError, IndexError):
        raise LLMError("bad_response", "odpowiedź Gemini nie jest poprawnym JSON-em")
    counts = {"in": usage.get("promptTokenCount") or 0,
              "out": (usage.get("candidatesTokenCount") or 0) + (usage.get("thoughtsTokenCount") or 0)}
    finish, problem = cand.get("finishReason"), None
    if finish not in (None, "STOP"):
        problem = LLMError("bad_response" if finish == "MAX_TOKENS" else "blocked", f"finishReason={finish}")
    return text, counts, problem


def generate_json(system, prompt, schema):
    """Returns (dict, {"in", "out"}). Raises LLMError."""
    c = cfg()
    body = {"contents": [{"role": "user", "parts": [{"text": prompt}]}],
            "systemInstruction": {"parts": [{"text": system}]},
            "generationConfig": {"temperature": 0.1, "maxOutputTokens": c["MAX_OUTPUT_TOKENS"],
                                 "responseMimeType": "application/json", "responseSchema": schema}}
    url = f"{c['BASE_URL']}/models/{c['MODEL']}:generateContent"
    text, usage = llmbase.call(NAME, c, url, {"x-goog-api-key": c["API_KEY"]}, body, _parse)
    return llmbase.parse_json(text), usage
