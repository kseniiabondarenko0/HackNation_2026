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
    # glowna / weryfikacja / odrzucone -- decides where the article is listed (reason in data["verdict"])
    verdict = models.CharField(max_length=12, blank=True, db_index=True)
    updated_at = models.DateTimeField(auto_now=True)
    priority = models.PositiveSmallIntegerField(default=0, db_index=True)
    region = models.CharField(max_length=30, blank=True, db_index=True)  # voivodeship, see analysis.regions  # PCI bonus, used for ordering only
    # Expert decision (human-in-the-loop). Never in update defaults, so re-analysis keeps it.
    REVIEW = [("nowy", "Nie oceniono"), ("zatwierdzony", "Zatwierdzone przez eksperta"),
              ("odrzucony", "Odrzucone przez eksperta")]
    review_status = models.CharField(max_length=12, choices=REVIEW, default="nowy", db_index=True)
    review_note = models.TextField(blank=True)
    reviewed_at = models.DateTimeField(null=True, blank=True)
    reviewed_by = models.CharField(max_length=150, blank=True)
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
