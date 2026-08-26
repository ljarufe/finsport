from dataclasses import dataclass
from decimal import Decimal, InvalidOperation

from django.db import transaction
from django.utils import timezone
from django.utils.dateparse import parse_datetime
from django_countries.fields import Country

from .api_inkabet import InkabetResponseError
from .country_mapping import country_code, normalized_text
from .models import (
    Bookmaker,
    MatchSourceRef,
    OddsMarket,
    ReconciliationStatus,
)
from .reconciliation import (
    MATCH_KICKOFF_TOLERANCE,
    reconcile_competition_ref,
    reconcile_match_ref,
    reconcile_team_ref,
)
from .sync import SyncStats, _upsert, get_inkabet_source, upsert_current_odds

MW3W = "MW3W"
OUTRIGHT_MARKERS = {
    "outright",
    "season winner",
    "winner",
    "campeon",
    "campeón",
    "ganador de la liga",
}


@dataclass(frozen=True)
class InkabetCompetition:
    external_id: str
    external_name: str
    external_slug: str
    country_slug: str
    region_id: str


@dataclass(frozen=True)
class InkabetEvent:
    external_id: str
    external_label: str
    external_slug: str
    competition_external_id: str
    kickoff: object
    home_name: str
    away_name: str


def _metadata_by_id(payload):
    result = {}

    def remember(identifier, metadata):
        if identifier is None or not isinstance(metadata, dict):
            return

        identifier = str(identifier)

        existing = result.setdefault(identifier, {})

        for key, value in metadata.items():
            if value not in (None, "", [], {}):
                existing[key] = value

    def walk(value):
        if isinstance(value, dict):
            identifier = value.get("eventId") or value.get("itemId") or value.get("id")
            remember(identifier, value)

            for key, nested in value.items():
                if isinstance(nested, dict) and str(key).startswith("f-"):
                    remember(key, nested)

                walk(nested)

        elif isinstance(value, list):
            for nested in value:
                walk(nested)

    walk(payload)

    return result


def _label(metadata, fallback):
    return str(
        metadata.get("label")
        or metadata.get("eventName")
        or metadata.get("name")
        or fallback
    ).strip()


def _team_name(metadata, side):
    value = metadata.get(f"{side}Team") or metadata.get(side)

    if isinstance(value, dict):
        return str(value.get("label") or value.get("name") or "").strip()

    if value:
        return str(value).strip()

    expected_roles = {"home", "1"} if side == "home" else {"away", "2"}

    for participant in metadata.get("participants") or []:
        role = str(
            participant.get("type")
            or participant.get("side")
            or participant.get("position")
            or ""
        ).casefold()

        if role in expected_roles:
            return str(
                participant.get("label") or participant.get("name") or ""
            ).strip()

    return ""


def _split_event_label(label):
    for separator in (" - ", " vs ", " v "):
        if separator in label:
            return tuple(part.strip() for part in label.split(separator, 1))
    return "", ""


def _is_real_match(event_id, label, slug, metadata):
    if not str(event_id).startswith("f-"):
        return False
    event_type = normalized_text(
        metadata.get("eventType") or metadata.get("type") or ""
    )
    searchable = normalized_text(f"{label} {slug} {event_type}")
    return not any(normalized_text(marker) in searchable for marker in OUTRIGHT_MARKERS)


def parse_categories(payload):
    data = payload.get("data") or {}
    items = data.get("items", {})

    if not isinstance(items, dict):
        raise TypeError("Inkabet categories items must be an object.")

    index_by_slug = items.get("indexBySlug", {})

    if not isinstance(index_by_slug, dict):
        raise TypeError("Inkabet categories indexBySlug must be an object.")

    metadata_by_id = _metadata_by_id(items)
    competitions = {}
    events = []
    for path, identifiers in index_by_slug.items():
        if not isinstance(identifiers, list):
            continue
        segments = str(path).strip("/").split("/")
        if len(segments) < 3 or segments[0] != "futbol":
            continue
        if len(identifiers) == 3:
            external_id = str(identifiers[2])
            competition_slug = segments[2]
            country_slug = segments[1]
            external_name = competition_slug.replace("-", " ")
            country_prefix = f"{country_slug} "
            if external_name.startswith(country_prefix):
                external_name = external_name[len(country_prefix) :]
            competitions[external_id] = InkabetCompetition(
                external_id=external_id,
                external_name=external_name,
                external_slug="/".join(segments[:3]),
                country_slug=country_slug,
                region_id=str(identifiers[1]),
            )
        elif len(identifiers) == 4 and len(segments) >= 4:
            external_id = str(identifiers[3])
            metadata = metadata_by_id.get(external_id, {})
            fallback = segments[-1].replace("-", " ")
            label = _label(metadata, fallback)
            if not _is_real_match(external_id, label, segments[-1], metadata):
                continue
            home_name = _team_name(metadata, "home")
            away_name = _team_name(metadata, "away")
            if not home_name or not away_name:
                home_name, away_name = _split_event_label(label)
            kickoff = parse_datetime(
                metadata.get("startDate")
                or metadata.get("startTime")
                or metadata.get("start_date")
                or ""
            )
            if kickoff and timezone.is_naive(kickoff):
                kickoff = timezone.make_aware(kickoff)
            events.append(
                InkabetEvent(
                    external_id=external_id,
                    external_label=label,
                    external_slug=path,
                    competition_external_id=str(identifiers[2]),
                    kickoff=kickoff,
                    home_name=home_name,
                    away_name=away_name,
                )
            )
    return list(competitions.values()), events


