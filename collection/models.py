from django.db import models


class Source(models.Model):
    DISCOVERY = [("rss", "RSS/Atom"), ("sitemap", "Sitemap"), ("html", "Lista HTML")]
    ORG = [("university", "Uczelnia"), ("school", "Szkoła"), ("local_gov", "Samorząd"),
           ("agency", "Agencja publiczna"), ("other", "Inna")]
    name = models.CharField(max_length=200)
    entry_url = models.URLField(max_length=500, unique=True)
    organization_type = models.CharField(max_length=20, choices=ORG, default="other")
    discovery_type = models.CharField(max_length=10, choices=DISCOVERY, default="html")
    allowed_prefix = models.CharField(max_length=500, blank=True,
        help_text="Tylko linki zaczynające się od tego prefiksu (domyślnie: katalog adresu startowego)")
    enabled = models.BooleanField(default=True)
    interval_min = models.PositiveIntegerField(default=60)
    last_success = models.DateTimeField(null=True, blank=True)
    last_error = models.TextField(blank=True)
    next_run_at = models.DateTimeField(null=True, blank=True)
    last_checked = models.DateTimeField(null=True, blank=True)
    last_stats = models.JSONField(default=dict, blank=True)
    locked_until = models.DateTimeField(null=True, blank=True)

    def __str__(self):
        return self.name


class Article(models.Model):
    STATUS = [("found", "Znaleziony"), ("fetched", "Pobrany"), ("skipped", "Pominięty"), ("error", "Błąd")]
    source = models.ForeignKey(Source, on_delete=models.CASCADE, related_name="articles")
    original_url = models.URLField(max_length=800, unique=True)
    final_url = models.URLField(max_length=800, blank=True)
    title = models.CharField(max_length=500, blank=True)
    text = models.TextField(blank=True)
    content_hash = models.CharField(max_length=64, blank=True, db_index=True)
    published_at = models.DateTimeField(null=True, blank=True)   # from source, may be unknown
    first_seen_at = models.DateTimeField(auto_now_add=True)       # when WE found it
    fetched_at = models.DateTimeField(null=True, blank=True)
    status = models.CharField(max_length=10, choices=STATUS, default="found")
    error = models.TextField(blank=True)
    duplicate_of = models.ForeignKey("self", null=True, blank=True, on_delete=models.SET_NULL)
    fetch_attempts = models.PositiveIntegerField(default=0)
    next_retry_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-first_seen_at"]

    def __str__(self):
        return self.title or self.original_url


class CollectionRun(models.Model):
    STATUS = [("running", "W toku"), ("success", "Zakończony"),
              ("partial", "Częściowo"), ("error", "Błąd"), ("interrupted", "Przerwany")]
    source = models.ForeignKey(Source, on_delete=models.CASCADE, related_name="runs")
    started_at = models.DateTimeField(auto_now_add=True)
    finished_at = models.DateTimeField(null=True, blank=True)
    status = models.CharField(max_length=12, choices=STATUS, default="running")
    stats = models.JSONField(default=dict)
    error = models.TextField(blank=True)

    class Meta:
        ordering = ["-started_at"]
