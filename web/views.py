from django.contrib import messages
from django.contrib.admin.views.decorators import staff_member_required
from django.core.paginator import Paginator
from django.db.models import Count, F, Q, Max
from django.http import JsonResponse
from django.shortcuts import render, get_object_or_404, redirect
from django.utils import timezone
from django.views.decorators.http import require_POST
from analysis.core import PATHS, SIGNALS
from analysis.search import search
from analysis.service import analyze_article
from collection.extract import content_hash, extract_article
from collection.models import Article, Source, CollectionRun
from collection.netsafe import safe_get
from .forms import SubmitForm


def radar(request):
    qs = Article.objects.select_related("source", "analysis").filter(status="fetched", duplicate_of__isnull=True)
    selected = request.GET.get("source", "")
    if selected.isdecimal():
        qs = qs.filter(source_id=selected)
    query = request.GET.get("q", "")[:200].strip()
    if query:
        qs = qs.filter(Q(text__icontains=query) | Q(title__icontains=query))
    path, signal, sort = request.GET.get("sciezka", ""), request.GET.get("sygnal", ""), request.GET.get("sort", "")
    if path in PATHS:
        qs = qs.filter(analysis__path=path)
    if signal in SIGNALS:
        qs = qs.filter(analysis__signal=signal)
    if sort == "potencjal":
        qs = qs.order_by(F("analysis__potential").desc(nulls_last=True), "-first_seen_at")
    page = Paginator(qs, 25).get_page(request.GET.get("page"))
    params = request.GET.copy()
    params.pop("page", None)
    return render(request, "web/radar.html", {
        "articles": page, "sources": Source.objects.all(), "q": query,
        "selected_source": selected, "total": page.paginator.count,
        "paths": PATHS.items(), "signals": SIGNALS.items(), "path": path, "signal": signal, "sort": sort,
        "extra": params.urlencode(),
        "source_count": Source.objects.filter(enabled=True).count(),
        "last_checked": Source.objects.aggregate(value=Max("last_checked"))["value"],
    })


def detail(request, pk):
    article = get_object_or_404(Article.objects.select_related("source", "analysis"), pk=pk)
    analysis = getattr(article, "analysis", None)
    return render(request, "web/detail.html", {"a": article, "an": analysis, "d": analysis.data if analysis else None})


def sources(request):
    now = timezone.now()
    entries = Source.objects.annotate(
        article_count=Count("articles"),
        fetched_count=Count("articles", filter=Q(articles__status="fetched", articles__duplicate_of__isnull=True)),
        error_count=Count("articles", filter=Q(articles__status="error")))
    rows = [{"s": s, "running": bool(s.locked_until and s.locked_until > now),
             "overdue": bool(s.enabled and (not s.next_run_at or s.next_run_at < now))} for s in entries]
    return render(request, "web/sources.html", {"rows": rows})


def runs(request):
    entries = CollectionRun.objects.select_related("source")
    return render(request, "web/runs.html", {"runs": Paginator(entries, 30).get_page(request.GET.get("page"))})


@require_POST
@staff_member_required
def request_scan(request, pk):
    source = get_object_or_404(Source, pk=pk)
    if not source.enabled:
        messages.warning(request, "Źródło jest wyłączone. Włącz je w panelu zarządzania.")
    elif source.locked_until and source.locked_until > timezone.now():
        messages.info(request, "Trwa już sprawdzanie tego źródła.")
    else:
        Source.objects.filter(pk=pk).update(next_run_at=timezone.now())
        messages.success(request, "Zlecono sprawdzenie w kolejnym cyklu kolektora.")
    return redirect("sources")


def health(request):
    Source.objects.exists()
    return JsonResponse({"status": "ok", "version": "0.1"})


def status(request):
    return JsonResponse({
        "version": "0.1", "sources": Source.objects.filter(enabled=True).count(),
        "articles": Article.objects.filter(status="fetched", duplicate_of__isnull=True).count(),
        "pending": Article.objects.filter(status="found").count(),
        "errors": Article.objects.filter(status="error").count(),
        "runs": CollectionRun.objects.count(),
        "last_checked": Source.objects.aggregate(value=Max("last_checked"))["value"],
    })


def api_search(request):
    """JSON: top articles for a free-text query, with their analysis summary."""
    query = request.GET.get("q", "").strip()[:200]
    if not query:
        return JsonResponse({"error": "Podaj parametr q."}, status=400)
    n = request.GET.get("n", "5")
    limit = min(20, max(1, int(n))) if n.isdecimal() else 5
    results = []
    for score, a in search(query, limit):
        an = getattr(a, "analysis", None)
        results.append({
            "id": a.pk, "title": a.title, "source": a.source.name, "url": a.final_url or a.original_url,
            "detail_url": request.build_absolute_uri(f"/a/{a.pk}/"), "score": round(score, 4),
            "published_at": a.published_at, "snippet": a.text[:300],
            "analysis": {"potential": an.potential, "signal": an.signal, "path": an.path,
                         "sector": an.sector, "stage": an.stage, "completeness": an.completeness} if an else None})
    return JsonResponse({"query": query, "count": len(results), "results": results},
                        json_dumps_params={"ensure_ascii": False})


SUBMIT_SOURCE = {"entry_url": "https://radar.local/zgloszenia/",
                 "defaults": {"name": "Zgłoszenia ręczne", "enabled": False, "organization_type": "other"}}


def submit(request):
    """Manual submission: pasted text or a URL; goes through the same analysis as collected articles."""
    form = SubmitForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        title, text, url = form.cleaned_data["title"].strip(), form.cleaned_data["text"], form.cleaned_data["url"]
        final_url = ""
        if not text:
            try:
                final_url, html = safe_get(url)
                data = extract_article(html, final_url)
            except Exception as exc:
                data = None
                form.add_error("url", f"Nie udało się pobrać strony ({type(exc).__name__}). Wklej opis ręcznie.")
            if data and len(data["text"]) >= 150:
                text, title = data["text"], title or data["title"]
            elif data is not None:
                form.add_error("url", "Na stronie nie znaleziono wystarczająco dużo tekstu. Wklej opis ręcznie.")
        if text and not form.errors:
            digest = content_hash(text)
            existing = Article.objects.filter(Q(content_hash=digest) | Q(original_url=url or "-")).first()
            if existing:
                messages.info(request, "Taki materiał już jest w bazie.")
                return redirect("detail", pk=existing.pk)
            source, _ = Source.objects.get_or_create(**SUBMIT_SOURCE)
            article = Article.objects.create(
                source=source, original_url=url or f"https://radar.local/zgloszenie/{digest[:24]}",
                final_url=final_url, title=title[:500] or "Zgłoszenie bez tytułu", text=text, content_hash=digest,
                status="fetched", fetched_at=timezone.now(), published_at=None)
            analyze_article(article)
            messages.success(request, "Zgłoszenie zapisane i przeanalizowane.")
            return redirect("detail", pk=article.pk)
    return render(request, "web/submit.html", {"form": form})
