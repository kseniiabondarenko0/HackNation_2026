from django.contrib import messages
from django.contrib.admin.views.decorators import staff_member_required
from django.core.paginator import Paginator
from django.db.models import Count, Q, Max
from django.http import JsonResponse
from django.shortcuts import render, get_object_or_404, redirect
from django.utils import timezone
from django.views.decorators.http import require_POST
from collection.models import Article, Source, CollectionRun


def radar(request):
    qs = Article.objects.select_related("source").filter(status="fetched", duplicate_of__isnull=True)
    selected = request.GET.get("source", "")
    if selected.isdecimal():
        qs = qs.filter(source_id=selected)
    query = request.GET.get("q", "")[:200].strip()
    if query:
        qs = qs.filter(Q(text__icontains=query) | Q(title__icontains=query))
    page = Paginator(qs, 25).get_page(request.GET.get("page"))
    return render(request, "web/radar.html", {
        "articles": page, "sources": Source.objects.all(), "q": query,
        "selected_source": selected, "total": page.paginator.count,
        "source_count": Source.objects.filter(enabled=True).count(),
        "last_checked": Source.objects.aggregate(value=Max("last_checked"))["value"],
    })


def detail(request, pk):
    article = get_object_or_404(Article.objects.select_related("source"), pk=pk)
    return render(request, "web/detail.html", {"a": article})


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
