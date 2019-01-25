from django.contrib import admin

from .models import Match, Team, League, LeagueRelatedName


class MatchAdmin(admin.ModelAdmin):

    list_display = (
        '__str__',
        'state',
        'start_datetime',
        'local_factor',
        'parity_factor',
        'visitor_factor',
    )

    list_filter = (
        'state',
        'parity_factor',
        'start_datetime',
    )

    search_fields = ('local_team__name', 'visitor_team__name')


class TeamAdmin(admin.ModelAdmin):
    ordering = ('name',)
    list_display = (
        'name', 'league'
    )


class LeagueRelatedNameAdminInline(admin.TabularInline):
    model = LeagueRelatedName


class LeagueAdmin(admin.ModelAdmin):
    ordering = ('name',)
    inlines = (LeagueRelatedNameAdminInline, )


class LeagueRelatedNameAdmin(admin.ModelAdmin):
    pass


admin.site.register(Match, MatchAdmin)
admin.site.register(Team, TeamAdmin)
admin.site.register(League, LeagueAdmin)
admin.site.register(LeagueRelatedName, LeagueRelatedNameAdmin)
