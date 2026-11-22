import logging
import signal
import time
from django.conf import settings
from django.core.management.base import BaseCommand, CommandError
from django.db import OperationalError, close_old_connections
from collection.services import run_source, due_sources
from collection.models import Source

logger = logging.getLogger(__name__)


class Command(BaseCommand):
    help = "Collect articles once or continuously according to each source schedule."

    def add_arguments(self, parser):
        parser.add_argument("--once", action="store_true")
        parser.add_argument("--all", action="store_true", help="Ignore schedule, not active source locks")
        parser.add_argument("--poll", type=int, default=15)

    def handle(self, *args, **options):
        if options["poll"] < 1:
            raise CommandError("--poll must be at least 1 second")
        previous = None
        if hasattr(signal, "SIGTERM"):
            try:
                previous = signal.signal(signal.SIGTERM, self._stop)
            except ValueError:
                pass  # command may be called from a test thread
        self.stdout.write("Kolektor uruchomiony; oczekiwanie na aktywne źródła.")
        try:
            while True:
                close_old_connections()
                try:
                    sources = Source.objects.filter(enabled=True, status="active") if options["all"] else due_sources()
                    ran = 0
                    for source in list(sources):
                        ran += 1
                        try:
                            stats = run_source(source)
                            self.stdout.write(f"{source.name}: {stats}" + (f" ERROR: {source.last_error}" if source.last_error else ""))
                        except Exception:
                            logger.exception("Unexpected source failure: %s", source.pk)
                        self._analyze(max_calls=settings.LLM.get("CALLS_PER_SOURCE", 2))
                    try:
                        from collection.sourcefinder import maybe_run_discovery
                        found = maybe_run_discovery()
                        if found is not None:
                            self.stdout.write(f"Wyszukiwanie źródeł: nowych kandydatów {found.stats.get('created', 0)}")
                    except Exception:
                        logger.exception("Source discovery failed; collection continues")
                    try:   # storage policy: rejected / duplicate / outdated / expired items go before they cost an AI call
                        from analysis.retention import maybe_cleanup
                        cleaned = maybe_cleanup(ran_sources=bool(ran))
                        if cleaned and any(v for k, v in cleaned.items() if k != "backup"):
                            self.stdout.write(f"Czyszczenie bazy: { {k: v for k, v in cleaned.items() if v} }")
                    except Exception:
                        logger.exception("Storage cleanup failed; collection continues")
                    self._analyze()
                except OperationalError:
                    if options["once"]:
                        raise
                    logger.exception("Database temporarily unavailable; retrying")
                if options["once"]:
                    return
                time.sleep(options["poll"])
        except KeyboardInterrupt:
            self.stdout.write("Kolektor zatrzymany.")
        finally:
            if previous is not None:
                signal.signal(signal.SIGTERM, previous)

    @staticmethod
    def _analyze(max_calls=None):
        try:
            from analysis.service import analyze_pending
            analyze_pending(max_calls=max_calls)
        except Exception:
            logger.exception("Analysis step failed; collection continues")

    @staticmethod
    def _stop(*args):
        raise KeyboardInterrupt
