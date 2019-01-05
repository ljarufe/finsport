# -*- coding: utf-8 -*-
from django.urls import path

from bet.views import BetTableListView, StatisticView

app_name = 'bet'


urlpatterns = [
    path('tables/', BetTableListView.as_view(), name='bet-list'),
    path('statistics/', StatisticView.as_view(), name='statistics'),
]
