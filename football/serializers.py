from django_countries.serializer_fields import CountryField
from rest_framework.serializers import ModelSerializer

from .models import Competition, Match, Team


class CompetitionSerializer(ModelSerializer):
    country = CountryField(country_dict=True)

    class Meta:
        model = Competition
        fields = ("id", "name", "country", "competition_type")


class TeamSerializer(ModelSerializer):
    competition = CompetitionSerializer()

    class Meta:
        model = Team
        fields = ("id", "name", "competition")


class MatchSerializer(ModelSerializer):
    home_team = TeamSerializer()
    away_team = TeamSerializer()

    class Meta:
        model = Match
        fields = (
            "id",
            "home_team",
            "away_team",
            "kickoff",
            "status_short",
            "status_long",
            "outcome",
            "home_score",
            "away_score",
        )
