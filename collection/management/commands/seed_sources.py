import json
from django.core.management.base import BaseCommand
from collection.models import Source
from collection.sourcefinder import DATA

FIELDS = ("name", "organization_type", "region", "discovery_type", "allowed_prefix", "feed_url")


def load_registry():
    return json.loads((DATA / "sources.json").read_text(encoding="utf-8"))


class Command(BaseCommand):
    help = ("Load the source registry (collection/data/sources.json). Verified entries are monitored; "
            "unverified registry entries wait for probe_sources or staff confirmation. "
            "Existing configuration is preserved.")

    def handle(self, *a, **o):
        counts = {"created": 0, "activated": 0, "exists": 0}
        for entry in load_registry():
            verified = bool(entry.get("verified"))
            defaults = {k: entry.get(k, "") for k in FIELDS}
            defaults.update(origin="registry", status="active" if verified else "candidate", enabled=verified)
            source, created = Source.objects.get_or_create(entry_url=entry["entry_url"], defaults=defaults)
            if not created and not source.region and entry.get("region"):
                Source.objects.filter(pk=source.pk).update(region=entry["region"])  # only fills a blank field
            if created:
                counts["created"] += 1
                state = "created " + ("(aktywne)" if verified else "(kandydat)")
            elif verified and source.origin == "registry" and source.status == "candidate" and not source.reviewed_at:
                Source.objects.filter(pk=source.pk).update(status="active", enabled=True)
                counts["activated"] += 1
                state = "activated"
            else:
                counts["exists"] += 1
                state = "exists "
            self.stdout.write(f"{state} {entry['name']}")
        self.stdout.write(f"Rejestr: {counts}")
