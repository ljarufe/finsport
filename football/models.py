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
    related_name = models.CharField(max_length=250, unique=True)

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
    local_score = models.IntegerField(null=True, blank=True)
    visitor_score = models.IntegerField(null=True, blank=True)
    state = models.CharField(max_length=1, choices=STATES, default=NEW)
    local_factor = models.FloatField()
    draw_factor = models.FloatField()
    visitor_factor = models.FloatField()
    start_datetime = models.DateTimeField()
    score = models.FloatField(default=0)

    TEAM_DIFFERENCE = 3
    MIN_PER_TEAM = 1.5
    MIN_DRAW = 3
    MAX_DRAW = 4.5

    MAX_SCORE_DIFFERENCE = 5
    MAX_SCORE_DRAW = 3

    LAPSE = timedelta(minutes=130)
    TRIAL_LAPSE = 300

    def __str__(self):
        return "{local} - {visitor} ({league}), {date}".format(
            local=self.local_team.name,
            visitor=self.visitor_team.name,
            league=self.local_team.league,
            date=self.start_datetime)

    def save(self, **kwargs):
        self.score = self.get_team_difference_score() + self.get_draw_score()
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

    @classmethod
    def check_rules(cls, start_datetime, local, draw, visitor):
        if start_datetime < datetime.now() + timedelta(minutes=5):
            return False, "There is no time"
        if abs(local - visitor) > cls.TEAM_DIFFERENCE:
            return False, "Too much difference in teams"
        if not cls.MIN_DRAW < draw < cls.MAX_DRAW:
            return False, "Draw beyond limits"
        if local < cls.MIN_PER_TEAM or visitor < cls.MIN_PER_TEAM:
            return False, "Teams are too secure to win"

        return True, ""

    @classmethod
    def get_best_match(cls):
        return cls.objects.filter(
            state=Match.NEW,
            start_datetime__gte=datetime.now() + timedelta(minutes=5),
            start_datetime__lte=datetime.now() + Match.LAPSE
        ).order_by('score').last()

    class Meta:
        verbose_name = "match"
        verbose_name_plural = "matches"
