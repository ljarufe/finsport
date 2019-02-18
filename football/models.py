# -*- coding: utf-8 -*-

from datetime import timedelta, datetime

from django.db import models

from django_extensions.db.models import TimeStampedModel


class League(TimeStampedModel):
    name = models.CharField(max_length=250)
    country = models.CharField(max_length=128, blank=True)

    def __str__(self):
        return self.name


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

    TEAM_DIFFERENCE = 4
    MIN_PER_TEAM = 1.5
    MIN_PARITY = 3.2
    STEP_PARITY_FORMULA = 0.04
    LAPSE = timedelta(minutes=130)

    def __str__(self):
        return "{local} - {visitor} ({league}), {date}".format(
            local=self.local_team.name,
            visitor=self.visitor_team.name,
            league=self.local_team.league,
            date=self.start_datetime)

    def set_used(self):
        self.state = Match.USED
        self.save()

    def set_not_used(self):
        self.state = Match.NOT_USED
        self.save()

    def is_usable(self, iteration=1):
        is_usable = self.start_datetime > datetime.now() and Match.check_rules(
            self.local_factor,
            self.parity_factor,
            self.visitor_factor,
            iteration)
        if not is_usable:
            self.set_not_used()

        return is_usable

    def has_bet_time(self, bet_row):
        return self.start_datetime - bet_row.match.start_datetime > Match.LAPSE

    @classmethod
    def check_rules(cls, local, parity, visitor, iteration=0):
        if not abs(local - visitor) <= cls.TEAM_DIFFERENCE:
            return False
        if not (local >= cls.MIN_PER_TEAM) or not (visitor >= cls.MIN_PER_TEAM):
            return False
        if not parity >= cls.MIN_PARITY + cls.STEP_PARITY_FORMULA * iteration:
            return False

        return True

    class Meta:
        verbose_name = "match"
        verbose_name_plural = "matches"
