from django.core.management.base import BaseCommand
from analysis.service import analyze_pending


class Command(BaseCommand):
    help = "Analyze fetched articles (cached; use --force to recompute)."

    def add_arguments(self, parser):
        parser.add_argument("--force", action="store_true")
        parser.add_argument("--backend", default=None)

    def handle(self, *args, **options):
        n = analyze_pending(options["backend"], options["force"])
        self.stdout.write(f"Przeanalizowano: {n}")
