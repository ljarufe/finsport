"""FS-023 review-2 regressions: fake provider traffic and deterministic time."""

from datetime import UTC, datetime, timedelta
from datetime import timezone as dt_timezone

import pytest
from django.test import override_settings

from football.models import (
    BSDEventBinding,
    CompetitionResultRoute,
    ResultProviderObservation,
)
from football.providers.bsd import BSDClient
from football.providers.bsd_bootstrap import bootstrap
from football.providers.bsd_continuity import run_bsd_continuity
from football.result_provider import Result, record, shadow_gate
from football.result_routing import recheck_pending_conflicts
from football.tests.test_fs023_contracts import NOW, _match
from football.tests.test_fs023_pass2 import BSDSession, Response, _bsd_graph

pytestmark = pytest.mark.django_db


def _client(session):
    return BSDClient(session=session, sleep=lambda _: None)


def test_feed_lag_convergence_is_audited_but_not_confirmed():
    match, route, event = _bsd_graph()
    BSDEventBinding.objects.create(match=match, bsd_league_id=1, bsd_event_id=1001)
    record(
        match,
        Result("API_FOOTBALL", "501", "FT", 2, 1, "HOME", NOW, {}),
        authoritative=True,
    )
    first, disposition = record(
        match,
        Result("BSD", "1001", "FT", 1, 2, "AWAY", NOW + timedelta(minutes=1), {}),
        authoritative=False,
    )
    assert disposition == "PENDING_CONFLICT"
    session = BSDSession(event)  # Later detail is FT 2-1, agreeing with API-F.
    with override_settings(BSD_API_TOKEN="fake-only"):
        calls, errors = recheck_pending_conflicts(
            at=NOW + timedelta(minutes=31), client_factory=lambda: _client(session)
        )
        repeated = recheck_pending_conflicts(
            at=NOW + timedelta(minutes=32), client_factory=lambda: _client(session)
        )
    first.refresh_from_db()
    route.refresh_from_db()
    match.refresh_from_db()
    latest = ResultProviderObservation.objects.filter(
        match=match, provider="BSD"
    ).latest("provider_observed_at")
    assert calls == 1 and errors == []
    assert repeated == (0, [])
    assert first.provenance["conflict_resolution"] == "FEED_LAG_CONVERGED"
    assert first.provenance["pending_conflict"] is False
    assert (first.home_regulation, first.away_regulation) == (1, 2)
    assert latest.provenance["same_provider_revision"] is True
    assert latest.provenance["conflict_resolution"] == "FEED_LAG_CONVERGED"
    assert latest.conflict is False and latest.authoritative is False
    assert shadow_gate()["confirmed_conflicts"] == 0
    assert route.bsd_state == "BSD_SHADOW_VALIDATION"
    assert (match.home_score, match.away_score, match.outcome) == (2, 1, "HOME")


def test_revision_after_authoritative_bsd_settlement_does_not_rewrite_match():
    match, _, _ = _bsd_graph()
    first, disposition = record(
        match,
        Result("BSD", "1001", "FT", 1, 2, "AWAY", NOW, {}),
        authoritative=True,
    )
    assert disposition == "RECORDED" and first.authoritative
    second, disposition = record(
        match,
        Result("BSD", "1001", "FT", 2, 1, "HOME", NOW + timedelta(minutes=31), {}),
        authoritative=True,
    )
    match.refresh_from_db()
    assert disposition == "RESULT_CONFLICT"
    assert second.conflict and not second.authoritative
    assert (match.home_score, match.away_score, match.outcome) == (1, 2, "AWAY")


def test_expired_backoff_resumes_without_open_position():
    match, route, event = _bsd_graph()
    route.bsd_state = "BSD_BACKOFF"
    route.bsd_backoff_until = NOW - timedelta(seconds=1)
    route.provenance = {
        "bsd_season_ids": {"1": 2026},
        "bsd_previous_state": "BSD_SHADOW_VALIDATION",
    }
    route.save()
    session = BSDSession(event)
    with override_settings(BSD_API_TOKEN="fake-only"):
        early = run_bsd_continuity(
            at=NOW - timedelta(seconds=2), client_factory=lambda: _client(session)
        )
        recovered = run_bsd_continuity(at=NOW, client_factory=lambda: _client(session))
    route.refresh_from_db()
    assert early["bindings"] == 0 and early["identity_calls"] == 0
    assert recovered["bindings"] == 1
    assert route.bsd_state == "BSD_SHADOW_VALIDATION"
    assert len(session.calls) == 1
    assert not match.capital_positions.exists()


