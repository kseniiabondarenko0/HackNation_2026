from django.contrib import admin
from .models import Recipient


@admin.register(Recipient)
class RecipientAdmin(admin.ModelAdmin):
    list_display = ("name", "institution_type", "region", "tags", "active", "is_example")
    list_filter = ("institution_type", "active", "is_example")
    search_fields = ("name", "needs", "tags")
