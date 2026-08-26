from datetime import timedelta
from decimal import Decimal

import pytest
from django.core.exceptions import ValidationError

from football.models import OddsMarket, OddsObservation, OddsSnapshot, Prediction
from football.sync import sync_fixture_payloads, sync_odds_payloads, upsert_current_odds

from .helpers import catalog_season, competition, fixture_payload, odds_payload, source

pytestmark = pytest.mark.django_db


def test_upsert_appends_temporal_observation_but_keeps_one_current_projection():
    tracked = competition()
    catalog_season(tracked)
    _, accepted = sync_fixture_payloads([fixture_payload()], {"39": tracked})
    match = accepted["1001"]
    market = OddsMarket.objects.create(source=source(), external_id="1", name="1X2")
    bookmaker = source().bookmaker_set.create(external_id="8", name="Book")
    observed = match.kickoff - timedelta(hours=3)
    provider_updated = observed - timedelta(minutes=5)
    prices = (Decimal("2.1"), Decimal("3.2"), Decimal("3.5"))

    upsert_current_odds(
        match=match,
        source=source(),
        bookmaker=bookmaker,
        market=market,
        prices=prices,
        provider_updated_at=provider_updated,
        observed_at=observed,
    )
    upsert_current_odds(
        match=match,
        source=source(),
        bookmaker=bookmaker,
        market=market,
        prices=prices,
        observed_at=observed,
    )
    upsert_current_odds(
        match=match,
        source=source(),
        bookmaker=bookmaker,
        market=market,
        prices=prices,
        observed_at=observed + timedelta(minutes=1),
    )

    assert OddsSnapshot.objects.count() == 1
    assert OddsObservation.objects.count() == 2
    assert (
        OddsObservation.objects.get(observed_at=observed).provider_updated_at
        == provider_updated
    )
    assert OddsSnapshot.objects.get().observed_at == observed + timedelta(minutes=1)


def test_prediction_rejects_invalid_probability_vector():
    prediction = Prediction(p_home=0.8, p_draw=0.8, p_away=-0.6)
    with pytest.raises(ValidationError):
        prediction.clean()


def test_invalid_decimal_quote_is_fail_soft_and_creates_no_current_or_history_row():
    tracked = competition()
    catalog_season(tracked)
    _, accepted = sync_fixture_payloads([fixture_payload()], {"39": tracked})
    market = OddsMarket.objects.create(
        source=source(), external_id="1", name="Match Winner"
    )

    stats = sync_odds_payloads([odds_payload(home="1.0")], accepted, market)

    assert stats.skipped == 1
    assert not OddsSnapshot.objects.exists()
    assert not OddsObservation.objects.exists()
