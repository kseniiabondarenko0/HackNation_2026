"""Task, section 6: run the demo scenario a)–e) on two use cases and print the result.

Case A: a technological innovation from a university. Case B: an organisational innovation from local government.
Both go through the same pipeline as the 'Zgłoś innowację' form, so they also appear in the web interface.
"""
from django.core.management.base import BaseCommand
from django.utils import timezone
from analysis.evaluation import evaluate
from analysis.examples import EXAMPLES
from analysis.external import external_search
from analysis.service import analyze_article
from collection.extract import content_hash
from collection.models import Article, Source
from matching.recipients import match_recipients
from matching.similar import similar

CASES = [("A — innowacja technologiczna (uczelnia)", "czujnik-sepsy"),
         ("B — innowacja organizacyjna (samorząd)", "gmina-decyzje")]
SUBMIT_SOURCE = {"entry_url": "https://radar.local/zgloszenia/",
                 "defaults": {"name": "Zgłoszenia ręczne", "enabled": False, "organization_type": "other"}}


class Command(BaseCommand):
    help = "Scenariusz demonstracyjny a)–e) na dwóch przypadkach użycia (dodaje je też do bazy jako zgłoszenia)."

    def handle(self, *args, **o):
        source, _ = Source.objects.get_or_create(**SUBMIT_SOURCE)
        w = self.stdout.write
        for label, ex_id in CASES:
            ex = next(e for e in EXAMPLES if e["id"] == ex_id)
            digest = content_hash(ex["text"])
            article = Article.objects.filter(content_hash=digest).first() or Article.objects.create(
                source=source, original_url=f"https://radar.local/zgloszenie/{digest[:24]}", title=ex["title"],
                text=ex["text"], content_hash=digest, status="fetched", fetched_at=timezone.now())
            an, _ = analyze_article(article, force=True)
            d = an.data
            w("\n" + "=" * 78 + f"\nPRZYPADEK {label}: {article.title}  (karta: /a/{article.pk}/)\n" + "=" * 78)
            w("a) Wprowadzenie: zgłoszenie przez ten sam potok co formularz / kolektor.")
            w(f"b) Uporządkowanie: typ innowacji: {', '.join(d['innovation_types'])}; sektor: {d['sector']}; "
              f"etap: {d['stage_label']}; autorzy: {', '.join(d['authors']) or 'brak w tekście'}")
            w(f"c) Ocena: werdykt filtra: {d['verdict']['label']} — {d['verdict']['reason']}")
            for c in d["criteria"]:
                score = f"{c['score']}/3" if c["score"] is not None else "brak danych"
                w(f"     {c['label']:<12} {score:<12} „{c['quote'][:90]}”" if c["quote"] else f"     {c['label']:<12} {score}")
            w(f"   potencjał {d['potential']}/100, kompletność dowodów {d['completeness']}%")
            p = d["path"]
            w(f"d) Ścieżka: {p['label'] if p else 'brak'}" + (f" — {'; '.join(p['reasons'])}" if p else ""))
            if p and p["missing"]:
                w(f"   czego brakuje: {'; '.join(p['missing'])}")
            for m in match_recipients(article, d):
                w(f"   odbiorca: {m['recipient'].name} ({m['score']} pkt) — {m['reasons'][0]}")
            sim = similar(article, limit=2)
            w("   podobne w bazie: " + ("; ".join(f"{s['article'].title} ({s['percent']}%)" for s in sim) or "brak"))
            w(f"   bazy zewnętrzne: zapytanie „{external_search(article.title)['query']}” (Espacenet, UPRP, PBN, NCBR…)")
            w("e) Uzasadnienie: każda ocena ma cytat zweryfikowany w tekście (powyżej); mierniki — niżej i na /skutecznosc/.")
        r = evaluate()
        w("\n" + "=" * 78 + f"\nMIERNIKI na {len(r['rows'])} oznaczonych przykładach (analysis/examples.py):")
        for name, m in (("lista główna + weryfikacja", r["lenient"]), ("tylko lista główna", r["strict"])):
            w(f"  {name}: precyzja {100 * m['precision']:.0f}%, czułość {100 * m['recall']:.0f}% "
              f"(TP {m['tp']}, FP {m['fp']}, FN {m['fn']})")
