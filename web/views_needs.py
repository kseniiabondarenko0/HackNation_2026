"""Organisations looking for solutions: submit a need, see matching innovations (task: łączenie z użytkownikami)."""
from django.contrib import messages
from django.shortcuts import render, get_object_or_404, redirect
from django.utils import timezone
from matching.models import Recipient
from matching.recipients import match_articles
from .forms import NeedForm


def needs(request):
    entries = Recipient.objects.filter(active=True, is_example=False).order_by("-submitted_at", "name")
    return render(request, "web/needs.html", {"needs": entries,
                                              "examples": Recipient.objects.filter(active=True, is_example=True).count()})


def need_submit(request):
    form = NeedForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        d = form.cleaned_data
        r = Recipient.objects.create(
            name=d["name"].strip(), institution_type=d["institution_type"], region=d["region"].strip(),
            needs=d["needs"].strip(), tags=d["tags"].strip(), sectors=", ".join(d["sectors"]),
            paths=", ".join(d["paths"]), is_example=False, active=True,
            contact=d["contact"].strip() if d["consent"] else "", consent=bool(d["consent"] and d["contact"]),
            submitted_at=timezone.now())
        messages.success(request, "Potrzeba zapisana. Poniżej innowacje z radaru, które do niej pasują.")
        return redirect("need_detail", pk=r.pk)
    return render(request, "web/need_form.html", {"form": form})


def need_detail(request, pk):
    r = get_object_or_404(Recipient, pk=pk, active=True)
    return render(request, "web/need_detail.html", {"r": r, "matches": match_articles(r)})