class FirstCall429(BSDSession):
    def get(self, url, **kwargs):
        if not self.calls:
            self.calls.append(url)
            response = Response({"code": "taster_exhausted"})
            response.status_code = 429
            response.headers = {"Retry-After": "3600"}
            return response
        return super().get(url, **kwargs)


def test_daily_429_retries_incremental_binding_after_reset_same_lima_day():
    match, route, event = _bsd_graph()
    session = FirstCall429(event)
    with override_settings(BSD_API_TOKEN="fake-only"):
        first = run_bsd_continuity(at=NOW, client_factory=lambda: _client(session))
        before_reset = run_bsd_continuity(
            at=NOW + timedelta(minutes=59), client_factory=lambda: _client(session)
        )
        after_reset = run_bsd_continuity(
            at=NOW + timedelta(hours=1, seconds=1),
            client_factory=lambda: _client(session),
        )
    route.refresh_from_db()
    assert first["bindings"] == 0 and "BSD_TASTER_EXHAUSTED" in first["errors"]
    assert before_reset["identity_calls"] == 0
    assert after_reset["bindings"] == 1
    assert route.bsd_state == "BSD_SHADOW_VALIDATION"
    assert len(session.calls) == 2
    assert not match.capital_positions.exists()


def test_daily_429_retries_shadow_after_reset_same_lima_day():
    match, route, event = _bsd_graph()
    BSDEventBinding.objects.create(match=match, bsd_league_id=1, bsd_event_id=1001)
    session = FirstCall429(event)
    at = match.kickoff + timedelta(hours=3)
    with override_settings(BSD_API_TOKEN="fake-only"):
        first = run_bsd_continuity(at=at, client_factory=lambda: _client(session))
        before_reset = run_bsd_continuity(
            at=at + timedelta(minutes=59), client_factory=lambda: _client(session)
        )
        after_reset = run_bsd_continuity(
            at=at + timedelta(hours=1, seconds=1),
            client_factory=lambda: _client(session),
        )
    route.refresh_from_db()
    assert first["shadow_calls"] == 1 and first["shadow_observations"] == 0
    assert before_reset["shadow_calls"] == 0
    assert after_reset["shadow_calls"] == 1 and after_reset["shadow_observations"] == 1
    assert route.bsd_state == "BSD_SHADOW_VALIDATION"
    assert len(session.calls) == 2
    assert not match.capital_positions.exists()


def test_bootstrap_sends_utc_calendar_dates_not_datetimes(monkeypatch):
    routes = []
    for index in range(1, 24):
        match = _match()
        routes.append(
            CompetitionResultRoute.objects.create(
                competition=match.season.competition,
                api_football_league_id=index,
                bsd_league_ids=[index, 24] if index == 1 else [index],
                bsd_state="BSD_BOOTSTRAP_PENDING",
            )
        )
    sent = []

    def fake_page(client, endpoint, params, identity):
        if endpoint == "leagues/":
            return [{"id": i, "current_season": {"id": 2026}} for i in range(1, 25)]
        if endpoint == "events/":
            sent.append(params)
        return []

    monkeypatch.setattr("football.providers.bsd_bootstrap._page", fake_page)
    # September 29 in Lima, but September 30 in UTC.
    at = datetime(2026, 9, 29, 23, 30, tzinfo=dt_timezone(timedelta(hours=-5)))
    assert at.astimezone(UTC).date().isoformat() == "2026-09-30"
    results = bootstrap(client=object(), at=at)
    assert len(results) == 23 and len(sent) == 24
    assert all(
        item["date_from"] == "2026-09-30" and item["date_to"] == "2026-10-14"
        for item in sent
    )
