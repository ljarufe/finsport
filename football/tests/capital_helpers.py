from datetime import date, datetime, timedelta, timezone
from decimal import Decimal

from football.models import (
    Bookmaker,
    Competition,
    Decision,
    Match,
    OddsMarket,
    OddsObservation,
    Prediction,
    PredictionExperiment,
    Season,
    Source,
    Team,
)


def create_capital_stream(
    rows,
    *,
    model_code=Prediction.DIXON_COLES,
    model_variant="",
    decision_policy="VALUE",
    decision_variant="",
    comparator=False,
    enabled=False,
    suffix="",
    base=None,
):
    competition = Competition.objects.create(
        name=f"Capital Test League{suffix}",
        competition_type="League",
        country="PE",
        enabled=enabled,
    )
    season = Season.objects.create(
        competition=competition,
        year=2025,
        start_date=date(2025, 1, 1),
        end_date=date(2025, 12, 31),
    )
    home = Team.objects.create(competition=competition, name=f"Capital Home{suffix}")
    away = Team.objects.create(competition=competition, name=f"Capital Away{suffix}")
    source = Source.objects.create(
        code=f"capital-test{suffix}".strip("-")[:50],
        name=f"Capital Test{suffix}",
        base_url="https://example.test",
    )
    bookmaker = Bookmaker.objects.create(
        source=source, external_id="capital", name="Capital Book"
    )
    market = OddsMarket.objects.create(
        source=source, external_id="1x2", name="Match Winner"
    )
    experiment = PredictionExperiment.objects.create(
        competition=competition,
        mode=PredictionExperiment.MODE_PROSPECTIVE,
        period_start=date(2025, 1, 1),
        period_end=date(2025, 1, 31),
        config={},
    )
    decisions = []
    base = base or datetime(2025, 1, 1, 12, tzinfo=timezone.utc)
    for index, spec in enumerate(rows, start=1):
        decision_time = spec.get("decision_time", base + timedelta(days=index))
        action = spec.get("action", Match.OUTCOME_HOME)
        outcome = spec.get("outcome", Match.OUTCOME_HOME)
        price = spec.get("price", Decimal("2.0000"))
        probability = spec.get("probability", 0.6)
        match = Match.objects.create(
            season=season,
            home_team=home,
            away_team=away,
            kickoff=decision_time + timedelta(hours=2, minutes=index),
            status_short="FT" if outcome else "NS",
            status_long="Match Finished" if outcome else "Not Started",
            outcome=outcome,
        )
        prediction = None
        if not comparator:
            prediction = Prediction.objects.create(
                experiment=experiment,
                match=match,
                model_code=model_code,
                variant=model_variant,
                model_version=spec.get("model_version", "test-v1"),
                model_config=spec.get("model_config", {}),
                cutoff=decision_time,
                p_home=0.6,
                p_draw=0.2,
                p_away=0.2,
                predicted_outcome=Match.OUTCOME_HOME,
                actual_outcome=outcome or None,
            )
        observation = None
        selected_price = None
        if action != Decision.ACTION_NO_BET and price is not None:
            observation = OddsObservation.objects.create(
                match=match,
                source=source,
                bookmaker=bookmaker,
                market=market,
                home=price,
                draw=Decimal("3.0000"),
                away=Decimal("4.0000"),
                observed_at=spec.get(
                    "observation_time", decision_time - timedelta(hours=1)
                ),
            )
            selected_price = price
        decisions.append(
            Decision.objects.create(
                experiment=experiment,
                match=match,
                prediction=prediction,
                policy_code=decision_policy,
                policy_variant=decision_variant,
                policy_version=spec.get("policy_version", "test-decision-v1"),
                policy_config=spec.get("policy_config", {}),
                decision_time=decision_time,
                action=action,
                reason=spec.get("reason", "TEST"),
                model_probability=(
                    probability if action != Decision.ACTION_NO_BET else None
                ),
                selected_odds_observation=observation,
                selected_price=selected_price,
            )
        )
    return experiment, decisions
