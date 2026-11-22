from django.conf import settings
from django.contrib import messages
from django.contrib.admin.views.decorators import staff_member_required
from django.core.paginator import Paginator
from django.db.models import Count, F, Q, Max
from django.http import Http404, HttpResponse, JsonResponse
from django.shortcuts import render, get_object_or_404, redirect
from django.utils import timezone
from django.views.decorators.http import require_POST
from analysis.core import AREAS, LABELS, PATHS, SIGNALS, STAGES, area_of, area_sectors, thresholds
from analysis.tabs import CHECKED, TABS, WAITING, tab_q
from analysis import demo
from analysis.external import external_search
from analysis.regions import CODES as REGIONS, NATIONAL
from analysis.models import Analysis
from analysis.search import matching_pks, search
from analysis.llmbase import LLMError
from analysis.service import analyze_article
from collection.extract import content_hash, extract_article
from collection import sourcefinder
from collection.models import Article, Source, CollectionRun, Submission, DiscoveryRun
from collection.netsafe import safe_get
from matching.recipients import match_recipients
from matching.models import Recipient
from matching.similar import similar
from .forms import SubmitForm

CATALOG_PAGE = 24
# the 'Do weryfikacji' condition as seen from Source (articles__...): used by the per-source quality table
WAITING_ARTICLES = Q(articles__status="fetched", articles__duplicate_of__isnull=True) & (
    Q(articles__analysis__isnull=True) | Q(articles__analysis__verdict__in=("weryfikacja", "")))


def _region_filter(qs, region):
    """?woj=<voivodeship> or ?woj=ogólnopolskie (no voivodeship)."""
    if region in REGIONS:
        return qs.filter(analysis__region=region)
    if region == NATIONAL:
        return qs.filter(analysis__region="")
    return qs


ACTORS = dict(Source.ORG)


def _actor_filter(qs, actor):
    """Who the innovation comes from: the submitter's type for a submission, else the source institution's type."""
    if actor in ACTORS:
        return qs.filter(Q(submission__submitter_type=actor) | Q(submission__isnull=True, source__organization_type=actor))
    return qs


def _qs_url(params, **changes):
    """Current query string with some keys replaced/removed (and paging reset)."""
    p = params.copy()
    p.pop("page", None)
    for key, value in changes.items():
        if value:
            p[key] = value
        else:
            p.pop(key, None)
    encoded = p.urlencode()
    return "?" + encoded if encoded else "?"


def overview(request):
    """'Przegląd': headline numbers and the newest cards of the main list."""
    main = Article.objects.select_related("source", "analysis", "submission").filter(
        status="fetched", duplicate_of__isnull=True).filter(tab_q("glowna"))
    total = main.count()
    scored = main.filter(analysis__potential__isnull=False).count()
    high = main.filter(analysis__potential__gte=70).count()
    rows = [r for r in main.filter(analysis__isnull=False).order_by().values("analysis__sector")
            .annotate(n=Count("pk")).order_by("-n") if r["analysis__sector"]][:6]
    top = rows[0]["n"] if rows else 1
    return render(request, "web/overview.html", {
        "latest": list(main.order_by(F("published_at").desc(nulls_last=True), "-first_seen_at", "-pk")[:3]), "total": total, "scored": scored,
        "high": high, "mid_low": scored - high, "unscored": total - scored,
        "queue": Article.objects.filter(status="fetched", duplicate_of__isnull=True).filter(WAITING).count(),
        "demo_count": demo.loaded_count(),
        "sectors": [{"label": r["analysis__sector"], "n": r["n"], "pct": round(100 * r["n"] / top)} for r in rows]})


