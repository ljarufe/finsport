# -*- coding: utf-8 -*-

import logging

from datetime import timedelta, datetime

from django.db import models
from django.db.models import Max

from django_countries import countries
from django_countries.fields import CountryField
from django_extensions.db.models import TimeStampedModel


logger_leagues = logging.getLogger('leagues')


class League(TimeStampedModel):
    name = models.CharField(max_length=250)
    country = CountryField(blank_label='(select country)')
    draw_percentage = models.FloatField(blank=True, null=True)

    def __str__(self):
        return "{country} {name}".format(
            country=self.country.name, name=self.name)

    @classmethod
    def get_league(cls, league_name, country):
        # TODO: El preprocesarmiento antes de la consulta depende de la casa
        #  de apuestas
        league = League.objects.filter(
            country=country, name__unaccent__trigram_similar=league_name,
            leaguerelatedname=None)
        if league.exists():
            return league.first()

        return None


class LeagueRelatedName(models.Model):
    league = models.ForeignKey('football.League', on_delete=models.CASCADE)
    bet_page = models.ForeignKey('accounts.BetPage', on_delete=models.CASCADE)
    name = models.CharField(max_length=250)

    def __str__(self):
        return "{bet_page}: {name}".format(
            bet_page=self.bet_page, name=self.name)

    @classmethod
    def get_league(cls, league_name, country, bet_page):
        country = countries.by_name(country, language="es")
        if country:
            related_league = cls.objects.filter(
                name__unaccent__iexact=league_name, league__country=country,
                bet_page=bet_page)
            if related_league.exists():
                return related_league.first().league
            league = League.get_league(league_name, country)
            if league:
                related_league, created = cls.objects.update_or_create(
                    league=league,
                    bet_page=bet_page,
                    defaults={'name': league_name})
                if created:
                    logger_leagues.info(
                        "Related league created: %s (%s)" % (league, bet_page))
                return league

        return None


class Team(TimeStampedModel):
    name = models.CharField(max_length=250)
    league = models.ForeignKey(
        'football.League', on_delete=models.CASCADE, null=True, blank=True)

    def __str__(self):
        return "{name}: {league}".format(name=self.name, league=self.league)


class Match(TimeStampedModel):
    NEW = 'N'
    USED = 'U'
    PLAYING = 'P'
    LOCAL = 'L'
    DRAW = 'R'
    VISITOR = 'V'
    NOT_USED = 'T'
    STATES = (
        ('N', 'new'),
        ('U', 'used'),
        ('P', 'playing'),
        ('L', 'local'),
        ('R', 'draw'),
        ('V', 'visitor'),
        ('T', 'not used'),
    )
    local_team = models.ForeignKey(
        'football.Team', on_delete=models.CASCADE, related_name='local_team')
    visitor_team = models.ForeignKey('football.Team', on_delete=models.CASCADE)
    local_score = models.PositiveSmallIntegerField(null=True, blank=True)
    visitor_score = models.PositiveSmallIntegerField(null=True, blank=True)
    inkabet_url = models.CharField(max_length=150, blank=True)
    state = models.CharField(max_length=1, choices=STATES, default=NEW)
    local_factor = models.FloatField()
    draw_factor = models.FloatField()
    visitor_factor = models.FloatField()
    start_datetime = models.DateTimeField()
    score = models.FloatField(default=0)

    TEAM_DIFFERENCE = 3
    MIN_PER_TEAM = 1.5
    MIN_DRAW = 2.8
    MAX_DRAW = 4.2

    MAX_SCORE_DIFFERENCE = 5
    MAX_SCORE_DRAW = 3
    MIN_SCORE_LEAGUE = 20

    TRIAL_LAPSE = 300

    @property
    def league(self):
        return self.local_team.league

    def __str__(self):
        return "{local} - {visitor} ({league}), {date}".format(
            local=self.local_team.name,
            visitor=self.visitor_team.name,
            league=self.league,
            date=self.start_datetime)

    def save(self, **kwargs):
        self.score = (
                self.get_team_difference_score() +
                self.get_draw_score() +
                self.get_league_score())
        super().save(**kwargs)

    def set_new(self):
        self.state = Match.NEW
        self.save()

    def set_used(self):
        self.state = Match.USED
        self.save()

    def set_playing(self):
        self.state = Match.PLAYING
        self.save()

    def set_draw(self):
        self.state = Match.DRAW
        self.save()

    def set_not_used(self):
        self.state = Match.NOT_USED
        self.save()

    def get_team_difference_score(self):
        return (Match.MAX_SCORE_DIFFERENCE * (
                1 - abs(self.local_factor - self.visitor_factor) /
                Match.TEAM_DIFFERENCE))

    def get_draw_score(self):
        return 2 * self.draw_factor - 6

    def get_league_score(self):
        limit = League.objects.aggregate(Max('draw_percentage'))

        return 2 * (self.league.draw_percentage - Match.MIN_SCORE_LEAGUE) / (
                limit['draw_percentage__max'] - Match.MIN_SCORE_LEAGUE)

    def get_match_name(self):
        return "{local} - {visitor}".format(
            local=self.local_team.name, visitor=self.visitor_team.name)

    def get_match_score(self):
        if self.local_score is not None:
            return "{local_score} - {visitor_score}".format(
                local_score=self.local_score, visitor_score=self.visitor_score)
        else:
            return "-"

    def get_logger_info(self):
        return "{id}: {local} - {visitor}, {start}".format(
            id=self.id,
            local=self.local_team.name,
            visitor=self.visitor_team.name,
            start=self.start_datetime
        )

    def is_suspended(self):
        difference = (datetime.now() - self.start_datetime).total_seconds() / 60

        return Match.TRIAL_LAPSE < difference

    def check_rules(self):
        if abs(self.local_factor - self.visitor_factor) > Match.TEAM_DIFFERENCE:
            return False, "Too much difference in teams"
        if not Match.MIN_DRAW <= self.draw_factor <= Match.MAX_DRAW:
            return False, "Draw beyond limits"
        if self.league.draw_percentage < Match.MIN_SCORE_LEAGUE:
            return False, "League draw percentage is too low"
        if (self.local_factor < Match.MIN_PER_TEAM or
                self.visitor_factor < Match.MIN_PER_TEAM):
            return False, "Teams are too secure to win"

        return True, ""

    @classmethod
    def get_best_match(cls):
        return cls.objects.filter(
            state=Match.NEW,
            start_datetime__gte=datetime.now() + timedelta(minutes=5),
            start_datetime__lte=datetime.now() + timedelta(minutes=65)
        ).order_by('score').last()

    class Meta:
        verbose_name = "match"
        verbose_name_plural = "matches"
