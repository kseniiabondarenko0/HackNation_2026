import json
from django.core.management.base import BaseCommand
from django.utils import timezone
from collection.models import Source
from collection.sourcefinder import DATA, apply_probe, probe_site


class Command(BaseCommand):
    help = ("Check sources: robots.txt, reachable page, RSS/sitemap and a news listing with >=3 links. "
            "--registry checks collection/data/sources.json (with --write it saves the result there); "
            "otherwise sources in the database are checked and registry candidates that pass are activated.")

    def add_arguments(self, parser):
        parser.add_argument("--registry", action="store_true")
        parser.add_argument("--write", action="store_true", help="With --registry: update sources.json")
        parser.add_argument("--only-unverified", action="store_true")
        parser.add_argument("--source", type=int, action="append", help="Database source id (repeatable)")

    def handle(self, *a, **o):
        if o["registry"]:
            return self._registry(o)
        qs = Source.objects.exclude(status="rejected").exclude(entry_url__startswith="https://radar.local")
        if o["source"]:
            qs = qs.filter(pk__in=o["source"])
        ok = failed = 0
        for source in qs.order_by("pk"):
            report = probe_site(source.entry_url)
            apply_probe(source, report)
            if report["ok"] and source.origin == "registry" and source.status == "candidate" and not source.reviewed_at:
                Source.objects.filter(pk=source.pk).update(status="active", enabled=True, next_run_at=timezone.now())
            ok, failed = ok + report["ok"], failed + (not report["ok"])
            self._line(source.name, report)
        self.stdout.write(f"OK: {ok}, błędy: {failed}")

    def _registry(self, o):
        path = DATA / "sources.json"
        entries = json.loads(path.read_text(encoding="utf-8"))
        ok = failed = 0
        for entry in entries:
            if o["only_unverified"] and entry.get("verified"):
                continue
            report = probe_site(entry["entry_url"])
            self._line(entry["name"], report)
            ok, failed = ok + report["ok"], failed + (not report["ok"])
            if not o["write"]:
                continue
            entry["checked_at"] = timezone.now().date().isoformat()
            entry["verified"] = report["ok"]
            if report["ok"]:
                entry.update(entry_url=report["entry_url"], discovery_type=report["discovery_type"],
                             allowed_prefix=report["allowed_prefix"], feed_url=report["feed_url"],
                             note=f"probe: {report['article_links']} linków, robots OK")
            else:
                entry["note"] = "probe: " + "; ".join(report["errors"])[:300]
        if o["write"]:
            urls = [e["entry_url"] for e in entries]
            if len(urls) != len(set(urls)):
                self.stderr.write("Uwaga: zduplikowane entry_url w rejestrze po weryfikacji.")
            path.write_text(json.dumps(entries, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
            self.stdout.write(f"Zapisano {path}")
        self.stdout.write(f"OK: {ok}, błędy: {failed}")

    def _line(self, name, r):
        if r["ok"]:
            self.stdout.write(f"OK    {name}: {r['discovery_type']} {r['entry_url']} "
                              f"(linków {r['article_links']}, prefiks {r['allowed_prefix']})")
        else:
            self.stdout.write(f"BŁĄD  {name}: {'; '.join(r['errors'])}")