def radar(request):
    qs = Article.objects.select_related("source", "analysis", "submission").filter(status="fetched", duplicate_of__isnull=True)
    selected = request.GET.get("source", "")
    if selected.isdecimal():
        qs = qs.filter(source_id=selected)
    query = request.GET.get("q", "")[:200].strip()
    if query:
        qs = qs.filter(pk__in=matching_pks(qs, query))
    # Three lists (analysis.tabs): Interesujące (AI-confirmed), Do weryfikacji (temporary queue), Wszystkie (checked).
    # Every filter is applied BEFORE the counters, so a counter always equals what its tab would list.
    view = request.GET.get("widok", "glowna")
    if view not in TABS:      # e.g. a bookmarked ?widok=odrzucone: fall back to the main list and do not echo the value
        request.GET = request.GET.copy()
        request.GET.pop("widok", None)
        view = "glowna"
    region = request.GET.get("woj", "")
    qs = _region_filter(qs, region)
    actor = request.GET.get("kto", "")
    qs = _actor_filter(qs, actor)
    path, signal, sort = request.GET.get("sciezka", ""), request.GET.get("sygnal", ""), request.GET.get("sort", "")
    if path in PATHS:
        qs = qs.filter(analysis__path=path)
    if signal in SIGNALS:
        qs = qs.filter(analysis__signal=signal)
    area, maturity = request.GET.get("obszar", ""), request.GET.get("dojrzalosc", "")
    if area in AREAS:
        qs = qs.filter(analysis__sector__in=area_sectors(area))
    if maturity in STAGES:
        qs = qs.filter(analysis__stage=maturity)
    sector = request.GET.get("sektor", "")[:80]
    sector_rows = [r for r in qs.filter(tab_q(view), analysis__isnull=False).order_by().values("analysis__sector")
                   .annotate(n=Count("pk")).order_by("-n", "analysis__sector") if r["analysis__sector"]]
    if sector:
        qs = qs.filter(analysis__sector=sector)
    tabs = [(k, label, qs.filter(tab_q(k)).count()) for k, label in TABS.items()]
    qs = qs.filter(tab_q(view))
    if sort == "potencjal":
        qs = qs.order_by(F("analysis__potential").desc(nulls_last=True), "-first_seen_at", "-pk")
    elif sort == "najnowsze":
        qs = qs.order_by(F("published_at").desc(nulls_last=True), "-first_seen_at", "-pk")
    else:    # default: PCI priority first, then the AI score (the best items open the list), then the newest
        qs = qs.order_by(F("analysis__priority").desc(nulls_last=True), F("analysis__potential").desc(nulls_last=True),
                         F("published_at").desc(nulls_last=True), "-pk")
    page = Paginator(qs, CATALOG_PAGE).get_page(request.GET.get("page"))
    has_demo = any(((getattr(a, "analysis", None) and a.analysis.data) or {}).get("demo") for a in page)
    params = request.GET.copy()
    params.pop("page", None)
    tab_params = params.copy()
    tab_params.pop("widok", None)
    layout = "tabela" if request.GET.get("uklad") == "tabela" else "karty"
    return render(request, "web/radar.html", {
        "layout": layout, "sector": sector, "sector_all_url": _qs_url(request.GET, sektor=""),
        "sector_chips": [{"label": r["analysis__sector"], "n": r["n"], "active": r["analysis__sector"] == sector,
                          "url": _qs_url(request.GET, sektor=r["analysis__sector"])} for r in sector_rows],
        "layout_cards_url": _qs_url(request.GET, uklad=""), "layout_table_url": _qs_url(request.GET, uklad="tabela"),
        "articles": page, "sources": Source.objects.all(), "q": query,
        "selected_source": selected, "total": page.paginator.count,
        "paths": PATHS.items(), "signals": SIGNALS.items(), "path": path, "signal": signal, "sort": sort,
        "extra": params.urlencode(), "view": view, "tabs": tabs, "tab_extra": tab_params.urlencode(),
        "regions": REGIONS, "region": region, "national": NATIONAL, "ttl": settings.RETENTION["QUEUE_TTL_HOURS"],
        "has_demo": has_demo, "areas": AREAS.items(), "area": area, "stages": STAGES.items(), "maturity": maturity,
        "compare": True,
        "actors": [(k, v) for k, v in Source.ORG if k != "other"], "actor": actor,
        "source_count": Source.objects.filter(enabled=True).count(),
        "last_checked": Source.objects.aggregate(value=Max("last_checked"))["value"],
    })


