from django.contrib import admin

from .models import (
    Bookmaker,
    Competition,
    CompetitionSourceRef,
    Match,
    MatchSourceRef,
    OddsMarket,
    OddsSnapshot,
    Season,
    Source,
    Team,
    TeamSourceRef,
)


@admin.register(Source)
class SourceAdmin(admin.ModelAdmin):
    list_display = ("code", "name", "base_url")
    search_fields = ("code", "name")


@admin.register(Competition)
class CompetitionAdmin(admin.ModelAdmin):
    list_display = ("name", "country", "competition_type", "enabled")
    list_filter = ("enabled", "competition_type", "country")
    search_fields = ("name",)
    list_editable = ("enabled",)


@admin.register(CompetitionSourceRef)
class CompetitionSourceRefAdmin(admin.ModelAdmin):
    list_display = (
        "source",
        "external_id",
        "external_name",
        "external_country",
        "reconciliation_status",
        "confidence",
        "competition",
        "proposed_competition",
    )
    list_filter = ("source", "reconciliation_status")
    search_fields = ("external_id", "external_name", "external_slug")
    raw_id_fields = ("competition", "proposed_competition")

    @admin.display(description="Provider country")
    def external_country(self, obj):
        return (
            obj.context.get("country_slug")
            or obj.context.get("country_name")
            or obj.context.get("country_code")
            or ""
        )


@admin.register(Season)
class SeasonAdmin(admin.ModelAdmin):
    list_display = (
        "competition",
        "year",
        "start_date",
        "end_date",
        "is_current",
    )
    list_filter = ("is_current", "year", "competition")
    search_fields = ("competition__name",)


@admin.register(Team)
class TeamAdmin(admin.ModelAdmin):
    list_display = ("name", "competition", "is_active")
    list_filter = ("is_active", "competition", "competition__country")
    search_fields = ("name", "code", "competition__name")
    raw_id_fields = ("competition",)


@admin.register(TeamSourceRef)
class TeamSourceRefAdmin(admin.ModelAdmin):
    list_display = (
        "source",
        "external_id",
        "external_name",
        "competition",
        "reconciliation_status",
        "confidence",
        "team",
        "proposed_team",
    )
    list_filter = ("source", "reconciliation_status", "competition")
    search_fields = (
        "external_id",
        "external_name",
        "competition__name",
        "team__name",
    )
    raw_id_fields = ("competition", "team", "proposed_team")


@admin.register(Match)
class MatchAdmin(admin.ModelAdmin):
    list_display = (
        "id",
        "home_team",
        "away_team",
        "kickoff",
        "status_short",
        "outcome",
    )
    list_filter = (
        "status_short",
        "outcome",
        "kickoff",
        "season__year",
        "season__competition",
    )
    search_fields = (
        "home_team__name",
        "away_team__name",
        "season__competition__name",
        "source_refs__external_id",
    )
    raw_id_fields = ("season", "home_team", "away_team")
    date_hierarchy = "kickoff"


@admin.register(MatchSourceRef)
class MatchSourceRefAdmin(admin.ModelAdmin):
    list_display = (
        "source",
        "external_id",
        "external_label",
        "reconciliation_status",
        "confidence",
        "match",
        "proposed_match",
    )
    list_filter = ("source", "reconciliation_status")
    search_fields = (
        "external_id",
        "external_label",
        "match__home_team__name",
        "match__away_team__name",
    )
    raw_id_fields = ("match", "proposed_match")


@admin.register(Bookmaker)
class BookmakerAdmin(admin.ModelAdmin):
    list_display = ("name", "external_id", "source")
    list_filter = ("source",)
    search_fields = ("name", "external_id")


@admin.register(OddsMarket)
class OddsMarketAdmin(admin.ModelAdmin):
    list_display = ("name", "external_id", "source")
    list_filter = ("source",)
    search_fields = ("name", "external_id")


@admin.register(OddsSnapshot)
class OddsSnapshotAdmin(admin.ModelAdmin):
    list_display = (
        "match",
        "source",
        "bookmaker",
        "market",
        "home",
        "draw",
        "away",
        "provider_updated_at",
        "observed_at",
    )
    list_filter = (
        "source",
        "bookmaker",
        "market",
        "match__season__competition",
    )
    search_fields = (
        "match__source_refs__external_id",
        "match__home_team__name",
        "match__away_team__name",
        "bookmaker__name",
    )
    raw_id_fields = ("match", "bookmaker", "market")
