from django.contrib import admin
from django.http import HttpResponse
from django.urls import path

from football.reporting.views import home_view, match_detail_view, matches_view


def healthz(_request):
    return HttpResponse("ok\n", content_type="text/plain")


urlpatterns = [
    path("healthz/", healthz, name="healthz"),
    path("", home_view, name="reporting-home"),
    path("partidos/", matches_view, name="reporting-matches"),
    path(
        "partidos/<int:match_id>/detalle/",
        match_detail_view,
        name="reporting-match-detail",
    ),
    path("admin/", admin.site.urls),
]
