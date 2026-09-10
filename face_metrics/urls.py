from django.contrib import admin
from django.urls import path

urlpatterns = [
    path("admin/", admin.site.urls),
    # path("api/", include("core.api_urls")),  # descomentar na Fase 2 (DRF)
]
