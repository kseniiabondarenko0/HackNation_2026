from django.core.management.base import BaseCommand
from collection.sourcefinder import run_discovery


class Command(BaseCommand):
    help = ("Find new candidate sources: search queries -> sites -> robots/RSS/sitemap check -> "
            "candidate, automatically activated when DISCOVERY_AUTO_APPROVE=1; staff may correct sources.")

    def add_arguments(self, parser):
        parser.add_argument("--query", action="append", help="Search query (repeatable); default: settings")
        parser.add_argument("--provider", action="append",
                            help="searxng, brave, seeds, links (repeatable); default: settings")
        parser.add_argument("--limit", type=int, help="Max new candidates")
        parser.add_argument("--dry-run", action="store_true", help="Do not save candidates")

    def handle(self, *a, **o):
        run = run_discovery(queries=o["query"], providers=o["provider"], limit=o["limit"],
                            dry_run=o["dry_run"], log=self.stdout.write)
        s = run.stats
        self.stdout.write(
            f"Dostawcy: {', '.join(s.get('providers_used', [])) or 'brak'}; trafień {s.get('hits', 0)}, "
            f"nowych domen {s.get('unique_hosts', 0)}, znanych {s.get('known', 0)}, sprawdzonych {s.get('probed', 0)}, "
            f"odrzuconych {s.get('probe_failed', 0)}, nowych kandydatów {s.get('created', 0)}")
        if s.get("provider_errors"):
            self.stdout.write(f"Błędy dostawców: {s['provider_errors']}")
        if run.error:
            self.stderr.write(run.error)
