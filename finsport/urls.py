from django.contrib import admin
from django.http import HttpResponse
from django.urls import path

from football.reporting.views import daily_view, historical_view


def healthz(_request):
    return HttpResponse("ok\n", content_type="text/plain")


urlpatterns = [
    path("healthz/", healthz, name="healthz"),
    path("", historical_view, name="reporting-home"),
    path("daily/", daily_view, name="reporting-daily"),
    path("admin/", admin.site.urls),
]
