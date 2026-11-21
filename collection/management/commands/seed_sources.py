from django.core.management.base import BaseCommand
from collection.models import Source

# Candidates from the plan (section 6.2). discovery_type/prefix must be verified on the first real run.
SEED = [
    dict(name="PWr — Aktualności", entry_url="https://pwr.edu.pl/uczelnia/aktualnosci", organization_type="university",
         discovery_type="html", allowed_prefix="https://pwr.edu.pl/uczelnia/aktualnosci/"),
    dict(name="UR — Aktualności", entry_url="https://www.ur.edu.pl/pl/uniwersytet/aktualnosci", organization_type="university",
         discovery_type="html", allowed_prefix="https://www.ur.edu.pl/pl/uniwersytet/aktualnosci/"),
]


class Command(BaseCommand):
    def handle(self, *a, **o):
        for d in SEED:
            _, created = Source.objects.get_or_create(entry_url=d["entry_url"], defaults=d)
            self.stdout.write(("created " if created else "exists  ") + d["name"])