def parse_mw3w(payload):
    accordions = (payload.get("data") or {}).get("accordions") or {}
    accordion = accordions.get(MW3W) or {}
    markets = accordion.get("markets") or []
    if isinstance(markets, dict):
        markets = list(markets.values())
    if not any(
        market.get("marketTemplateId") == MW3W
        and str(market.get("status") or "").casefold() == "open"
        for market in markets
    ):
        return None
    selections = accordion.get("selections") or []
    if isinstance(selections, dict):
        selections = list(selections.values())
    by_template = {
        selection.get("selectionTemplateId"): selection for selection in selections
    }
    if not all(template in by_template for template in ("HOME", "DRAW", "AWAY")):
        return None
    try:
        prices = tuple(
            Decimal(str(by_template[template]["odds"]))
            for template in ("HOME", "DRAW", "AWAY")
        )
    except (InvalidOperation, KeyError, TypeError):
        return None
    return {
        "prices": prices,
        "home": by_template["HOME"],
        "away": by_template["AWAY"],
    }


def _matches_in_kickoff_window(event, matches):
    if not event.kickoff:
        return []
    return [
        match
        for match in matches
        if abs(match.kickoff - event.kickoff) <= MATCH_KICKOFF_TOLERANCE
    ]


@transaction.atomic
def reconcile_categories(payload, relevant_matches):
    source = get_inkabet_source()
    stats = SyncStats()
    try:
        competitions, events = parse_categories(payload)
    except (AttributeError, IndexError, KeyError, TypeError, ValueError) as error:
        raise InkabetResponseError(
            "Inkabet returned an unexpected categories payload shape."
        ) from error
    relevant_by_country = {}
    for match in relevant_matches:
        relevant_by_country.setdefault(match.competition.country.code, []).append(match)

    competitions_by_id = {item.external_id: item for item in competitions}
    candidates_by_event_id = {}
    for event in events:
        item = competitions_by_id.get(event.competition_external_id)
        code = country_code(item.country_slug) if item else ""
        candidates = _matches_in_kickoff_window(
            event,
            relevant_by_country.get(code, ()),
        )
        if candidates:
            candidates_by_event_id[event.external_id] = candidates

    relevant_competition_ids = {
        event.competition_external_id
        for event in events
        if event.external_id in candidates_by_event_id
    }
    processed_refs = {}
    for item in competitions:
        if item.external_id not in relevant_competition_ids:
            continue
        code = country_code(item.country_slug)
        if not code or code not in relevant_by_country:
            continue
        ref = reconcile_competition_ref(
            source=source,
            external_id=item.external_id,
            external_name=item.external_name,
            country=Country(code),
            external_slug=item.external_slug,
            context={
                "region_id": item.region_id,
                "country_slug": item.country_slug,
            },
        )
        processed_refs[item.external_id] = ref
        if ref.reconciliation_status == ReconciliationStatus.PENDING:
            stats.pending_competitions += 1

    for event in events:
        candidate_matches = candidates_by_event_id.get(event.external_id)
        if not candidate_matches:
            continue
        competition_ref = processed_refs.get(event.competition_external_id)
        if (
            not competition_ref
            or competition_ref.reconciliation_status != ReconciliationStatus.RESOLVED
            or not competition_ref.competition_id
            or not competition_ref.competition.enabled
        ):
            continue
        candidate_matches = [
            match
            for match in candidate_matches
            if match.season.competition_id == competition_ref.competition_id
        ]
        if not candidate_matches:
            continue
        ref = reconcile_match_ref(
            source=source,
            external_id=event.external_id,
            external_label=event.external_label,
            competition=competition_ref.competition,
            kickoff=event.kickoff,
            home_name=event.home_name,
            away_name=event.away_name,
            context={
                "slug": event.external_slug,
                "competition_external_id": event.competition_external_id,
            },
            candidate_matches=candidate_matches,
        )
        if ref.reconciliation_status == ReconciliationStatus.PENDING:
            stats.pending_matches += 1
    return stats


@transaction.atomic
def sync_mw3w_payload(payload, match_ref):
    parsed = parse_mw3w(payload)
    stats = SyncStats()
    if parsed is None or not match_ref.match_id:
        stats.skipped += 1
        return stats
    source = match_ref.source
    match = match_ref.match
    for side, canonical_team in (
        ("home", match.home_team),
        ("away", match.away_team),
    ):
        selection = parsed[side]
        participant_id = selection.get("participantId")
        participant_name = selection.get("participantLabel") or ""
        if participant_id is not None:
            ref = reconcile_team_ref(
                source=source,
                external_id=participant_id,
                external_name=participant_name,
                competition=match.competition,
                canonical_team=canonical_team,
            )
            if (
                ref.reconciliation_status == ReconciliationStatus.PENDING
                or ref.team_id != canonical_team.id
            ):
                stats.pending_teams += 1
                stats.skipped += 1
                return stats
    bookmaker, result = _upsert(
        Bookmaker,
        {"source": source, "external_id": "inkabet"},
        {"name": "Inkabet"},
    )
    stats.add(result)
    market, result = _upsert(
        OddsMarket,
        {"source": source, "external_id": MW3W},
        {"name": "Match Winner"},
    )
    stats.add(result)
    _, result = upsert_current_odds(
        match=match,
        source=source,
        bookmaker=bookmaker,
        market=market,
        prices=parsed["prices"],
        observed_at=timezone.now(),
    )
    stats.add(result)
    return stats


def resolved_match_refs_for(matches):
    return (
        MatchSourceRef.objects.filter(
            source__code="inkabet",
            reconciliation_status=ReconciliationStatus.RESOLVED,
            match__in=matches,
        )
        .select_related(
            "source", "match__home_team", "match__away_team", "match__season"
        )
        .order_by("external_id")
    )
