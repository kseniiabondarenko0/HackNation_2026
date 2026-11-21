from django.contrib import admin
from .models import Submission, Source, Article, CollectionRun, DiscoveryRun
from . import sourcefinder


@admin.register(Source)
class SourceAdmin(admin.ModelAdmin):
    list_display = ("name", "status", "organization_type", "region", "discovery_type", "enabled", "origin",
                    "discovery_score", "last_checked", "last_error")
    list_filter = ("status", "enabled", "origin", "organization_type", "region", "discovery_type")
    search_fields = ("name", "entry_url")
    readonly_fields = ("last_success", "last_checked", "last_stats", "locked_until", "last_error",
                       "probe_report", "probed_at", "discovered_at", "reviewed_at")
    actions = ["approve", "reject", "probe"]

    @admin.action(description="Zatwierdź: zacznij monitorować")
    def approve(self, request, queryset):
        for source in queryset:
            sourcefinder.approve(source)
        self.message_user(request, f"Zatwierdzono: {queryset.count()}")

    @admin.action(description="Odrzuć (nie będzie ponownie proponowane)")
    def reject(self, request, queryset):
        for source in queryset:
            sourcefinder.reject(source)
        self.message_user(request, f"Odrzucono: {queryset.count()}")

    @admin.action(description="Sprawdź robots.txt, RSS/sitemap i listę publikacji")
    def probe(self, request, queryset):
        ok = 0
        for source in queryset[:10]:
            ok += sourcefinder.apply_probe(source, sourcefinder.probe_site(source.entry_url)).probe_report["ok"]
        self.message_user(request, f"Sprawdzono {min(queryset.count(), 10)}, poprawnych: {ok}")


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


@admin.register(DiscoveryRun)
class DiscoveryRunAdmin(admin.ModelAdmin):
    list_display = ("started_at", "finished_at", "providers", "error")
    readonly_fields = ("started_at", "finished_at", "queries", "providers", "stats", "error")

    def has_add_permission(self, request):
        return False


@admin.register(Submission)
class SubmissionAdmin(admin.ModelAdmin):
    list_display = ("article", "submitter_type", "organization", "region", "consent", "created_at")
    list_filter = ("submitter_type", "region", "consent")
