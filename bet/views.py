from collections import OrderedDict

from django.db.models import Sum

from rest_framework.response import Response
from rest_framework import viewsets
from rest_framework.pagination import LimitOffsetPagination

from .models import BetTable
from .serializers import BetTableSerializer


class BetTablePagination(LimitOffsetPagination):
    def __init__(self, *args, **kwargs):
        self.total = 0
        super().__init__(*args, **kwargs)

    def paginate_queryset(self, queryset, request, view=None):
        self.total = queryset.aggregate(total=Sum("total_profit"))["total"]

        return super().paginate_queryset(queryset, request, view=view)

    def get_paginated_response(self, data):
        return Response(
            OrderedDict(
                [
                    ("total", self.total),
                    ("count", self.count),
                    ("next", self.get_next_link()),
                    ("previous", self.get_previous_link()),
                    ("results", data),
                ]
            )
        )


class BetTableView(viewsets.ModelViewSet):  # pylint: disable=too-many-ancestors
    serializer_class = BetTableSerializer
    pagination_class = BetTablePagination

    def get_queryset(self):
        state = self.request.query_params.get("state", None)
        bet_tables = BetTable.objects.all()
        if state:
            bet_tables = bet_tables.filter(state=state)
            if state == "A":
                bet_tables = bet_tables.order_by("id")

        return bet_tables
