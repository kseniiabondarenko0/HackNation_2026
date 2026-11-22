from django.core.management.base import BaseCommand
from analysis import service
from analysis.models import LLMState


class Command(BaseCommand):
    help = "Analyze fetched articles (cached; use --force to recompute). Default backend ai requires a configured provider; rules is explicit offline mode."

    def add_arguments(self, parser):
        parser.add_argument("--force", action="store_true")
        parser.add_argument("--backend", choices=("ai", "rules"), default=None)
        parser.add_argument("--max-calls", type=int, default=None,
                            help="max article analysis attempts (0 = none); HTTP retries/fallback share daily counters")

    def handle(self, *args, **options):
        n = service.analyze_pending(options["backend"], options["force"], options["max_calls"])
        self.stdout.write(f"Przeanalizowano: {n}")
        if service.last_stats:
            self.stdout.write(f"AI: {service.last_stats}")
        for state in LLMState.objects.exclude(blocked_until=None):
            self.stdout.write(f"  {state.provider}: wstrzymany do {state.blocked_until:%H:%M} ({state.last_error[:80]})")
        self.stdout.write(f"Etapy: {service.pipeline_counts()}")
