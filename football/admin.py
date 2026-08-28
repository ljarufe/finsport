from django.contrib import admin

from .models import (
    Bookmaker,
    CapitalExperiment,
    CapitalLedgerEntry,
    CapitalPolicyRun,
    CaptureRun,
    CaptureWorkItem,
    Competition,
    CompetitionSourceRef,
    Decision,
    Match,
    MatchSourceRef,
    OddsMarket,
    OddsObservation,
    OddsSnapshot,
    Prediction,
    PredictionExperiment,
    Season,
    Source,
    Team,
    TeamSourceRef,
)


class ReadOnlyCapitalAuditMixin:
    def get_readonly_fields(self, request, obj=None):
        del request, obj
        return tuple(field.name for field in self.model._meta.concrete_fields)

    def has_add_permission(self, request, obj=None):
        del request, obj
        return False

    def has_change_permission(self, request, obj=None):
        del request, obj
        return False

    def has_delete_permission(self, request, obj=None):
        del request, obj
        return False


class CapitalPolicyRunInline(ReadOnlyCapitalAuditMixin, admin.TabularInline):
    model = CapitalPolicyRun
    extra = 0
    can_delete = False
    show_change_link = True


class CaptureWorkItemInline(ReadOnlyCapitalAuditMixin, admin.TabularInline):
    model = CaptureWorkItem
    extra = 0
    can_delete = False
    show_change_link = True


@admin.register(CaptureRun)
class CaptureRunAdmin(ReadOnlyCapitalAuditMixin, admin.ModelAdmin):
    list_display = (
        "id",
        "trigger",
        "status",
        "planning_at",
        "started_at",
        "completed_at",
        "provider_attempts",
        "provider_pages",
        "quota_remaining_before",
        "quota_remaining_after",
        "observations_created",
        "matches_resolved",
        "skips",
        "failures",
    )
    list_filter = ("trigger", "status", "quota_basis")
    date_hierarchy = "started_at"
    inlines = (CaptureWorkItemInline,)


@admin.register(CaptureWorkItem)
class CaptureWorkItemAdmin(ReadOnlyCapitalAuditMixin, admin.ModelAdmin):
    list_display = (
        "id",
        "run",
        "purpose",
        "status",
        "match",
        "intended_window",
        "target_at",
        "executed_at",
        "actual_attempts",
        "observations_created",
        "matches_resolved",
        "reason",
    )
    list_filter = (
        "purpose",
        "status",
        "source",
        "intended_window",
        "match__season__competition",
    )
    search_fields = (
        "logical_identity",
        "match__home_team__name",
        "match__away_team__name",
        "error_class",
        "error_message",
    )
    raw_id_fields = ("run", "match", "market")
    date_hierarchy = "target_at"


@admin.register(CapitalExperiment)
class CapitalExperimentAdmin(ReadOnlyCapitalAuditMixin, admin.ModelAdmin):
    list_display = (
        "id",
        "source_experiment",
        "source_identity",
        "decision_policy_code",
        "decision_policy_variant",
        "mode",
        "engine_version",
        "input_count",
        "completed_at",
    )
    list_filter = ("mode", "engine_version", "decision_policy_code")
    raw_id_fields = ("source_experiment",)
    inlines = (CapitalPolicyRunInline,)

    @admin.display(description="Source")
    def source_identity(self, obj):
        if obj.source_model_code:
            return f"{obj.source_model_code}:{obj.source_model_variant}"
        return f"comparator:{obj.source_comparator_code}"


@admin.register(CapitalPolicyRun)
class CapitalPolicyRunAdmin(ReadOnlyCapitalAuditMixin, admin.ModelAdmin):
    list_display = (
        "id",
        "experiment",
        "policy_code",
        "policy_version",
        "status",
        "reason",
        "seed",
        "path_count",
    )
    list_filter = ("status", "policy_code", "policy_version", "experiment__mode")
    raw_id_fields = ("experiment",)


@admin.register(CapitalLedgerEntry)
class CapitalLedgerEntryAdmin(ReadOnlyCapitalAuditMixin, admin.ModelAdmin):
    list_display = (
        "id",
        "policy_run",
        "source_decision",
        "batch_time",
        "batch_index",
        "step",
        "requested_stake",
        "applied_stake",
        "bankroll_before",
        "bankroll_after",
        "profit_loss",
        "cap_hit",
        "practical_ruin",
        "termination_reason",
    )
    list_filter = (
        "policy_run__policy_code",
        "policy_run__experiment__mode",
        "cap_hit",
        "practical_ruin",
        "termination_reason",
    )
    raw_id_fields = ("policy_run", "source_decision")
    date_hierarchy = "batch_time"


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


@admin.register(OddsObservation)
class OddsObservationAdmin(admin.ModelAdmin):
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
    date_hierarchy = "observed_at"


@admin.register(PredictionExperiment)
class PredictionExperimentAdmin(admin.ModelAdmin):
    list_display = (
        "id",
        "competition",
        "mode",
        "period_start",
        "period_end",
        "engine_version",
        "completed_at",
    )
    list_filter = ("mode", "competition", "engine_version")
    search_fields = ("competition__name", "engine_version")
    raw_id_fields = ("competition",)
    readonly_fields = ("config", "summary")


@admin.register(Prediction)
class PredictionAdmin(admin.ModelAdmin):
    list_display = (
        "match",
        "experiment",
        "model_code",
        "variant",
        "model_version",
        "cutoff",
        "p_home",
        "p_draw",
        "p_away",
        "predicted_outcome",
        "actual_outcome",
    )
    list_filter = (
        ("experiment", admin.RelatedOnlyFieldListFilter),
        "model_code",
        "variant",
        "predicted_outcome",
        "actual_outcome",
        "experiment__mode",
        "match__season__competition",
    )
    search_fields = (
        "match__home_team__name",
        "match__away_team__name",
        "model_version",
    )
    raw_id_fields = ("experiment", "match")
    date_hierarchy = "cutoff"


@admin.register(Decision)
class DecisionAdmin(admin.ModelAdmin):
    list_display = (
        "match",
        "experiment",
        "policy_code",
        "policy_variant",
        "action",
        "reason",
        "selected_price",
        "decision_time",
    )
    list_filter = (
        ("experiment", admin.RelatedOnlyFieldListFilter),
        "policy_code",
        "policy_variant",
        "action",
        "reason",
        "experiment__mode",
        "match__season__competition",
    )
    search_fields = (
        "match__home_team__name",
        "match__away_team__name",
        "policy_version",
        "reason",
    )
    raw_id_fields = (
        "experiment",
        "match",
        "prediction",
        "selected_odds_observation",
    )
    date_hierarchy = "decision_time"
