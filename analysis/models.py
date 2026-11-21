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
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"Analiza #{self.article_id} ({self.backend})"
