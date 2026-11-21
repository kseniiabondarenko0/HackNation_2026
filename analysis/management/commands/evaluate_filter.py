import csv
from django.core.management.base import BaseCommand, CommandError
from analysis.evaluation import evaluate
from collection.models import Article

TRUE = {"tak", "1", "true", "t", "yes", "y"}
FALSE = {"nie", "0", "false", "f", "no", "n"}


def pct(x):
    return "—" if x is None else f"{100 * x:.0f}%"


class Command(BaseCommand):
    help = ("Ocena filtra innowacji: precision/recall na oznaczonych przykładach. "
            "--export plik.csv zapisuje zebrane artykuły do ręcznego oznaczenia, "
            "--labels plik.csv ocenia filtr na tych oznaczeniach (kolumna 'interesujace': tak/nie).")

    def add_arguments(self, parser):
        parser.add_argument("--labels", help="CSV z kolumnami id,interesujace (z --export)")
        parser.add_argument("--export", help="Zapisz CSV z artykułami z bazy do oznaczenia")

    def handle(self, *args, **o):
        if o["export"]:
            return self.export(o["export"])
        examples = self.load_labels(o["labels"]) if o["labels"] else None
        result = evaluate(examples) if examples is not None else evaluate()
        w = self.stdout.write
        w(f"{'przykład':<24} {'oczek.':<7} {'werdykt':<15} {'pot.':>4}  powód")
        for r in result["rows"]:
            mark = "" if r["label"] == (r["verdict"] != "odrzucone") else "  <-- BŁĄD"
            w(f"{r['id'][:24]:<24} {'tak' if r['label'] else 'nie':<7} {r['verdict_label']:<15} "
              f"{r['potential'] if r['potential'] is not None else '—':>4}  {r['reason']}{mark}")
        for name, m in (("łagodnie (lista główna + do weryfikacji)", result["lenient"]),
                        ("ściśle (tylko lista główna)", result["strict"])):
            w(f"\n{name}: precision {pct(m['precision'])}, recall {pct(m['recall'])} "
              f"(TP {m['tp']}, FP {m['fp']}, FN {m['fn']})")
        w(f"\nBłędy (łagodnie): {len(result['errors'])}")
        for r in result["errors"]:
            kind = "przepuszczony nieinteresujący" if not r["label"] else "odrzucony interesujący"
            w(f"- {r['id']}: {kind} — {r['reason']}")

    def export(self, path):
        qs = Article.objects.filter(status="fetched", duplicate_of__isnull=True).exclude(text="")
        with open(path, "w", newline="", encoding="utf-8-sig") as f:
            out = csv.writer(f)
            out.writerow(["id", "tytul", "url", "interesujace"])
            for a in qs:
                out.writerow([a.pk, a.title, a.final_url or a.original_url, ""])
        self.stdout.write(f"Zapisano {qs.count()} artykułów do {path}. Uzupełnij kolumnę 'interesujace' (tak/nie).")

    def load_labels(self, path):
        examples = []
        with open(path, encoding="utf-8-sig", newline="") as f:
            for row in csv.DictReader(f):
                value = (row.get("interesujace") or "").strip().lower()
                if value not in TRUE | FALSE:
                    continue
                a = Article.objects.filter(pk=row.get("id")).first()
                if a and a.text:
                    examples.append({"id": f"#{a.pk} {a.title[:18]}", "label": value in TRUE,
                                     "title": a.title, "text": a.text})
        if not examples:
            raise CommandError("Brak oznaczonych artykułów w pliku (kolumna 'interesujace': tak/nie).")
        return examples
