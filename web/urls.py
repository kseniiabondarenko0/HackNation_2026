from django.urls import path
from . import views
urlpatterns = [
    path("", views.radar, name="radar"),
    path("a/<int:pk>/", views.detail, name="detail"),
    path("zglos/", views.submit, name="submit"),
    path("zrodla/", views.sources, name="sources"),
    path("zrodla/<int:pk>/sprawdz/", views.request_scan, name="request_scan"),
    path("przebiegi/", views.runs, name="runs"),
    path("health/", views.health, name="health"),
    path("api/szukaj/", views.api_search, name="api_search"),
    path("api/status/", views.status, name="status"),
]
