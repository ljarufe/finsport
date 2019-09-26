from rest_framework import viewsets

from .models import BetTable
from .serializers import BetTableSerializer


class BetTableView(viewsets.ModelViewSet):
    serializer_class = BetTableSerializer

    def get_queryset(self):
        state = self.request.query_params.get("state", None)
        if state:
            return BetTable.objects.filter(state=state)

        return BetTable.objects.all()
