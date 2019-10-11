from rest_framework import viewsets

from .models import BetTable
from .serializers import BetTableSerializer


class BetTableView(viewsets.ModelViewSet):
    serializer_class = BetTableSerializer

    def get_queryset(self):
        state = self.request.query_params.get("state", None)
        bet_tables = BetTable.objects.all()
        if state:
            bet_tables = bet_tables.filter(state=state)
            if state == 'A':
                bet_tables = bet_tables.order_by('id')

        return bet_tables
