from rest_framework import serializers

from football.serializers import MatchSerializer
from .models import BetTable, BetRow


class BetRowSerializer(serializers.ModelSerializer):
    state = serializers.CharField(source='get_state_display')
    match = MatchSerializer()

    class Meta:
        model = BetRow
        fields = (
            'id',
            'bet_amount',
            'inversion_amount',
            'profit',
            'state',
            'iteration',
            'match',
        )


class BetTableSerializer(serializers.ModelSerializer):
    bet_rows = serializers.SerializerMethodField()

    class Meta:
        model = BetTable
        fields = (
            'id',
            'name',
            'total_profit',
            'total_inversion',
            'bet_rows',
        )

    def get_bet_rows(self, instance):
        bet_rows = instance.bet_rows.all().order_by('id')

        return BetRowSerializer(bet_rows, many=True).data
