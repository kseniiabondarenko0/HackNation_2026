from django.urls import path
from . import views
urlpatterns = [path("", views.radar, name="radar"), path("a/<int:pk>/", views.detail, name="detail"),
               path("zrodla/", views.sources, name="sources")]
