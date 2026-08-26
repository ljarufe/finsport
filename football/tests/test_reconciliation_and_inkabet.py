from datetime import timedelta
from decimal import Decimal
from unittest import mock

import pytest
from django_countries.fields import Country

from football.country_mapping import country_code
from football.inkabet import (
    parse_categories,
    parse_mw3w,
    reconcile_categories,
    sync_mw3w_payload,
)
from football.models import (
    Competition,
    CompetitionSourceRef,
    Match,
    MatchSourceRef,
    OddsSnapshot,
    ReconciliationStatus,
    Team,
    TeamSourceRef,
)
from football.reconciliation import (
    reconcile_competition_ref,
    reconcile_match_ref,
    reconcile_team_ref,
)
from football.sync import sync_fixture_payloads

from .helpers import (
    catalog_season,
    competition,
    fixture_payload,
    inkabet_categories_payload,
    inkabet_mw3w_payload,
    inkabet_source,
)

pytestmark = pytest.mark.django_db


def test_competition_normalization_removes_country_prefix_deterministically():
    tracked = Competition.objects.create(
        name="La Liga", competition_type="League", country="ES"
    )
    ref = reconcile_competition_ref(
        source=inkabet_source(),
        external_id="12",
        external_name="España La Liga",
        country=Country("ES"),
    )
    assert ref.competition == tracked
    assert ref.reconciliation_status == ReconciliationStatus.RESOLVED
    assert ref.confidence == Decimal("1.0000")


def test_argentina_country_prefix_maps_to_canonical_liga_profesional():
    tracked = Competition.objects.create(
        name="Liga Profesional", competition_type="League", country="AR"
    )
    ref = reconcile_competition_ref(
        source=inkabet_source(),
        external_id="22681",
        external_name="Argentina Liga Profesional",
        country=Country("AR"),
    )
    assert ref.competition == tracked
    assert ref.reconciliation_status == ReconciliationStatus.RESOLVED


def test_competition_trigram_ranking_is_country_scoped():
    germany = Competition.objects.create(
        name="Bundesliga", competition_type="League", country="DE"
    )
    Competition.objects.create(
        name="Bundesliga", competition_type="League", country="AT"
    )
    ref = reconcile_competition_ref(
        source=inkabet_source(),
        external_id="15",
        external_name="Alemania Bundes Liga",
        country=Country("DE"),
    )
    assert ref.competition == germany
    assert ref.reconciliation_status == ReconciliationStatus.RESOLVED


def test_ambiguous_competition_stays_pending_without_canonical_duplicate():
    Competition.objects.create(
        name="Liga Profesional A", competition_type="League", country="AR"
    )
    Competition.objects.create(
        name="Liga Profesional B", competition_type="League", country="AR"
    )
    ref = reconcile_competition_ref(
        source=inkabet_source(),
        external_id="22681",
        external_name="Argentina Liga Profesional",
        country=Country("AR"),
    )
    assert ref.reconciliation_status == ReconciliationStatus.PENDING
    assert ref.competition is None
    assert ref.proposed_competition is not None
    assert Competition.objects.count() == 2


@pytest.mark.parametrize(
    ("external_name", "canonical_name"),
    [
        ("Melgar", "FBC Melgar"),
        ("Celta Vigo", "RC Celta de Vigo"),
        ("Bayern de Múnich", "Bayern Munich"),
    ],
)
def test_team_reconciliation_is_scoped_to_one_competition(
    external_name, canonical_name
):
    tracked = competition()
    expected = Team.objects.create(competition=tracked, name=canonical_name)
    Team.objects.create(
        competition=competition(external_id=40, name="Other League", country="ES"),
        name=external_name,
    )
    ref = reconcile_team_ref(
        source=inkabet_source(),
        external_id=f"provider-{canonical_name}",
        external_name=external_name,
        competition=tracked,
    )
    assert ref.team == expected
    assert ref.reconciliation_status == ReconciliationStatus.RESOLVED


def test_resolved_reference_bypasses_fuzzy_matching_on_later_ingestion():
    tracked = competition()
    existing = CompetitionSourceRef.objects.create(
        source=inkabet_source(),
        competition=tracked,
        external_id="3",
        external_name="Old label",
        reconciliation_status=ReconciliationStatus.RESOLVED,
    )
    with mock.patch(
        "football.reconciliation._rank_with_trigram",
        side_effect=AssertionError("fuzzy matching must not run"),
    ):
        ref = reconcile_competition_ref(
            source=inkabet_source(),
            external_id="3",
            external_name="Changed provider label",
            country=Country("EN"),
        )
    assert ref.pk == existing.pk
    assert ref.competition == tracked
    assert ref.external_name == "Changed provider label"


