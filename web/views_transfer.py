"""Anonymous-session scenario reports. The URL alone never grants access to someone else's inputs."""
import uuid
from datetime import timedelta

from django.http import Http404
from django.shortcuts import get_object_or_404, redirect, render
from django.utils.crypto import salted_hmac
from django.utils import timezone
from django.views.decorators.cache import never_cache
from django.views.decorators.http import require_http_methods

from analysis import transfer
from analysis.llmbase import LLMError
from analysis.models import TransferScenario
from collection.models import Article
from .forms import TransferForm

ERRORS = {
    "budget": "Wyczerpano dzienny limit AI lub limit 8 scenariuszy na godzinę w tej przeglądarce. Zachowaliśmy formularz. Spróbuj później.",
    "quota": "Dostawca wstrzymał zapytania w darmowym limicie. Zachowaliśmy formularz; spróbuj po odnowieniu limitu.",
    "no_key": "Analiza wymaga skonfigurowanego klucza Gemini lub Groq w darmowym planie. Formularz pozostaje wypełniony.",
    "bad_response": "Nie udało się potwierdzić poprawności odpowiedzi i cytatów. Nie zapisaliśmy jej jako wyniku. Spróbuj ponownie za chwilę.",
    "unavailable": "Scenariusz jest przetwarzany, czeka na ponowną próbę lub źródło właśnie się zmieniło. Spróbuj ponownie za kilka minut.",
    "bad_request": "Ta publikacja nie ma jeszcze pełnego, samodzielnego tekstu do analizy.",
}


def _owner(request, create=False):
    if not request.session.session_key:
        if not create:
            return ""
        request.session.create()
    return salted_hmac("transfer-owner", request.session.session_key).hexdigest()


@never_cache
@require_http_methods(["GET", "POST"])
def scenario(request, pk):
    article = get_object_or_404(Article.objects.select_related("source"), pk=pk, status="fetched", duplicate_of__isnull=True)
    owner = _owner(request, create=True)
    # Previous inputs stay in this session only; no public list, API export or URL parameters with their text.
    saved = TransferScenario.objects.filter(article=article, owner=owner,
                                           created_at__gte=timezone.now() - timedelta(days=7))
    previous = saved.order_by("-created_at").first()
    if request.GET.get("from"):
        try:
            previous_id = uuid.UUID(request.GET["from"])
        except ValueError:
            raise Http404 from None
        previous = get_object_or_404(saved, pk=previous_id)
    form = TransferForm(request.POST if request.method == "POST" else None,
                        initial=previous.profile if previous else None)
    if request.method == "POST" and form.is_valid():
        try:
            report, _ = transfer.generate(article, form.cleaned_data, owner)
        except LLMError as exc:
            form.add_error(None, ERRORS.get(exc.kind, "AI jest chwilowo niedostępne. Formularz pozostaje wypełniony; spróbuj później."))
        else:
            return redirect("transfer_result", pk=report.pk)
    reports = saved.filter(status="ready").order_by("-created_at")[:8]
    return render(request, "web/transfer_form.html", {"a": article, "form": form, "reports": reports})


@never_cache
@require_http_methods(["GET"])
def result(request, pk):
    report = get_object_or_404(TransferScenario.objects.select_related("article__source"),
                               pk=pk, owner=_owner(request), status="ready",
                               created_at__gte=timezone.now() - timedelta(days=7))
    current = transfer.is_current(report, report.article)
    # Withdraw obsolete quotations and recommendations instead of showing them beside a changed source.
    data = report.data if current else {}
    return render(request, "web/transfer_result.html", {
        "report": report, "a": report.article, "current": current,
        "profile": report.profile, "organization": dict(TransferForm.base_fields["organization_type"].choices).get(
            report.profile.get("organization_type"), "Organizacja"),
        "verdict": transfer.VERDICTS.get(data.get("ai", {}).get("verdict"), ""),
        "ai": data.get("ai", {}), "quotes": data.get("verified", {}).get("quotes", []),
    })
