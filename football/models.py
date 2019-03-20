# -*- coding: utf-8 -*-

from datetime import timedelta, datetime

from django.db import models

from django_countries.fields import CountryField
from django_extensions.db.models import TimeStampedModel


class League(TimeStampedModel):
    name = models.CharField(max_length=250)
    country = CountryField(blank_label='(select country)')

    def __str__(self):
        return "{country} {name}".format(
            country=self.country.name, name=self.name)


class LeagueRelatedName(models.Model):
    league = models.ForeignKey(League, on_delete=models.CASCADE)
    related_name = models.CharField(max_length=250)

    def __str__(self):
        return self.related_name


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
    PARITY = 'R'
    VISITOR = 'V'
    UNKNOW = 'K'
    NOT_USED = 'T'
    STATES = (
        ('N', 'new'),
        ('U', 'used'),
        ('P', 'playing'),
        ('L', 'local'),
        # TODO: cambiar parity por draw en todo el código
        ('R', 'parity'),
        ('V', 'visitor'),
        ('K', 'unknow'),
        ('T', 'not used'),
    )
    local_team = models.ForeignKey(
        'football.Team', on_delete=models.CASCADE, related_name='local_team')
    visitor_team = models.ForeignKey('football.Team', on_delete=models.CASCADE)
    local_score = models.IntegerField(null=True, blank=True)
    visitor_score = models.IntegerField(null=True, blank=True)
    state = models.CharField(max_length=1, choices=STATES, default=NEW)
    local_factor = models.FloatField()
    parity_factor = models.FloatField()
    visitor_factor = models.FloatField()
    start_datetime = models.DateTimeField()

    TEAM_DIFFERENCE = 3
    MIN_PER_TEAM = 1.5
    MIN_PARITY = 2.5
    MAX_PARITY = 4.5
    LAPSE = timedelta(minutes=130)
    TRIAL_LAPSE = 300

    def __str__(self):
        return "{local} - {visitor} ({league}), {date}".format(
            local=self.local_team.name,
            visitor=self.visitor_team.name,
            league=self.local_team.league,
            date=self.start_datetime)

    def set_new(self):
        self.state = Match.NEW
        self.save()

    def set_used(self):
        self.state = Match.USED
        self.save()

    def set_playing(self):
        self.state = Match.PLAYING
        self.save()

    def set_not_used(self):
        self.state = Match.NOT_USED
        self.save()

    def get_match_name(self):
        return "{local} - {visitor}".format(
            local=self.local_team.name, visitor=self.visitor_team.name)

    def get_score(self):
        if self.local_score is not None:
            return "{local_score} - {visitor_score}".format(
                local_score=self.local_score, visitor_score=self.visitor_score)
        else:
            return "-"

    def is_usable(self):
        is_usable = Match.check_rules(
            self.start_datetime,
            self.local_factor,
            self.parity_factor,
            self.visitor_factor,
        )
        if not is_usable:
            self.set_not_used()

        return is_usable

    def has_bet_time(self, bet_row):
        return self.start_datetime - bet_row.match.start_datetime > Match.LAPSE

    def is_suspended(self):
        difference = (datetime.now() - self.start_datetime).total_seconds() / 60

        return Match.TRIAL_LAPSE < difference

    @classmethod
    def check_rules(cls, start_datetime, local, parity, visitor):
        if start_datetime < datetime.now() + timedelta(minutes=5):
            return False
        if abs(local - visitor) > cls.TEAM_DIFFERENCE:
            return False
        if not cls.MIN_PARITY < parity < cls.MAX_PARITY:
            return False
        if local < cls.MIN_PER_TEAM or visitor < cls.MIN_PER_TEAM:
            return False

        return True

    class Meta:
        verbose_name = "match"
        verbose_name_plural = "matches"