def test_match_reconciliation_uses_teams_and_small_kickoff_tolerance_then_persists():
    tracked = competition()
    catalog_season(tracked)
    _, accepted = sync_fixture_payloads([fixture_payload()], {"39": tracked})
    match = accepted["1001"]
    ref = reconcile_match_ref(
        source=inkabet_source(),
        external_id="f-current-match",
        external_label="Home - Away",
        competition=tracked,
        kickoff=match.kickoff + timedelta(minutes=5),
        home_name="Home",
        away_name="Away",
    )
    assert ref.match == match
    assert ref.reconciliation_status == ReconciliationStatus.RESOLVED
    repeated = reconcile_match_ref(
        source=inkabet_source(),
        external_id="f-current-match",
        external_label="Provider label changed",
        competition=tracked,
        kickoff=match.kickoff + timedelta(days=10),
        home_name="Unknown",
        away_name="Unknown",
    )
    assert repeated.match == match


def test_categories_parser_discovers_region_competition_match_and_ignores_outright():
    payload = inkabet_categories_payload()
    index = payload["data"]["items"]["indexBySlug"]
    index["futbol/england/england-premier-league/season-winner"] = [
        "1",
        "11",
        "3",
        "f-outright",
    ]
    payload["data"]["items"]["byId"]["f-outright"] = {
        "id": "f-outright",
        "label": "Premier League Season Winner",
        "eventType": "Outright",
    }
    competitions, events = parse_categories(payload)
    assert competitions[0].region_id == "11"
    assert competitions[0].external_id == "3"
    assert [event.external_id for event in events] == ["f-current-match"]
    assert events[0].home_name == "Home"
    assert events[0].away_name == "Away"


def test_categories_parser_accepts_real_keyed_event_shape_and_spanish_slug():
    payload = inkabet_categories_payload(
        country_slug="espana",
        competition_slug="espana-la-liga",
        event_id="f-real-shape",
        event_slug="real-madrid-real-sociedad",
        event_label="Real Madrid - Real Sociedad",
        kickoff="2026-08-26T19:00:00Z",
    )
    metadata = payload["data"]["items"]["byId"]["f-real-shape"]
    metadata.pop("id")
    metadata.pop("homeTeam")
    metadata.pop("awayTeam")
    metadata["participants"] = [
        {"side": 1, "name": "Real Madrid"},
        {"side": 2, "name": "Real Sociedad"},
    ]

    competitions, events = parse_categories(payload)

    assert competitions[0].country_slug == "espana"
    assert country_code(competitions[0].country_slug) == "ES"
    assert events[0].external_id == "f-real-shape"
    assert events[0].kickoff.tzinfo is not None
    assert events[0].home_name == "Real Madrid"
    assert events[0].away_name == "Real Sociedad"


def test_mw3w_parser_uses_only_strict_home_draw_away_templates():
    parsed = parse_mw3w(inkabet_mw3w_payload())
    assert parsed["prices"] == (
        Decimal("1.80"),
        Decimal("3.40"),
        Decimal("4.20"),
    )
    payload = inkabet_mw3w_payload()
    payload["data"]["accordions"]["MW3W"]["selections"][0][
        "selectionTemplateId"
    ] = "HOME_HANDICAP"
    assert parse_mw3w(payload) is None


def test_inkabet_pending_discovery_never_creates_canonical_entities():
    tracked = competition()
    catalog_season(tracked)
    _, accepted = sync_fixture_payloads([fixture_payload()], {"39": tracked})
    payload = inkabet_categories_payload(
        competition_slug="england-unmapped-league",
        event_label="Unknown A - Unknown B",
    )
    before = (Competition.objects.count(), Team.objects.count(), Match.objects.count())
    stats = reconcile_categories(payload, accepted.values())
    after = (Competition.objects.count(), Team.objects.count(), Match.objects.count())
    assert stats.pending_competitions == 1
    assert before == after
    assert (
        CompetitionSourceRef.objects.filter(
            source=inkabet_source(),
            reconciliation_status=ReconciliationStatus.PENDING,
        ).count()
        == 1
    )


