"""Shared provider prerequisites for executable API-Football odds capture."""

from football.models import CaptureWorkItem, OddsMarket, ReconciliationStatus
from football.sync import MATCH_WINNER_NAMES


def match_winner_market(source):
    return next(
        (
            market
            for market in OddsMarket.objects.filter(source=source)
            if market.name.strip().casefold() in MATCH_WINNER_NAMES
        ),
        None,
    )


def odds_capture_prerequisite(match, source, ref, market):
    """Return a planner-compatible ineligibility, or None when capture is viable."""

    if (match.season.coverage or {}).get("odds") is not True:
        return (
            CaptureWorkItem.Status.ODDS_NOT_COVERED,
            "season does not explicitly report odds coverage",
        )
    if (
        ref is None
        or ref.match_id != match.pk
        or ref.source_id != source.pk
        or ref.reconciliation_status != ReconciliationStatus.RESOLVED
        or market is None
        or market.source_id != source.pk
        or market.name.strip().casefold() not in MATCH_WINNER_NAMES
    ):
        return (
            CaptureWorkItem.Status.UNRESOLVED_IDENTITY,
            "resolved fixture identity and Match Winner market are required",
        )
    return None
