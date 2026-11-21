from django.contrib import admin
from .models import Source, Article
@admin.register(Source)
class SourceAdmin(admin.ModelAdmin):
    list_display = ("name", "discovery_type", "enabled", "last_success", "last_error")
@admin.register(Article)
class ArticleAdmin(admin.ModelAdmin):
    list_display = ("title", "source", "status", "published_at", "first_seen_at")
    list_filter = ("status", "source")
