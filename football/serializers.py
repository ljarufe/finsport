from rest_framework.serializers import ModelSerializer
from django_countries.serializer_fields import CountryField

from .models import Match, Team, League


class LeagueSerializer(ModelSerializer):
    country = CountryField(country_dict=True)

    class Meta:
        model = League
        fields = (
            "name",
            "country",
        )


class TeamSerializer(ModelSerializer):
    league = LeagueSerializer()

    class Meta:
        model = Team
        fields = (
            "name",
            "league",
        )


class MatchSerializer(ModelSerializer):
    local_team = TeamSerializer()
    visitor_team = TeamSerializer()

    class Meta:
        model = Match
        fields = (
            "local_team",
            "visitor_team",
            "start_datetime",
            "local_score",
            "visitor_score",
            "local_factor",
            "visitor_factor",
            "draw_factor",
        )
