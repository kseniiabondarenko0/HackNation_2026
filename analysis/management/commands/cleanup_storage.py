from django.core.management.base import BaseCommand, CommandError
from django.db import connection
from django.utils import timezone

from analysis.retention import backup_db, cleanup, counts
from collection.models import Article


class Command(BaseCommand):
    help = ("Storage policy (analysis.retention): deletes rejected, duplicate, outdated and expired items, bounds the queue, "
            "the registry and the archive. Dry run unless --apply; --apply takes a database backup first. The same policy "
            "runs automatically in every collection cycle.")

    def add_arguments(self, parser):
        parser.add_argument("--apply", action="store_true")
        parser.add_argument("--restart-queue-clock", action="store_true",
                            help="One-off: unconfirmed items get a fresh queue TTL (use once after introducing the policy)")
        parser.add_argument("--no-vacuum", action="store_true", help="Do not shrink the database file afterwards")

    def handle(self, *args, **o):
        apply = o["apply"]
        before = counts()
        self.stdout.write(f"Przed: {before}")

        def restart():
            n = (Article.objects.filter(status="fetched", duplicate_of__isnull=True, submission__isnull=True)
                 .exclude(analysis__backend="ai", analysis__verdict="glowna").update(first_seen_at=timezone.now()))
            self.stdout.write(f"Zegar kolejki (TTL) zrestartowany dla: {n}")

        if apply:
            try:
                path = backup_db(force=True)
            except Exception as exc:
                raise CommandError(f"Kopia zapasowa nieudana, nic nie usunięto: {exc}") from exc
            self.stdout.write(f"Kopia zapasowa: {path or 'brak (baza nie jest plikiem SQLite)'}")
        stats = cleanup(dry=not apply, before=restart if o["restart_queue_clock"] else None)
        self.stdout.write(("Wykonano: " if apply else "Próba (bez zmian): ") + str({k: v for k, v in stats.items() if v}))
        if apply:
            if not o["no_vacuum"] and connection.vendor == "sqlite":
                connection.cursor().execute("VACUUM")
            self.stdout.write(f"Po: {counts()}")
        else:
            self.stdout.write("Dodaj --apply, aby wykonać (najpierw powstanie kopia zapasowa).")
