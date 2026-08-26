from datetime import timedelta
from decimal import Decimal

from django.contrib.postgres.search import TrigramSimilarity
from django.db import transaction
from django.utils import timezone

from .country_mapping import country_name_prefixes, normalized_text
from .models import (
    Competition,
    CompetitionSourceRef,
    Match,
    MatchSourceRef,
    ReconciliationStatus,
    Team,
    TeamSourceRef,
)

COMPETITION_AUTO_THRESHOLD = 0.55
COMPETITION_MARGIN = 0.15
TEAM_AUTO_THRESHOLD = 0.35
TEAM_MARGIN = 0.10
MATCH_KICKOFF_TOLERANCE = timedelta(minutes=30)
GENERIC_TEAM_TOKENS = {"home", "away", "team", "local", "visitor"}


def normalized_entity_name(value, country=None):
    normalized = normalized_text(value)
    for prefix in country_name_prefixes(country):
        if normalized == prefix:
            return ""
        if normalized.startswith(f"{prefix} "):
            return normalized[len(prefix) + 1 :]
    return normalized


def _token_confidence(left, right):
    left_tokens = set(left.split())
    right_tokens = set(right.split())
    if not left_tokens or not right_tokens:
        return 0.0
    if left_tokens == right_tokens:
        return 1.0
    overlap = len(left_tokens & right_tokens)
    if overlap == min(len(left_tokens), len(right_tokens)):
        return overlap / max(len(left_tokens), len(right_tokens))
    return 0.0


def _rank_with_trigram(queryset, value):
    return list(
        queryset.annotate(similarity=TrigramSimilarity("name", value)).order_by(
            "-similarity", "id"
        )[:2]
    )


def _safe_automatic_candidate(ranked, threshold, margin):
    if not ranked:
        return None, 0.0
    best = ranked[0]
    best_score = float(best.similarity or 0)
    second_score = float(ranked[1].similarity or 0) if len(ranked) > 1 else 0
    if best_score >= threshold and best_score - second_score >= margin:
        return best, best_score
    return None, best_score


def _save_ref(ref, values):
    changed = []
    for field, value in values.items():
        if getattr(ref, field) != value:
            setattr(ref, field, value)
            changed.append(field)
    ref.full_clean()
    if ref.pk:
        if changed:
            ref.save(update_fields=changed)
    else:
        ref.save()
    return ref


def _canonical_mapping_available(model, source, field, candidate, current_ref):
    if candidate is None:
        return False
    return not (
        model.objects.filter(source=source, **{field: candidate})
        .exclude(pk=current_ref.pk)
        .exists()
    )


@transaction.atomic
def reconcile_competition_ref(
    *,
    source,
    external_id,
    external_name,
    country,
    external_slug="",
    context=None,
):
    external_id = str(external_id)
    existing = (
        CompetitionSourceRef.objects.filter(source=source, external_id=external_id)
        .select_related("competition")
        .first()
    )
    now = timezone.now()
    if (
        existing
        and existing.reconciliation_status == ReconciliationStatus.RESOLVED
        and existing.competition_id
    ):
        return _save_ref(
            existing,
            {
                "external_name": external_name,
                "external_slug": external_slug,
                "context": context or {},
                "last_seen_at": now,
            },
        )

    ref = existing or CompetitionSourceRef(source=source, external_id=external_id)
    candidates = Competition.objects.filter(country=country)
    normalized_external = normalized_entity_name(external_name, country)
    deterministic = []
    for candidate in candidates:
        normalized_candidate = normalized_entity_name(candidate.name, country)
        confidence = _token_confidence(normalized_external, normalized_candidate)
        if normalized_external == normalized_candidate:
            confidence = 1.0
        if confidence >= 0.80:
            deterministic.append((candidate, confidence))
    if len(deterministic) == 1:
        candidate, confidence = deterministic[0]
        if not _canonical_mapping_available(
            CompetitionSourceRef, source, "competition", candidate, ref
        ):
            return _save_ref(
                ref,
                {
                    "competition": None,
                    "proposed_competition": candidate,
                    "external_name": external_name,
                    "external_slug": external_slug,
                    "context": context or {},
                    "reconciliation_status": ReconciliationStatus.PENDING,
                    "confidence": Decimal(str(round(confidence, 4))),
                    "last_seen_at": now,
                },
            )
        return _save_ref(
            ref,
            {
                "competition": candidate,
                "proposed_competition": None,
                "external_name": external_name,
                "external_slug": external_slug,
                "context": context or {},
                "reconciliation_status": ReconciliationStatus.RESOLVED,
                "confidence": Decimal(str(round(confidence, 4))),
                "last_seen_at": now,
            },
        )

    ranked = _rank_with_trigram(candidates, normalized_external)
    candidate, confidence = _safe_automatic_candidate(
        ranked, COMPETITION_AUTO_THRESHOLD, COMPETITION_MARGIN
    )
    if candidate and not _canonical_mapping_available(
        CompetitionSourceRef, source, "competition", candidate, ref
    ):
        candidate = None
    return _save_ref(
        ref,
        {
            "competition": candidate,
            "proposed_competition": candidate or (ranked[0] if ranked else None),
            "external_name": external_name,
            "external_slug": external_slug,
            "context": context or {},
            "reconciliation_status": (
                ReconciliationStatus.RESOLVED
                if candidate
                else ReconciliationStatus.PENDING
            ),
            "confidence": (Decimal(str(round(confidence, 4))) if ranked else None),
            "last_seen_at": now,
        },
    )