def compare(request):
    """Side-by-side comparison of 2-4 selected innovations: verified facts apart from AI estimates."""
    ids = []
    for raw in request.GET.getlist("id"):
        if raw.isdecimal() and int(raw) not in ids:
            ids.append(int(raw))
    ids = ids[:4]
    found = {a.pk: a for a in Article.objects.select_related("source", "analysis")
             .filter(pk__in=ids, status="fetched", analysis__isnull=False)}
    cols = []
    for pk in ids:
        a = found.get(pk)
        if not a:
            continue
        d, ai = a.analysis.data or {}, (a.analysis.data or {}).get("ai") or {}
        cols.append({"a": a, "an": a.analysis, "d": d, "ai": ai, "area": AREAS.get(area_of(a.analysis.sector), "—"),
                     "quotes": (d.get("verified") or {}).get("quotes") or [], "demo": bool(d.get("demo"))})
    return render(request, "web/compare.html", {"cols": cols, "few": len(cols) < 2})


def detail(request, pk):
    article = get_object_or_404(Article.objects.select_related("source", "analysis", "submission"), pk=pk)
    analysis = getattr(article, "analysis", None)
    data = analysis.data if analysis else None
    return render(request, "web/detail.html", {
        "area": AREAS.get(area_of(analysis.sector), "") if analysis else "",
        "a": article, "an": analysis, "d": data, "handling_choices": Analysis.HANDLING,
        "sub": getattr(article, "submission", None),
        "external": external_search(article.title, (data or {}).get("sector", "")),
        "similar": similar(article), "recipients": match_recipients(article, data)})


@require_POST
@staff_member_required
def handling(request, pk):
    """Record the next step for an identified innovation (contact, handover to a partner, pilot, deployment)."""
    from matching.models import Recipient
    analysis = get_object_or_404(Analysis, article_id=pk)
    status = request.POST.get("etap", "")
    if status not in dict(Analysis.HANDLING):
        messages.warning(request, "Nieznany etap.")
        return redirect("detail", pk=pk)
    partner_id = request.POST.get("partner", "")
    partner = Recipient.objects.filter(pk=partner_id).first() if partner_id.isdecimal() else None
    if status in ("przekazano", "pilotaz") and not (partner or analysis.handling_partner):
        messages.warning(request, "Wskaż partnera, któremu przekazano innowację.")
        return redirect("detail", pk=pk)
    partner = partner or analysis.handling_partner
    note = request.POST.get("uwaga", "").strip()[:1000]
    analysis.handling, analysis.handling_partner = status, partner
    analysis.handling_log = (analysis.handling_log or []) + [{
        "status": status, "label": dict(Analysis.HANDLING)[status], "partner": partner.name if partner else "",
        "note": note, "by": request.user.get_username(), "at": timezone.now().strftime("%Y-%m-%d %H:%M")}]
    analysis.save(update_fields=["handling", "handling_partner", "handling_log"])
    messages.success(request, f"Zapisano etap: {dict(Analysis.HANDLING)[status]}.")
    return redirect("detail", pk=pk)