def test_daily_reconciliation_ignores_future_events_outside_accepted_match_set():
    tracked = competition(name="La Liga", country="ES")
    catalog_season(tracked)
    _, accepted = sync_fixture_payloads(
        [
            fixture_payload(
                kickoff="2026-08-26T19:00:00+00:00",
                home_name="Real Madrid",
                away_name="Real Sociedad",
            )
        ],
        {"39": tracked},
    )
    relevant_match = accepted["1001"]
    Match.objects.create(
        season=relevant_match.season,
        home_team=relevant_match.home_team,
        away_team=relevant_match.away_team,
        kickoff=relevant_match.kickoff + timedelta(minutes=10),
        kickoff_timezone="UTC",
        status_short="NS",
        status_long="Not Started",
    )
    payload = inkabet_categories_payload(
        country_slug="espana",
        competition_slug="espana-la-liga",
        event_id="f-relevant",
        event_slug="real-madrid-real-sociedad",
        event_label="Real Madrid - Real Sociedad",
        kickoff="2026-08-26T19:00:00Z",
    )
    items = payload["data"]["items"]
    items["byId"]["f-relevant"]["homeTeam"] = {"name": "Real Madrid"}
    items["byId"]["f-relevant"]["awayTeam"] = {"name": "Real Sociedad"}
    for suffix, kickoff in (
        ("future-one", "2026-09-12T19:00:00Z"),
        ("future-two", "2026-09-19T19:00:00Z"),
    ):
        external_id = f"f-unrelated-{suffix}"
        items["indexBySlug"][f"futbol/espana/espana-la-liga/unrelated-{suffix}"] = [
            "1",
            "11",
            "3",
            external_id,
        ]
        items["byId"][external_id] = {
            "label": "Future Home - Future Away",
            "startDate": kickoff,
            "eventType": "Match",
            "participants": [
                {"side": 1, "name": "Future Home"},
                {"side": 2, "name": "Future Away"},
            ],
        }

    stats = reconcile_categories(payload, accepted.values())

    assert stats.pending_matches == 0
    ref = MatchSourceRef.objects.get(source=inkabet_source())
    assert ref.external_id == "f-relevant"
    assert ref.match == relevant_match


def test_daily_reconciliation_keeps_relevant_unresolvable_event_pending():
    tracked = competition(name="La Liga", country="ES")
    catalog_season(tracked)
    _, accepted = sync_fixture_payloads(
        [
            fixture_payload(
                kickoff="2026-08-26T19:00:00+00:00",
                home_name="Real Madrid",
                away_name="Real Sociedad",
            )
        ],
        {"39": tracked},
    )
    payload = inkabet_categories_payload(
        country_slug="espana",
        competition_slug="espana-la-liga",
        event_id="f-relevant-unknown-teams",
        event_label="Unknown Home - Unknown Away",
        kickoff="2026-08-26T19:00:00Z",
    )
    metadata = payload["data"]["items"]["byId"]["f-relevant-unknown-teams"]
    metadata["homeTeam"] = {"name": "Unknown Home"}
    metadata["awayTeam"] = {"name": "Unknown Away"}

    stats = reconcile_categories(payload, accepted.values())

    ref = MatchSourceRef.objects.get(external_id="f-relevant-unknown-teams")
    assert stats.pending_matches == 1
    assert ref.reconciliation_status == ReconciliationStatus.PENDING
    assert ref.match is None


def test_inkabet_odds_update_single_current_row_and_do_not_change_result():
    tracked = competition()
    catalog_season(tracked)
    _, accepted = sync_fixture_payloads(
        [
            fixture_payload(
                status_short="FT",
                status_long="Match Finished",
                home_score=2,
                away_score=1,
                home_winner=True,
                away_winner=False,
            )
        ],
        {"39": tracked},
    )
    match = accepted["1001"]
    match_ref = MatchSourceRef.objects.create(
        source=inkabet_source(),
        match=match,
        external_id="f-current-match",
        external_label="Home - Away",
        reconciliation_status=ReconciliationStatus.RESOLVED,
    )
    first = sync_mw3w_payload(inkabet_mw3w_payload(), match_ref)
    second = sync_mw3w_payload(
        inkabet_mw3w_payload(home="1.95", draw="3.30", away="4.00"),
        match_ref,
    )
    match.refresh_from_db()
    snapshot = OddsSnapshot.objects.get(source=inkabet_source())
    assert first.created == 3
    assert second.updated == 1
    assert second.unchanged == 2
    assert OddsSnapshot.objects.filter(source=inkabet_source()).count() == 1
    assert snapshot.home == Decimal("1.9500")
    assert match.home_score == 2
    assert match.outcome == Match.OUTCOME_HOME
    assert TeamSourceRef.objects.filter(source=inkabet_source()).count() == 2


@pytest.mark.parametrize(
    "items",
    [
        [],
        {"indexBySlug": []},
    ],
)
def test_categories_parser_rejects_invalid_nested_shapes(items):
    payload = {
        "data": {
            "items": items,
        }
    }

    with pytest.raises(TypeError):
        parse_categories(payload)
