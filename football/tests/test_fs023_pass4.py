"""Pass 4 regressions for BSD exact identity and terminal physical-call audits."""

from types import SimpleNamespace

import pytest
import requests

from football.models import (
    BSDEventBinding,
    BSDTeamMapping,
    CompetitionResultRoute,
    ProviderCallAudit,
)
from football.providers.bsd import BSDClient, BSDError
from football.providers.bsd_identity import (
    bind_event,
    exact_unique_team_pairs,
    normalized_name,
)
from football.tests.test_fs023_contracts import NOW, _match


def test_u11_punctuation_is_a_word_boundary_and_diacritics_remain_equal():
    assert normalized_name("St. Louis City") == normalized_name("St.Louis City")
    assert normalized_name("St. Louis City") == "st louis city"
    assert normalized_name("Internacional de Bogota") == normalized_name(
        "Internacional de Bogotá"
    )
    assert normalized_name("ST. LOUIS CITY") == "st louis city"
    assert normalized_name("StLouis City") != normalized_name("St. Louis City")


def test_u11_normalization_collisions_do_not_auto_approve():
    local = [SimpleNamespace(name="St. Louis City")]
    provider = [
        {"id": 1, "name": "St.Louis City"},
        {"id": 2, "name": "St. Louis City"},
    ]
    assert exact_unique_team_pairs(local, provider) == []
    local.append(SimpleNamespace(name="St.Louis City"))
    assert exact_unique_team_pairs(local, provider[:1]) == []


@pytest.mark.django_db
def test_u11_fixture_1490500_identity_shape_binds_event_605013_once():
    match = _match()
    match.home_team.name = "New York Red Bulls"
    match.home_team.save(update_fields=["name"])
    match.away_team.name = "St. Louis City"
    match.away_team.save(update_fields=["name"])
    route = CompetitionResultRoute.objects.create(
        competition=match.season.competition,
        api_football_league_id=253,
        bsd_league_ids=[18],
    )
    pairs = exact_unique_team_pairs(
        [match.home_team, match.away_team],
        [
            {"id": 281, "name": "New York Red Bulls"},
            {"id": 9001, "name": "St.Louis City"},
        ],
    )
    assert len(pairs) == 2
    for team, provider in pairs:
        BSDTeamMapping.objects.create(
            route=route,
            canonical_team=team,
            bsd_team_id=provider["id"],
            bsd_league_id=18,
            approval="EXACT_UNIQUE",
        )
    event = {
        "id": 605013,
        "league_id": 18,
        "home_team_id": 281,
        "away_team_id": 9001,
        "event_date": NOW.isoformat(),
    }
    assert bind_event(match, route, [event]) == "BOUND"
    assert bind_event(match, route, [event]) == "BOUND"
    assert list(
        BSDEventBinding.objects.filter(match=match).values_list(
            "bsd_event_id", flat=True
        )
    ) == [605013]
    assert (
        bind_event(match, route, [event, dict(event, id=605014)])
        == "BSD_IDENTITY_AMBIGUOUS"
    )


@pytest.mark.django_db
def test_u10_u29_two_network_failures_finish_both_audits():
    class FailingSession:
        calls = 0

        def get(self, *args, **kwargs):
            self.calls += 1
            raise requests.ConnectionError("synthetic-network-failure")

    session = FailingSession()
    slept = []
    client = BSDClient(token="test-only-token", session=session, sleep=slept.append)
    with pytest.raises(BSDError) as raised:
        client.get("events/605013/", logical_identity="test:pass4:network")
    assert raised.value.state == "RESULT_PROVIDER_ERROR"
    assert session.calls == 2
    assert slept == [2]
    audits = list(
        ProviderCallAudit.objects.filter(logical_identity="test:pass4:network")
        .order_by("attempt_number")
        .values("attempt_number", "outcome", "completed_at", "request_metadata")
    )
    assert [(row["attempt_number"], row["outcome"]) for row in audits] == [
        (1, "RESULT_PROVIDER_ERROR"),
        (2, "RESULT_PROVIDER_ERROR"),
    ]
    assert all(row["completed_at"] is not None for row in audits)
    assert all("test-only-token" not in str(row["request_metadata"]) for row in audits)