def effectiveness(request):
    """'Skuteczność': live state of the base (what is kept, what waits, what was removed) + the filter on labelled examples."""
    from analysis.evaluation import evaluate
    from collection.models import Rejected
    base = Article.objects.filter(status="fetched", duplicate_of__isnull=True)
    stored = base.count()
    checked = base.filter(CHECKED).count()
    interesting = base.filter(tab_q("glowna")).count()
    analysed = Analysis.objects.filter(article__in=base)
    funnel = [("Aktualne materiały w bazie (bez duplikatów)", stored),
              ("Po analizie AI", checked),
              ("Interesujące (lista główna)", interesting),
              ("Przekazane partnerowi (lub dalej)", analysed.filter(handling__in=("przekazano", "pilotaz", "wdrozono")).count()),
              ("Wdrożone / skomercjalizowane", analysed.filter(handling="wdrozono").count())]
    top = max([n for _, n in funnel] + [1])
    by_source = (Source.objects.annotate(
        collected=Count("articles", filter=Q(articles__status="fetched", articles__duplicate_of__isnull=True)),
        interesting=Count("articles", filter=Q(articles__analysis__verdict="glowna")),
        review=Count("articles", filter=WAITING_ARTICLES))
        .filter(collected__gt=0).order_by("-interesting", "name"))
    return render(request, "web/effectiveness.html", {
        "funnel": [(label, n, round(100 * n / top)) for label, n in funnel], "by_source": by_source,
        "stored": stored, "waiting": stored - checked, "removed": Rejected.objects.count(),
        "ttl": settings.RETENTION["QUEUE_TTL_HOURS"], "window": settings.ANALYSIS["WINDOW_MONTHS"],
        "share": round(100 * interesting / stored) if stored else None,
        "offline": evaluate()})


def about(request):
    """'O systemie': data sources, assumptions, limitations, what we do NOT claim."""
    sources = Source.objects.filter(status="active").annotate(
        fetched_count=Count("articles", filter=Q(articles__status="fetched", articles__duplicate_of__isnull=True)))
    return render(request, "web/about.html", {
        "sources": sources, "backend": settings.ANALYSIS["BACKEND"], "ttl": settings.RETENTION["QUEUE_TTL_HOURS"],
        "window": settings.ANALYSIS["WINDOW_MONTHS"], "threshold": thresholds()["main"],
        "weights": [(LABELS[k], w) for k, w in settings.ANALYSIS["WEIGHTS"].items()],
        "collect": settings.COLLECT, "max_mb": settings.COLLECT["MAX_BYTES"] // 1_000_000, "recipient_count": Recipient.objects.filter(active=True).count(),
        "article_count": Article.objects.filter(status="fetched", duplicate_of__isnull=True).count()})


def sources(request):
    now = timezone.now()
    entries = Source.objects.exclude(status__in=("candidate", "rejected")).annotate(
        article_count=Count("articles"),
        fetched_count=Count("articles", filter=Q(articles__status="fetched", articles__duplicate_of__isnull=True)),
        error_count=Count("articles", filter=Q(articles__status="error")))
    rows = [{"s": s, "running": bool(s.locked_until and s.locked_until > now),
             "overdue": bool(s.enabled and (not s.next_run_at or s.next_run_at < now))} for s in entries]
    candidates = Source.objects.filter(status="candidate").order_by("-discovery_score", "name")
    return render(request, "web/sources.html", {
        "rows": rows, "candidates": candidates,
        "rejected_count": Source.objects.filter(status="rejected").count(),
        "last_discovery": DiscoveryRun.objects.first()})


@require_POST
@staff_member_required
def review_candidate(request, pk, decision):
    source = get_object_or_404(Source, pk=pk, status="candidate")
    if decision == "approve":
        sourcefinder.approve(source)
        messages.success(request, f"Źródło „{source.name}” będzie monitorowane od kolejnego cyklu.")
    else:
        sourcefinder.reject(source)
        messages.info(request, f"Odrzucono „{source.name}”; nie będzie ponownie proponowane.")
    return redirect("sources")


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


def robots(request):
    return HttpResponse("User-agent: *\nDisallow: /admin/\nAllow: /\n", content_type="text/plain; charset=utf-8")


def favicon(request):
    from django.templatetags.static import static
    return redirect(static("web/favicon.svg"), permanent=True)


def health(request):
    Source.objects.exists()
    return JsonResponse({"status": "ok", "version": settings.APP_VERSION})


EXPORT_FIELDS = ["id", "tytul", "url", "zrodlo", "typ_instytucji", "wojewodztwo", "werdykt", "potencjal",
                 "kompletnosc", "sektor", "etap", "typ_innowacji", "sciezka", "priorytet_pci", "etap_obslugi",
                 "partner", "karta"]


