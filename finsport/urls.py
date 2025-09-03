from django.contrib import admin
from django.urls import path, include

urlpatterns = [
    path("", admin.site.urls),
    path("bet/", include("bet.urls")),
    path("api/", include("rest_framework.urls", namespace="rest_framework")),
]
