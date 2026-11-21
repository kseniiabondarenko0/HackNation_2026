from django.contrib import admin
from .models import Source, Article, CollectionRun


@admin.register(Source)
class SourceAdmin(admin.ModelAdmin):
    list_display = ("name", "discovery_type", "enabled", "last_checked", "next_run_at", "last_error")
    list_filter = ("enabled", "discovery_type")
    readonly_fields = ("last_success", "last_checked", "last_stats", "locked_until", "last_error")


@admin.register(Article)
class ArticleAdmin(admin.ModelAdmin):
    list_display = ("title", "source", "status", "published_at", "first_seen_at")
    list_filter = ("status", "source")
    search_fields = ("title", "original_url")


@admin.register(CollectionRun)
class RunAdmin(admin.ModelAdmin):
    list_display = ("source", "started_at", "finished_at", "status")
    list_filter = ("status", "source")
    readonly_fields = ("source", "started_at", "finished_at", "status", "stats", "error")

    def has_add_permission(self, request):
        return False