def find_team_candidate(competition, external_name):
    candidates = Team.objects.filter(competition=competition)
    normalized_external = normalized_entity_name(external_name)
    deterministic = []
    for candidate in candidates:
        normalized_candidate = normalized_entity_name(candidate.name)
        meaningful_overlap = (
            set(normalized_external.split())
            & set(normalized_candidate.split()) - GENERIC_TEAM_TOKENS
        )
        confidence = _token_confidence(normalized_external, normalized_candidate)
        if normalized_external == normalized_candidate:
            confidence = 1.0
        elif not meaningful_overlap:
            confidence = 0.0
        if confidence >= 0.50:
            deterministic.append((candidate, confidence))
    deterministic.sort(key=lambda item: item[1], reverse=True)
    if len(deterministic) == 1 or (
        len(deterministic) > 1
        and deterministic[0][1] - deterministic[1][1] >= TEAM_MARGIN
    ):
        return deterministic[0]
    ranked = _rank_with_trigram(candidates, normalized_external)
    candidate, confidence = _safe_automatic_candidate(
        ranked, TEAM_AUTO_THRESHOLD, TEAM_MARGIN
    )
    if candidate:
        meaningful_overlap = (
            set(normalized_external.split())
            & set(normalized_entity_name(candidate.name).split()) - GENERIC_TEAM_TOKENS
        )
        if not meaningful_overlap:
            return None, confidence
    return candidate, confidence


@transaction.atomic
def reconcile_team_ref(
    *, source, external_id, external_name, competition, canonical_team=None
):
    external_id = str(external_id)
    existing = (
        TeamSourceRef.objects.filter(source=source, external_id=external_id)
        .select_related("team")
        .first()
    )
    now = timezone.now()
    if (
        existing
        and existing.reconciliation_status == ReconciliationStatus.RESOLVED
        and existing.team_id
    ):
        return _save_ref(
            existing,
            {"external_name": external_name, "last_seen_at": now},
        )
    ref = existing or TeamSourceRef(
        source=source,
        external_id=external_id,
        competition=competition,
    )
    if ref.competition_id != competition.id:
        return _save_ref(
            ref,
            {
                "team": None,
                "proposed_team": None,
                "external_name": external_name,
                "reconciliation_status": ReconciliationStatus.PENDING,
                "confidence": None,
                "last_seen_at": now,
            },
        )
    if canonical_team is not None:
        candidate, confidence = canonical_team, 1.0
        proposed = None
    else:
        candidate, confidence = find_team_candidate(competition, external_name)
        ranked = (
            []
            if candidate
            else _rank_with_trigram(
                Team.objects.filter(competition=competition),
                normalized_entity_name(external_name),
            )
        )
        proposed = ranked[0] if ranked else None
    if candidate and not _canonical_mapping_available(
        TeamSourceRef, source, "team", candidate, ref
    ):
        proposed = candidate
        candidate = None
    return _save_ref(
        ref,
        {
            "team": candidate,
            "proposed_team": proposed,
            "external_name": external_name,
            "reconciliation_status": (
                ReconciliationStatus.RESOLVED
                if candidate
                else ReconciliationStatus.PENDING
            ),
            "confidence": (Decimal(str(round(confidence, 4))) if confidence else None),
            "last_seen_at": now,
        },
    )


@transaction.atomic
def reconcile_match_ref(
    *,
    source,
    external_id,
    external_label,
    competition,
    kickoff,
    home_name,
    away_name,
    context=None,
    candidate_matches=None,
):
    external_id = str(external_id)
    existing = (
        MatchSourceRef.objects.filter(source=source, external_id=external_id)
        .select_related("match")
        .first()
    )
    now = timezone.now()
    if (
        existing
        and existing.reconciliation_status == ReconciliationStatus.RESOLVED
        and existing.match_id
    ):
        return _save_ref(
            existing,
            {
                "external_label": external_label,
                "context": context or {},
                "last_seen_at": now,
            },
        )

    ref = existing or MatchSourceRef(source=source, external_id=external_id)
    home_team, _ = find_team_candidate(competition, home_name)
    away_team, _ = find_team_candidate(competition, away_name)
    matches = Match.objects.none()
    if kickoff and home_team and away_team:
        matches = Match.objects.filter(
            season__competition=competition,
            home_team=home_team,
            away_team=away_team,
            kickoff__gte=kickoff - MATCH_KICKOFF_TOLERANCE,
            kickoff__lte=kickoff + MATCH_KICKOFF_TOLERANCE,
        ).order_by("kickoff")
        if candidate_matches is not None:
            candidate_ids = [match.pk for match in candidate_matches]
            matches = matches.filter(pk__in=candidate_ids)
    candidates = list(matches[:2])
    candidate = candidates[0] if len(candidates) == 1 else None
    if candidate and not _canonical_mapping_available(
        MatchSourceRef, source, "match", candidate, ref
    ):
        candidate = None
    return _save_ref(
        ref,
        {
            "match": candidate,
            "proposed_match": candidates[0] if candidates else None,
            "external_label": external_label,
            "context": context or {},
            "reconciliation_status": (
                ReconciliationStatus.RESOLVED
                if candidate
                else ReconciliationStatus.PENDING
            ),
            "confidence": Decimal("1.0000") if candidate else None,
            "last_seen_at": now,
        },
    )