def _export_rows(request):
    view = request.GET.get("widok", "glowna")
    view = view if view in TABS else "glowna"
    qs = (Article.objects.select_related("source", "analysis", "analysis__handling_partner", "submission")
          .filter(status="fetched", duplicate_of__isnull=True, analysis__isnull=False).filter(tab_q(view)))
    qs = _actor_filter(_region_filter(qs, request.GET.get("woj", "")), request.GET.get("kto", ""))
    qs = qs.order_by("-first_seen_at")[:2000]
    for a in qs:
        an, d = a.analysis, a.analysis.data
        yield {"id": a.pk, "tytul": a.title, "url": a.final_url or a.original_url, "zrodlo": a.source.name,
               "typ_instytucji": (a.submission.get_submitter_type_display() if hasattr(a, "submission")
                                  else a.source.get_organization_type_display()),
               "wojewodztwo": an.region or NATIONAL,
               "werdykt": (d.get("verdict") or {}).get("label", ""),
               "potencjal": an.potential, "kompletnosc": an.completeness, "sektor": an.sector,
               "etap": d.get("stage_label", ""), "typ_innowacji": ", ".join(d.get("innovation_types") or []),
               "sciezka": (d.get("path") or {}).get("label", ""), "priorytet_pci": an.priority,
               "etap_obslugi": an.get_handling_display(),
               "partner": an.handling_partner.name if an.handling_partner else "",
               "karta": request.build_absolute_uri(f"/a/{a.pk}/")}


def export(request, fmt):
    """Innovations for other systems (CRM, spreadsheets, BI). No personal data: authors and contacts are omitted."""
    if fmt not in ("json", "csv"):
        raise Http404("Dostępne formaty: json, csv.")
    rows = list(_export_rows(request))
    if fmt == "json":
        return JsonResponse({"count": len(rows), "fields": EXPORT_FIELDS, "results": rows},
                            json_dumps_params={"ensure_ascii": False})
    import csv
    from django.http import HttpResponse
    response = HttpResponse(content_type="text/csv; charset=utf-8")
    response["Content-Disposition"] = 'attachment; filename="radar-innowacji.csv"'
    response.write("\ufeff")  # Excel opens UTF-8 correctly
    writer = csv.DictWriter(response, fieldnames=EXPORT_FIELDS, delimiter=";")
    writer.writeheader()
    writer.writerows(rows)
    return response


def status(request):
    return JsonResponse({
        "version": settings.APP_VERSION, "sources": Source.objects.filter(enabled=True).count(),
        "articles": Article.objects.filter(status="fetched", duplicate_of__isnull=True).count(),
        "pending": Article.objects.filter(status="found").count(),
        "errors": Article.objects.filter(status="error").count(),
        "runs": CollectionRun.objects.count(), "demo_mode": settings.DEMO_MODE,
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
        final_url, published_at = "", None
        if not text:
            try:
                final_url, html = safe_get(url)
                data = extract_article(html, final_url)
            except Exception as exc:
                data = None
                form.add_error("url", f"Nie udało się pobrać strony ({type(exc).__name__}). Wklej opis ręcznie.")
            if data and len(data["text"]) >= 150:
                text, title = data["text"], title or data["title"]
                published_at = data.get("published_at")
            elif not form.errors:
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
                status="fetched", fetched_at=timezone.now(), published_at=published_at)
            d = form.cleaned_data
            consent = bool(d["consent"])
            Submission.objects.create(
                article=article, submitter_type=d["submitter_type"] or "other", organization=d["organization"].strip(),
                region=d["region"], consent=consent,
                author_name=d["author_name"].strip() if consent else "",
                show_name=bool(consent and d["show_name"] and d["author_name"].strip()),
                contact=d["contact"].strip() if consent else "")
            try:
                analyze_article(article)
                messages.success(request, "Zgłoszenie zapisane i przeanalizowane.")
            except LLMError:   # quota / network / bad answer: the submission is kept, the collector retries later
                messages.warning(request, "Zgłoszenie zapisane. Analiza zostanie wykonana automatycznie później.")
            return redirect("detail", pk=article.pk)
    return render(request, "web/submit.html", {"form": form})
