"""Groq API (OpenAI-compatible), FREE plan only: the fallback when Gemini is paused or out of quota."""
from django.conf import settings

from . import llmbase
from .llmbase import LLMError

NAME = "groq"


def cfg():
    return settings.GROQ


def configured():
    return bool(cfg()["API_KEY"])


def model():
    return cfg()["MODEL"]


def schema_hint(schema):
    """Plain-text description of the JSON schema (JSON mode does not take a schema)."""
    lines = []
    for key, spec in schema["properties"].items():
        kind = spec["type"].lower()
        if kind == "array":
            item = spec["items"]
            kind = "lista " + ("wartości: " + " | ".join(item["enum"]) if "enum" in item else item["type"].lower())
        elif "enum" in spec:
            kind = "jedna z: " + " | ".join(spec["enum"])
        lines.append(f'- "{key}": {kind}{" lub null" if spec.get("nullable") else ""}')
    return "Odpowiedz WYŁĄCZNIE jednym obiektem JSON z polami:\n" + "\n".join(lines)


def _parse(response):
    try:
        data = response.json()
        usage = data.get("usage") or {}
        choice = (data.get("choices") or [{}])[0]
        text = (choice.get("message") or {}).get("content") or ""
    except (ValueError, AttributeError, TypeError, IndexError):
        raise LLMError("bad_response", "odpowiedź Groq nie jest poprawnym JSON-em")
    counts = {"in": usage.get("prompt_tokens") or 0, "out": usage.get("completion_tokens") or 0}
    finish = choice.get("finish_reason")
    problem = LLMError("bad_response", f"finish_reason={finish}") if finish not in (None, "stop") else None
    return text, counts, problem


def generate_json(system, prompt, schema):
    """Returns (dict, {"in", "out"}). Raises LLMError."""
    c = cfg()
    body = {"model": c["MODEL"], "temperature": 0.1, "max_tokens": c["MAX_OUTPUT_TOKENS"],
            "response_format": {"type": "json_object"},
            "messages": [{"role": "system", "content": system + "\n" + schema_hint(schema)},
                         {"role": "user", "content": prompt}]}
    text, usage = llmbase.call(NAME, c, f"{c['BASE_URL']}/chat/completions",
                               {"Authorization": f"Bearer {c['API_KEY']}"}, body, _parse)
    return llmbase.parse_json(text), usage
