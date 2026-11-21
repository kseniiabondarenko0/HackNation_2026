import time
from django.core.management.base import BaseCommand
from collection.services import run_source, due_sources
from collection.models import Source


class Command(BaseCommand):
    help = "Collect new articles from enabled sources. --once = single pass; otherwise loop (worker)."

    def add_arguments(self, p):
        p.add_argument("--once", action="store_true")
        p.add_argument("--all", action="store_true", help="ignore next_run_at")
        p.add_argument("--poll", type=int, default=60)

    def handle(self, *a, **o):
        while True:
            qs = Source.objects.filter(enabled=True) if o["all"] else due_sources()
            for s in qs:
                st = run_source(s)
                self.stdout.write(f"{s.name}: {st}" + (f"  ERROR: {s.last_error}" if s.last_error else ""))
            if o["once"]:
                return
            time.sleep(o["poll"])
