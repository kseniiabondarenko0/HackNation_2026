import json

from django.core.management.base import BaseCommand, CommandError

from analysis import demo


class Command(BaseCommand):
    help = ("Writes the demonstration set (analysis/data/demo_innovations.json) from the AI-confirmed publications of the "
            "current database. Only real items; dead links are dropped; no API keys, e-mails or phone numbers are allowed.")

    def add_arguments(self, parser):
        parser.add_argument("--limit", type=int, default=30)
        parser.add_argument("--per-source", type=int, default=4, help="At most N items per institution")
        parser.add_argument("--min-score", type=int, default=0)
        parser.add_argument("--no-check-links", action="store_true", help="Skip the HTTP check of each link (not for the final file)")
        parser.add_argument("--out", default=str(demo.DEMO_PATH))

    def handle(self, *args, **o):
        report = {}
        items = demo.export_items(o["limit"], o["per_source"], not o["no_check_links"], min_score=o["min_score"], report=report)
        self.stdout.write(f"Kandydaci: {report}")
        if not items:
            raise CommandError("Brak potwierdzonych przez AI publikacji do wyeksportowania.")
        payload = demo.build_payload(items)
        problems = demo.check_clean(payload)
        if problems:
            raise CommandError(f"W zestawie są dane osobowe lub klucze ({problems[:5]}): plik nie został zapisany.")
        with open(o["out"], "w", encoding="utf-8") as fh:
            json.dump(payload, fh, ensure_ascii=False, indent=1)
            fh.write("\n")
        institutions = len({i["source"]["entry_url"] for i in items})
        self.stdout.write(self.style.SUCCESS(f"Zapisano {len(items)} publikacji z {institutions} instytucji do {o['out']}"))
        if len(items) < 20:
            self.stdout.write(self.style.WARNING("Mniej niż 20 pozycji: poczekaj na kolejne potwierdzone publikacje i uruchom ponownie."))
