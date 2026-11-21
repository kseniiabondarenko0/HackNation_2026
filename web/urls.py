from django.urls import path
from django.views.generic import TemplateView
from . import views, views_needs
urlpatterns = [
    path("", views.overview, name="overview"),
    path("inicjatywy/", views.radar, name="radar"),
    path("porownaj/", views.compare, name="compare"),
    path("a/<int:pk>/", views.detail, name="detail"),
    path("a/<int:pk>/dalej/", views.handling, name="handling"),
    path("zglos/", views.submit, name="submit"),
    path("skutecznosc/", views.effectiveness, name="effectiveness"),
    path("potrzeby/", views_needs.needs, name="needs"),
    path("potrzeby/zglos/", views_needs.need_submit, name="need_submit"),
    path("potrzeby/<int:pk>/", views_needs.need_detail, name="need_detail"),
    path("o-systemie/", views.about, name="about"),
    path("dla-kogo/", TemplateView.as_view(template_name="web/for_whom.html"), name="for_whom"),
    path("zrodla/", views.sources, name="sources"),
    path("zrodla/<int:pk>/sprawdz/", views.request_scan, name="request_scan"),
    path("zrodla/<int:pk>/zatwierdz/", views.review_candidate, {"decision": "approve"}, name="approve_candidate"),
    path("zrodla/<int:pk>/odrzuc/", views.review_candidate, {"decision": "reject"}, name="reject_candidate"),
    path("przebiegi/", views.runs, name="runs"),
    path("health/", views.health, name="health"),
    path("api/szukaj/", views.api_search, name="api_search"),
    path("api/status/", views.status, name="status"),
    path("api/innowacje.<str:fmt>", views.export, name="export"),
]
