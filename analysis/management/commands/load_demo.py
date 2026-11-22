from django.core.management.base import BaseCommand, CommandError

from analysis import demo
from analysis.retention import counts


class Command(BaseCommand):
    help = ("Loads the demonstration set (real publications confirmed by the AI, preliminary scores) into a clean installation. "
            "Idempotent; inserts only; does nothing when the base already holds its own records (unless --force).")

    def add_arguments(self, parser):
        parser.add_argument("--force", action="store_true", help="Add missing demo items even if the base is not empty (existing records are never changed)")
        parser.add_argument("--dry-run", action="store_true")
        parser.add_argument("--file", default=str(demo.DEMO_PATH))

    def handle(self, *args, **o):
        try:
            r = demo.load(o["file"], force=o["force"], dry=o["dry_run"])
        except demo.DemoError as exc:
            raise CommandError(str(exc)) from exc
        if r["refused"]:
            self.stdout.write(f"Baza zawiera już własne rekordy ({r['own_records']}): zestaw demo pominięty, nic nie zmieniono "
                              "(--force dodaje tylko brakujące pozycje demo).")
            return
        self.stdout.write(("Próba (bez zmian): " if o["dry_run"] else "") +
                          f"zestaw demo: {r['items']} pozycji; dodano {r['added']}, już były {r['existing']}, "
                          f"usunięte wcześniej {r['tombstoned']}, poza oknem wieku {r['too_old']}, "
                          f"nowe źródła {r['sources_created']}.")
        if not o["dry_run"]:
            self.stdout.write(f"Listy: {counts()}")
