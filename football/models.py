# -*- coding: utf-8 -*-
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
    factor = models.FloatField(null=True, blank=True)

    def __str__(self):
        return self.name


class Match(TimeStampedModel):
    MATCH_STATES = (
        (0, 'new'),
        (1, 'used'),
        (2, 'playing'),
        (3, 'local'),
        (4, 'parity'),
        (5, 'visitor'),
        (6, 'unknow'),
        (7, 'favorite'),
        (8, 'not used'),
    )
    local_team = models.ForeignKey(
        'football.Team', on_delete=models.CASCADE, related_name='local_team')
    visitor_team = models.ForeignKey('football.Team', on_delete=models.CASCADE)
    local_score = models.IntegerField(null=True, blank=True)
    visitor_score = models.IntegerField(null=True, blank=True)
    local_score_half_time = models.IntegerField(null=True, blank=True)
    visitor_score_half_time = models.IntegerField(null=True, blank=True)
    match_state = models.IntegerField(
        choices=MATCH_STATES, default=MATCH_STATES[0][0])
    match_state_half_time = models.IntegerField(
        choices=MATCH_STATES, default=MATCH_STATES[0][0])
    local_factor = models.FloatField()
    parity_factor = models.FloatField()
    visitor_factor = models.FloatField()
    local_factor_half_time = models.FloatField(null=True, blank=True)
    parity_factor_half_time = models.FloatField(null=True, blank=True)
    visitor_factor_half_time = models.FloatField(null=True, blank=True)
    start_datetime = models.DateTimeField()
    ent_datetime = models.DateTimeField(null=True, blank=True)

    def __str__(self):
        return '%s - %s' % (self.local_team.name, self.visitor_team.name)
