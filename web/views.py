from django.shortcuts import render, get_object_or_404
from collection.models import Article, Source


def radar(request):
    qs = Article.objects.select_related("source").filter(status="fetched", duplicate_of__isnull=True)
    if s := request.GET.get("source"):
        qs = qs.filter(source_id=s)
    if q := request.GET.get("q"):
        qs = qs.filter(text__icontains=q) | qs.filter(title__icontains=q)
    return render(request, "web/radar.html", {"articles": qs[:200], "sources": Source.objects.all(), "q": q or ""})


def detail(request, pk):
    return render(request, "web/detail.html", {"a": get_object_or_404(Article.objects.select_related("source"), pk=pk)})


def sources(request):
    return render(request, "web/sources.html", {"sources": Source.objects.all()})
