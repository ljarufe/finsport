from django.conf import settings
from django.shortcuts import render

from .selectors import home, match_detail, matches_day


def _navigation():
    return {"grafana_url": settings.FINSPORT_GRAFANA_URL}


def home_view(request):
    return render(request, "reporting/inicio.html", {**home(), **_navigation()})


def matches_view(request):
    return render(
        request,
        "reporting/partidos.html",
        {**matches_day(request.GET), **_navigation()},
    )


def match_detail_view(request, match_id):
    return render(request, "reporting/partido_detalle.html", match_detail(match_id))
