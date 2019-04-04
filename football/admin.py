from django.contrib import admin

from .forms import LeagueForm
from .models import Match, Team, League, LeagueRelatedName


@admin.register(Match)
class MatchAdmin(admin.ModelAdmin):
    list_display = (
        'get_match_name', 'state', 'start_datetime', 'local_factor',
        'draw_factor', 'visitor_factor',)
    list_filter = ('state', 'start_datetime',)
    search_fields = ('local_team__name', 'visitor_team__name',)


@admin.register(Team)
class TeamAdmin(admin.ModelAdmin):
    list_display = ('name', 'league',)
    search_fields = ('name', 'league__name')
    list_filter = ('league',)


class LeagueRelatedNameAdminInline(admin.TabularInline):
    model = LeagueRelatedName


@admin.register(League)
class LeagueAdmin(admin.ModelAdmin):
    list_display = ('name', 'country',)
    list_filter = ('country',)
    ordering = ('country',)
    search_fields = ('name',)
    form = LeagueForm
    inlines = (LeagueRelatedNameAdminInline,)
