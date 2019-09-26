from rest_framework import serializers

from football.serializers import MatchSerializer
from .models import BetTable, BetRow


class BetRowSerializer(serializers.ModelSerializer):
    state = serializers.CharField(source='get_state_display')
    match = MatchSerializer()

    class Meta:
        model = BetRow
        fields = (
            'bet_amount',
            'inversion_amount',
            'profit',
            'state',
            'iteration',
            'match',
        )


class BetTableSerializer(serializers.ModelSerializer):
    bet_rows = BetRowSerializer(many=True)

    class Meta:
        model = BetTable
        fields = (
            'id',
            'name',
            'total_profit',
            'total_inversion',
            'bet_rows',
        )
