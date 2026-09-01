from django.contrib import admin
from django.urls import path

from football.reporting.views import daily_view, historical_view

urlpatterns = [
    path("", historical_view, name="reporting-home"),
    path("daily/", daily_view, name="reporting-daily"),
    path("admin/", admin.site.urls),
]
