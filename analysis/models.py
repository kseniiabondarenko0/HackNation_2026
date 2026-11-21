from django.db import models


class Analysis(models.Model):
    """Cached, reproducible analysis of one fetched article (one row per article)."""
    article = models.OneToOneField("collection.Article", on_delete=models.CASCADE, related_name="analysis")
    input_key = models.CharField(max_length=120)  # version:backend:content_hash -> cache validity
    backend = models.CharField(max_length=20)
    data = models.JSONField(default=dict)
    potential = models.PositiveSmallIntegerField(null=True, blank=True, db_index=True)
    completeness = models.PositiveSmallIntegerField(default=0)
    path = models.CharField(max_length=20, blank=True, db_index=True)
    signal = models.CharField(max_length=10, default="brak", db_index=True)
    sector = models.CharField(max_length=40, blank=True)
    stage = models.CharField(max_length=12, blank=True)
    # glowna (Interesujące) / weryfikacja (queue) / odrzucone (removed by analysis.retention); reason in data["verdict"]
    verdict = models.CharField(max_length=12, blank=True, db_index=True)
    updated_at = models.DateTimeField(auto_now=True)
    priority = models.PositiveSmallIntegerField(default=0, db_index=True)
    region = models.CharField(max_length=30, blank=True, db_index=True)  # voivodeship, see analysis.regions  # PCI bonus, used for ordering only
    # What happens after identification (task, section 9): handling stages with a history of changes.
    HANDLING = [("brak", "Nie rozpoczęto"), ("kontakt", "Kontakt z autorem"), ("przekazano", "Przekazano partnerowi"),
                ("pilotaz", "Pilotaż u partnera"), ("wdrozono", "Wdrożono / skomercjalizowano"),
                ("zamknieto", "Zamknięto bez kontynuacji")]
    handling = models.CharField(max_length=12, choices=HANDLING, default="brak", db_index=True)
    handling_partner = models.ForeignKey("matching.Recipient", null=True, blank=True, on_delete=models.SET_NULL,
                                         related_name="handled_innovations")
    handling_log = models.JSONField(default=list, blank=True)  # [{"status","label","partner","note","by","at"}]

    def __str__(self):
        return f"Analiza #{self.article_id} ({self.backend})"


class LLMUsage(models.Model):
    """Daily counters per AI provider (one row per day and provider): they enforce the free-tier limits."""
    day = models.DateField()
    provider = models.CharField(max_length=20)
    calls = models.PositiveIntegerField(default=0)
    tokens_in = models.PositiveIntegerField(default=0)
    tokens_out = models.PositiveIntegerField(default=0)
    errors = models.PositiveIntegerField(default=0)

    class Meta:
        unique_together = [("day", "provider")]

    def __str__(self):
        return f"{self.provider} {self.day}: {self.calls} wywołań"


class LLMState(models.Model):
    """Pause of a provider after a quota/auth/network error. Survives restarts, so a 429 is never hammered."""
    provider = models.CharField(max_length=20, unique=True)
    blocked_until = models.DateTimeField(null=True, blank=True)
    failures = models.PositiveSmallIntegerField(default=0)   # consecutive failures; 0 after a success
    last_error = models.CharField(max_length=300, blank=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"{self.provider}: {self.last_error or 'ok'}"
