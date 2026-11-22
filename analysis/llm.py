"""Provider chain for AI analysis: Gemini (free tier) first, Groq (free plan) as the fallback.

If no provider can answer, the caller gets LLMError (batch kind) and the article stays in the queue.
It is never replaced by a formula."""
from django.conf import settings

from . import gemini, groq, llmbase
from .llmbase import ARTICLE_ERRORS, LLMError

PROVIDERS = {"gemini": gemini, "groq": groq}


def chain():
    """Configured providers in fallback order."""
    return [PROVIDERS[n] for n in settings.LLM["PROVIDERS"] if n in PROVIDERS and PROVIDERS[n].configured()]


def remaining_calls():
    """Calls possible right now across providers that are neither paused nor over their daily limit."""
    return sum(llmbase.remaining_calls(p.NAME, p.cfg()) for p in chain() if llmbase.available(p.NAME))


def complete_json(system, prompt, schema):
    """(dict, {"provider", "model", "in", "out"}). Tries the providers in order; raises LLMError."""
    article_error = batch_error = None
    for provider in chain():
        try:
            raw, usage = provider.generate_json(system, prompt, schema)
            llmbase.validate_json(raw, schema)
        except LLMError as exc:
            if exc.kind in ARTICLE_ERRORS:
                article_error = exc
            else:
                batch_error = batch_error or exc
            continue
        return raw, {"provider": provider.NAME, "model": provider.model(), **usage}
    if article_error:        # somebody answered, but not usably: counts against this article
        raise article_error
    raise batch_error or LLMError("no_key", "brak skonfigurowanych kluczy AI (GEMINI_API_KEY / GROQ_API_KEY)")
