from django.core.management.base import BaseCommand, CommandError
from collection import archive
from collection.models import Article
from collection.services import reject_article
from collection.window import cutoff


class Command(BaseCommand):
    help = ("Articles published before the window (default 8 months): full record -> archive file, then the row is "
            "replaced by a URL/hash/reason entry in the Rejected registry. Dry run unless --apply. "
            "Manual submissions are never touched. The same rule runs automatically (analysis.retention).")

    def add_arguments(self, parser):
        parser.add_argument("--apply", action="store_true")

    def handle(self, *args, **options):
        old = Article.objects.filter(published_at__date__lt=cutoff()).select_related("analysis", "source")
        old = list(old.filter(submission__isnull=True))
        if not options["apply"]:
            self.stdout.write(f"Starsze niż {cutoff():%d.%m.%Y}: {len(old)} (próba, bez zmian). "
                              f"Dodaj --apply: najpierw archiwum ({archive.path()}), potem usunięcie z bazy.")
            return
        try:   # the whole batch is archived before the first deletion
            written = archive.append(old, f"Starsze niż okno ({cutoff():%d.%m.%Y})")
        except OSError as exc:
            raise CommandError(f"Archiwum niezapisane, nic nie usunięto: {exc}")
        done = sum(reject_article(a, f"Starsze niż okno (publikacja {a.published_at:%d.%m.%Y}).") for a in old)
        self.stdout.write(f"Zarchiwizowano: {written}; usunięto z aktualnej bazy: {done}. Archiwum: {archive.path()}")
