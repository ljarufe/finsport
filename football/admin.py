from django.contrib import admin, messages
from django.shortcuts import redirect
from django.urls import path

from common.scrapy_runner import run_scrapy_spider

from .forms import LeagueForm
from .models import League, LeagueRelatedName, Match, Team


@admin.register(Match)
class MatchAdmin(admin.ModelAdmin):
    list_display = (
        "get_match_name",
        "state",
        "start_datetime",
        "score",
        "local_factor",
        "draw_factor",
        "visitor_factor",
    )
    list_filter = (
        "state",
        "start_datetime",
    )
    search_fields = (
        "local_team__name",
        "visitor_team__name",
    )
    raw_id_fields = (
        "local_team",
        "visitor_team",
    )


@admin.register(Team)
class TeamAdmin(admin.ModelAdmin):
    list_display = (
        "name",
        "league",
    )
    search_fields = ("name", "league__name")
    list_filter = ("league",)


class LeagueRelatedNameAdminInline(admin.TabularInline):
    model = LeagueRelatedName
    extra = 1


@admin.register(League)
class LeagueAdmin(admin.ModelAdmin):
    list_display = ("name", "country", "draw_percentage")
    list_filter = ("country",)
    ordering = ("-draw_percentage",)
    search_fields = ("name",)
    form = LeagueForm
    inlines = (LeagueRelatedNameAdminInline,)

    def get_urls(self):
        urls = super().get_urls()
        custom_urls = [
            path(
                "get-leagues/",
                self.admin_site.admin_view(self.get_leagues),
                name="get_leagues",
            ),
        ]
        return custom_urls + urls

    def get_leagues(self, request):
        message = run_scrapy_spider("leagues")
        if message["success"]:
            self.message_user(
                request, "Successful command get leagues", messages.SUCCESS
            )
        else:
            self.message_user(
                request,
                f"Error command get leagues: {message['stderr']}",
                messages.ERROR,
            )

        return redirect("admin:football_league_changelist")
