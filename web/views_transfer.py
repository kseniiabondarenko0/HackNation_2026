"""Anonymous-session scenario reports. The URL alone never grants access to someone else's inputs."""
import uuid
from datetime import timedelta

from django.http import Http404
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
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
    "network": "Nie udało się połączyć z dostawcą AI (sieć lub usługa chwilowo niedostępna). Zachowaliśmy formularz i zapisane scenariusze. Spróbuj za kilka minut.",
    "auth": "Dostawca AI odrzucił klucz API lub model jest wyłączony. Zachowaliśmy formularz. Wymagana jest poprawka konfiguracji na serwerze.",
    "config": "Dostawca AI odrzucił klucz API lub model jest wyłączony. Zachowaliśmy formularz. Wymagana jest poprawka konfiguracji na serwerze.",
    "blocked": "Dostawca AI odmówił odpowiedzi dla tego tekstu. Zachowaliśmy formularz; spróbuj zmienić opis warunków.",
    "budget": "Wyczerpano dzienny limit AI lub limit 8 scenariuszy na godzinę w tej przeglądarce. Zachowaliśmy formularz. Spróbuj później.",
    "quota": "Dostawca wstrzymał zapytania w darmowym limicie. Zachowaliśmy formularz; spróbuj po odnowieniu limitu.",
    "no_key": "Analiza wymaga skonfigurowanego klucza Gemini lub Groq w darmowym planie. Formularz pozostaje wypełniony.",
    "bad_response": "Nie udało się potwierdzić poprawności odpowiedzi i cytatów. Nie zapisaliśmy jej jako wyniku. Spróbuj ponownie za chwilę.",
    "unavailable": "Analiza jest chwilowo wstrzymana: dostawca AI zgłosił wcześniej błąd lub limit, ten scenariusz właśnie się liczy albo źródło się zmieniło. Zachowaliśmy formularz. Spróbuj ponownie za kilka minut, a przy wyczerpanym limicie darmowego planu po jego odnowieniu.",
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
        # The result page compares the new answer with the scenario the person edited (or, failing that, the latest ready one).
        basis = previous if previous and previous.status == "ready" else saved.filter(status="ready").order_by("-created_at").first()
        try:
            report, _ = transfer.generate(article, form.cleaned_data, owner)
        except LLMError as exc:
            form.add_error(None, ERRORS.get(exc.kind, "AI jest chwilowo niedostępne. Formularz pozostaje wypełniony; spróbuj później."))
        else:
            target = reverse("transfer_result", args=[report.pk])
            return redirect(f"{target}?vs={basis.pk}" if basis and basis.pk != report.pk else target)
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
    org_labels = dict(TransferForm.base_fields["organization_type"].choices)
    saved = TransferScenario.objects.filter(article=report.article, owner=report.owner, status="ready",
                                            created_at__gte=timezone.now() - timedelta(days=7)).exclude(pk=report.pk)
    earlier = saved.filter(created_at__lt=report.created_at).order_by("-created_at").first()
    other, comparison = None, None
    try:   # ?vs=<scenario> comes from the "change conditions" flow; anything unusable is simply ignored
        other = saved.filter(pk=uuid.UUID(request.GET.get("vs", ""))).first()
    except ValueError:
        pass
    if current and other and transfer.is_current(other, report.article):
        comparison = transfer.compare(other, report, org_labels)
    return render(request, "web/transfer_result.html", {
        "report": report, "a": report.article, "current": current, "comparison": comparison, "other": other,
        "earlier": earlier if current and not comparison else None,
        "profile": report.profile, "organization": org_labels.get(report.profile.get("organization_type"), "Organizacja"),
        "verdict": transfer.VERDICTS.get(data.get("ai", {}).get("verdict"), ""),
        "ai": data.get("ai", {}), "quotes": data.get("verified", {}).get("quotes", []),
    })
