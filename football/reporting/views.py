from django.shortcuts import render

from .selectors import daily, historical


def historical_view(request):
    return render(request, "reporting/historical.html", historical(request.GET))


def daily_view(request):
    return render(request, "reporting/daily.html", daily(request.GET))
