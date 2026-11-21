from django.db import models


class Source(models.Model):
    DISCOVERY = [("rss", "RSS/Atom"), ("sitemap", "Sitemap"), ("html", "Lista HTML")]
    ORG = [("university", "Uczelnia"), ("tech_park", "Park naukowo-technologiczny"),
           ("ctt", "Centrum transferu technologii"), ("research", "Instytut badawczy"),
           ("school", "Szkoła"), ("local_gov", "Samorząd"), ("agency", "Agencja publiczna"),
           ("company", "Firma prywatna"), ("ngo", "Organizacja pozarządowa"), ("person", "Osoba prywatna"),
           ("other", "Inna")]
    STATUS = [("active", "Monitorowane"), ("candidate", "Kandydat"), ("rejected", "Odrzucone")]
    ORIGIN = [("registry", "Rejestr"), ("discovery", "Automatyczne wyszukiwanie"), ("manual", "Ręcznie")]
    name = models.CharField(max_length=200)
    entry_url = models.URLField(max_length=500, unique=True)
    organization_type = models.CharField(max_length=20, choices=ORG, default="other")
    # Voivodeship of the institution ("" = national scope). Codes: analysis.regions.CODES.
    region = models.CharField(max_length=30, blank=True, db_index=True,
                              help_text="Województwo siedziby (puste = zasięg ogólnopolski).")
    discovery_type = models.CharField(max_length=10, choices=DISCOVERY, default="html")
    allowed_prefix = models.CharField(max_length=500, blank=True,
        help_text="Tylko linki zaczynające się od tego prefiksu (domyślnie: katalog adresu startowego)")
    enabled = models.BooleanField(default=True)
    status = models.CharField(max_length=10, choices=STATUS, default="active", db_index=True,
        help_text="Kandydaci z automatycznego wyszukiwania nie są zbierani, dopóki ekspert ich nie zatwierdzi.")
    origin = models.CharField(max_length=10, choices=ORIGIN, default="manual")
    feed_url = models.URLField(max_length=500, blank=True)
    sitemap_url = models.URLField(max_length=500, blank=True)
    robots_allowed = models.BooleanField(null=True, blank=True)
    probe_report = models.JSONField(default=dict, blank=True)
    probed_at = models.DateTimeField(null=True, blank=True)
    discovery_query = models.CharField(max_length=300, blank=True)
    discovery_score = models.IntegerField(default=0)
    discovered_at = models.DateTimeField(null=True, blank=True)
    reviewed_at = models.DateTimeField(null=True, blank=True)
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


class DiscoveryRun(models.Model):
    """One automatic search for new candidate sources."""
    started_at = models.DateTimeField(auto_now_add=True)
    finished_at = models.DateTimeField(null=True, blank=True)
    queries = models.JSONField(default=list)
    providers = models.JSONField(default=list)
    stats = models.JSONField(default=dict)
    error = models.TextField(blank=True)

    class Meta:
        ordering = ["-started_at"]


class Submission(models.Model):
    """Who submitted an innovation through the form. Schools, firms and private persons can submit too.

    Personal data (author, contact) is stored only with consent; the author's name is public only if they chose so;
    the contact is visible to the logged-in team only and never exported."""
    article = models.OneToOneField(Article, on_delete=models.CASCADE, related_name="submission")
    submitter_type = models.CharField(max_length=20, choices=Source.ORG, default="other", db_index=True)
    organization = models.CharField(max_length=200, blank=True)
    region = models.CharField(max_length=30, blank=True)
    author_name = models.CharField(max_length=200, blank=True)
    show_name = models.BooleanField(default=False)
    contact = models.CharField(max_length=200, blank=True)
    consent = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"Zgłoszenie #{self.article_id} ({self.get_submitter_type_display()})"
