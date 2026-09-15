"""Persisted FS-016 study adapters using the v2 event chronology."""

from __future__ import annotations

import hashlib
import json
import random
from dataclasses import dataclass
from datetime import timedelta
from decimal import Decimal

from django.db import transaction
from django.utils import timezone

from football.models import (
    CapitalExecutionBasis,
    CapitalExecutionState,
    CapitalPosition,
    CapitalRuntimeConfig,
    Decision,
    HistoricalMarketEvidence,
    Match,
)

from .contracts import CapitalDecision, RunUnavailable, json_decimal
from .policies import POLICY_VERSIONS, make_policy
from .runtime import (
    EXECUTION_VERSION,
    FINISHED_STATUSES,
    RUNTIME_VERSION,
    VOID_STATUSES,
    ZERO,
    _decimal_state,
)
from .stress import deteriorate_probability, is_forced_loss, stress_parameters

FIXED_LANES = {
    "FLAT_UNIT": 10,
    "FIXED_FRACTION_BANKROLL": 10,
    "FIXED_TARGET_PROFIT_NO_RECOVERY": 10,
    "LEGACY_RECOVERY": 1,
    "LEGACY_CAPPED": 1,
    "LEGACY_PARTIAL": 1,
    "FRACTIONAL_KELLY": 10,
}


@dataclass(frozen=True)
class StudyCandidate:
    decision: Decision
    execution_at: object
    settlement_at: object
    price: Decimal | None
    probability: Decimal | None
    outcome: str
    observation_id: int | None
    historical_evidence_id: int | None
    evidence_class: str
    provenance: dict


def _canonical_study_outcome(match, mode):
    if mode not in {
        CapitalRuntimeConfig.Mode.REPLAY,
        CapitalRuntimeConfig.Mode.HISTORICAL,
    }:
        return match.outcome
    if match.status_short in VOID_STATUSES:
        return "VOID"
    if match.status_short in FINISHED_STATUSES and match.outcome in {
        Match.OUTCOME_HOME,
        Match.OUTCOME_DRAW,
        Match.OUTCOME_AWAY,
    }:
        return match.outcome
    if match.status_short in FINISHED_STATUSES | {"PST", "SUSP"}:
        raise RunUnavailable(
            f"UNRESOLVED_CANONICAL_OUTCOME:{match.pk}:{match.status_short}"
        )
    raise RunUnavailable(
        f"UNSUPPORTED_CANONICAL_RESULT:{match.pk}:{match.status_short or 'BLANK'}"
    )


def _study_candidates(decisions, *, mode):
    historical = mode == CapitalRuntimeConfig.Mode.HISTORICAL
    candidates = []
    for decision in decisions:
        evidence = None
        if historical:
            evidence = (
                HistoricalMarketEvidence.objects.filter(
                    match=decision.match,
                    time_semantics=HistoricalMarketEvidence.TimeSemantics.ASSUMED_T30M,
                )
                .order_by("source_id")
                .first()
            )
            price = (
                getattr(evidence, f"{decision.action.lower()}_price")
                if evidence and decision.action != Decision.ACTION_NO_BET
                else None
            )
            execution_at = decision.match.kickoff - timedelta(minutes=30)
            evidence_class = HistoricalMarketEvidence.EVIDENCE_CLASS
            provenance = {
                "source_price_is_real": True,
                "timestamp_is_imputed": True,
                "time_semantics": "ASSUMED_T30M",
                "settlement_time": "SYNTHETIC_RESEARCH_ONLY",
                "provenance_version": evidence.provenance_version if evidence else "",
            }
            observation_id = None
        else:
            observation = decision.selected_odds_observation
            price = decision.selected_price
            execution_at = (
                observation.observed_at if observation else decision.decision_time
            )
            evidence_class = "EXPLICIT_V2_STUDY"
            provenance = {"settlement_time": "SYNTHETIC_RESEARCH_ONLY"}
            observation_id = decision.selected_odds_observation_id
        candidates.append(
            StudyCandidate(
                decision=decision,
                execution_at=execution_at,
                settlement_at=decision.match.kickoff + timedelta(hours=2),
                price=price,
                probability=(
                    Decimal(str(decision.model_probability))
                    if decision.model_probability is not None
                    else None
                ),
                outcome=_canonical_study_outcome(decision.match, mode),
                observation_id=observation_id,
                historical_evidence_id=evidence.pk if evidence else None,
                evidence_class=evidence_class,
                provenance=provenance,
            )
        )
    return tuple(candidates)


def _outcome_for(candidate, mode, rng, stress, action_index):
    if mode in (
        CapitalRuntimeConfig.Mode.REPLAY,
        CapitalRuntimeConfig.Mode.HISTORICAL,
    ):
        return candidate.outcome
    probability = float(candidate.probability or ZERO)
    if mode == CapitalRuntimeConfig.Mode.STRESS:
        probability = deteriorate_probability(probability, stress["probability_delta"])
    won = rng.random() < probability
    if mode == CapitalRuntimeConfig.Mode.STRESS and is_forced_loss(
        action_index,
        start=stress["forced_loss_start"],
        length=stress["forced_loss_length"],
    ):
        won = False
    return candidate.decision.action if won else "LOSS"


def _run_path(candidates, policy_code, policy_config, max_lanes, mode, seed, stress):
    policy = make_policy(policy_code, policy_config)
    rng = random.Random(seed)
    equity = Decimal("100")
    peak_equity = Decimal("100")
    maximum_drawdown = ZERO
    reserved = ZERO
    state = policy.initial_state()
    open_rows = []
    ledger = []
    wins = losses = voids = 0
    active = True
    practical_ruin = False
    termination_reason = ""
    action_index = 0

    def settle_due(until=None):
        nonlocal equity, peak_equity, maximum_drawdown, reserved, state
        nonlocal wins, losses, voids
        nonlocal active, practical_ruin, termination_reason
        due = sorted(open_rows, key=lambda row: (row[0], row[1].decision.pk))
        for row in tuple(due):
            settlement_at, candidate, request, price, outcome = row
            if until is not None and settlement_at > until:
                continue
            open_rows.remove(row)
            reserved -= request.applied
            state_before = state
            if outcome == "VOID":
                pnl = ZERO
                status = CapitalPosition.Status.VOID
                voids += 1
            else:
                won = outcome == candidate.decision.action
                pnl = request.applied * (price - 1) if won else -request.applied
                state, _ = policy.settle(state, request, won)
                status = (
                    CapitalPosition.Status.SETTLED_WIN
                    if won
                    else CapitalPosition.Status.SETTLED_LOSS
                )
                wins += int(won)
                losses += int(not won)
            equity += pnl
            peak_equity = max(peak_equity, equity)
            if peak_equity > ZERO:
                drawdown = (peak_equity - equity) / peak_equity
                maximum_drawdown = max(maximum_drawdown, drawdown)
            if equity <= ZERO and not practical_ruin:
                active = False
                practical_ruin = True
                termination_reason = "BANKROLL_DEPLETED"
            ledger.append(
                {
                    "kind": "SETTLEMENT",
                    "candidate": candidate,
                    "at": settlement_at,
                    "status": status,
                    "pnl": pnl,
                    "equity": equity,
                    "reserved": reserved,
                    "state_before": state_before,
                    "state_after": state,
                    "practical_ruin": practical_ruin,
                    "termination_reason": termination_reason,
                }
            )

    def ranking_key(row):
        ev = (
            row.probability * row.price - 1
            if row.probability is not None and row.price is not None
            else Decimal("-Infinity")
        )
        return row.execution_at, -ev, row.decision.match.kickoff, row.decision.pk

    for candidate in sorted(candidates, key=ranking_key):
        settle_due(candidate.execution_at)
        if not active:
            continue
        if candidate.decision.action == Decision.ACTION_NO_BET:
            ledger.append(
                {"kind": "NOT_PLACED", "candidate": candidate, "reason": "NO_BET"}
            )
            continue
        if candidate.price is None or candidate.price <= 1:
            ledger.append(
                {
                    "kind": "NOT_PLACED",
                    "candidate": candidate,
                    "reason": "NO_EXECUTION_PRICE",
                }
            )
            continue
        if len(open_rows) >= max_lanes:
            ledger.append(
                {
                    "kind": "NOT_PLACED",
                    "candidate": candidate,
                    "reason": "EXPIRED_CAPACITY",
                }
            )
            continue
        price = candidate.price
        if mode == CapitalRuntimeConfig.Mode.STRESS:
            haircut = Decimal(str(stress["price_haircut"]))
            price = Decimal("1") + (price - Decimal("1")) * (Decimal("1") - haircut)
        capital_decision = CapitalDecision(
            source_id=candidate.decision.pk,
            decision_time=candidate.execution_at,
            action=candidate.decision.action,
            outcome="",
            price=price,
            probability=candidate.probability,
            observation_id=candidate.observation_id,
            observation_time=candidate.execution_at,
        )
        request = policy.request(capital_decision, equity, _decimal_state(state))
        available = equity - reserved
        if request.termination_reason:
            active = False
            practical_ruin = True
            termination_reason = request.termination_reason
            ledger.append(
                {
                    "kind": "NOT_PLACED",
                    "candidate": candidate,
                    "reason": "INELIGIBLE",
                    "termination_reason": request.termination_reason,
                }
            )
            continue
        if request.requested <= ZERO:
            ledger.append(
                {
                    "kind": "NOT_PLACED",
                    "candidate": candidate,
                    "reason": "INELIGIBLE",
                }
            )
            continue
        if request.requested > available:
            ledger.append(
                {
                    "kind": "NOT_PLACED",
                    "candidate": candidate,
                    "reason": "INSUFFICIENT_AVAILABLE_CASH",
                }
            )
            continue
        placement = {
            "kind": "PLACEMENT",
            "candidate": candidate,
            "at": candidate.execution_at,
            "price": price,
            "request": request,
            "equity_before": equity,
            "reserved_before": reserved,
            "state_before": state,
        }
        reserved += request.applied
        placement["reserved_after"] = reserved
        ledger.append(placement)
        outcome = _outcome_for(candidate, mode, rng, stress, action_index)
        action_index += 1
        open_rows.append((candidate.settlement_at, candidate, request, price, outcome))
    settle_due()
    return {
        "terminal_equity": equity,
        "peak_equity": peak_equity,
        "maximum_drawdown": maximum_drawdown,
        "realized_pnl": equity - Decimal("100"),
        "wins": wins,
        "losses": losses,
        "voids": voids,
        "placed": sum(row["kind"] == "PLACEMENT" for row in ledger),
        "not_placed": sum(row["kind"] == "NOT_PLACED" for row in ledger),
        "ledger": ledger,
        "policy_state": state,
        "practical_ruin": practical_ruin,
        "termination_reason": termination_reason,
    }


def _identity(
    mode, policy_code, policy_config, decision_ids, seed, path_count, stress_config
):
    payload = {
        "runtime": RUNTIME_VERSION,
        "mode": mode,
        "policy": policy_code,
        "config": policy_config,
        "decisions": decision_ids,
        "seed": seed,
        "path_count": path_count,
        "stress": stress_config,
    }
    digest = hashlib.sha256(
        json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()
    return f"{RUNTIME_VERSION}:study:{digest}"


@transaction.atomic
def run_persisted_v2_study(
    decisions,
    *,
    policy_code,
    policy_config,
    mode,
    seed=0,
    path_count=1,
    stress=None,
):
    """Persist a v2 study summary plus one complete audit trajectory."""

    decisions = tuple(
        Decision.objects.filter(
            pk__in=[row.pk if isinstance(row, Decision) else row for row in decisions]
        )
        .select_related("match", "prediction", "selected_odds_observation")
        .order_by("match__kickoff", "id")
    )
    if not decisions:
        raise ValueError("A v2 study requires at least one Decision.")
    if mode not in {
        CapitalRuntimeConfig.Mode.REPLAY,
        CapitalRuntimeConfig.Mode.MONTE_CARLO,
        CapitalRuntimeConfig.Mode.STRESS,
        CapitalRuntimeConfig.Mode.HISTORICAL,
    }:
        raise ValueError("Unsupported v2 study mode.")
    if path_count < 1:
        raise ValueError("path_count must be positive.")
    max_lanes = FIXED_LANES[policy_code]
    historical = mode == CapitalRuntimeConfig.Mode.HISTORICAL
    candidates = _study_candidates(decisions, mode=mode)
    stress_config = stress_parameters(stress or {})
    identity = _identity(
        mode,
        policy_code,
        policy_config,
        [row.pk for row in decisions],
        seed,
        path_count,
        stress_config,
    )
    existing = CapitalRuntimeConfig.objects.filter(identity=identity).first()
    if existing:
        return existing
    paths = [
        _run_path(
            candidates,
            policy_code,
            policy_config,
            max_lanes,
            mode,
            seed + index,
            stress_config,
        )
        for index in range(path_count)
    ]
    mean_equity = sum((row["terminal_equity"] for row in paths), ZERO) / Decimal(
        path_count
    )
    first = paths[0]
    config = CapitalRuntimeConfig.objects.create(
        identity=identity,
        runtime_version=RUNTIME_VERSION,
        execution_version=EXECUTION_VERSION,
        mode=mode,
        automatic=False,
        current=False,
        source_model_code=decisions[0].prediction.model_code,
        decision_policy_code=decisions[0].policy_code,
        decision_policy_variant=decisions[0].policy_variant,
        policy_code=policy_code,
        policy_version=POLICY_VERSIONS[policy_code],
        policy_config=policy_config,
        max_lanes=max_lanes,
        initial_bankroll=Decimal("100"),
        bankroll_equity=first["terminal_equity"],
        reserved_exposure=ZERO,
        policy_state=json_decimal(first["policy_state"]),
        status=(
            CapitalRuntimeConfig.Status.TERMINATED
            if first["practical_ruin"]
            else CapitalRuntimeConfig.Status.COMPLETE
        ),
        practical_ruin=first["practical_ruin"],
        termination_reason=first["termination_reason"],
        peak_equity=first["peak_equity"],
        maximum_drawdown=first["maximum_drawdown"],
        completed_at=timezone.now(),
        metrics={
            "chronology": "FS016_EVENT_TIME_V2",
            "path_count": path_count,
            "mean_terminal_equity": str(mean_equity),
            "terminal_equity_min": str(min(row["terminal_equity"] for row in paths)),
            "terminal_equity_max": str(max(row["terminal_equity"] for row in paths)),
            "placed": first["placed"],
            "not_placed": first["not_placed"],
            "practical_ruin_paths": sum(row["practical_ruin"] for row in paths),
            "termination_reasons": sorted(
                {
                    row["termination_reason"]
                    for row in paths
                    if row["termination_reason"]
                }
            ),
            "no_winner_claim": True,
        },
        provenance={
            "research_only": True,
            "seed": seed,
            "stress": stress_config if mode == CapitalRuntimeConfig.Mode.STRESS else {},
            "historical_time_semantics": (
                "SYNTHETIC_TIME_RESEARCH_ONLY" if historical else ""
            ),
        },
    )
    placements = {}
    settlements = {
        row["candidate"].decision.pk: row
        for row in first["ledger"]
        if row["kind"] == "SETTLEMENT"
    }
    for row in first["ledger"]:
        candidate = row["candidate"]
        if row["kind"] == "NOT_PLACED":
            CapitalExecutionState.objects.create(
                config=config,
                match=candidate.decision.match,
                status=CapitalExecutionState.Status.NOT_PLACED,
                non_placement_reason=row["reason"],
                terminal_at=candidate.execution_at,
                diagnostics={"policy_reason": row.get("termination_reason", "")},
            )
            continue
        if row["kind"] != "PLACEMENT":
            continue
        basis = CapitalExecutionBasis.objects.create(
            config=config,
            match=candidate.decision.match,
            prediction=candidate.decision.prediction,
            originating_decision=candidate.decision,
            decision_policy_code=candidate.decision.policy_code,
            decision_policy_variant=candidate.decision.policy_variant,
            decision_policy_version=candidate.decision.policy_version,
            decision_policy_config=candidate.decision.policy_config,
            action=candidate.decision.action,
            reason=candidate.decision.reason,
            model_probability=candidate.probability,
            selected_odds_observation_id=candidate.observation_id,
            historical_market_evidence_id=candidate.historical_evidence_id,
            selected_price=row["price"],
            expected_value=(
                candidate.probability * row["price"] - 1
                if candidate.probability is not None
                else None
            ),
            execution_at=candidate.execution_at,
            evidence_not_before=candidate.execution_at,
            evidence_cutoff=candidate.execution_at + timedelta(microseconds=1),
            evidence_class=candidate.evidence_class,
            provenance=candidate.provenance,
        )
        settled = settlements[candidate.decision.pk]
        position = CapitalPosition.objects.create(
            config=config,
            match=candidate.decision.match,
            execution_basis=basis,
            status=settled["status"],
            placed_at=row["at"],
            result_known_at=settled["at"],
            settled_at=settled["at"],
            requested_stake=row["request"].requested,
            applied_stake=row["request"].applied,
            policy_step=row["request"].step,
            request_metadata=json_decimal(row["request"].metadata),
            placement_equity_before=row["equity_before"],
            placement_reserved_before=row["reserved_before"],
            placement_available_before=row["equity_before"] - row["reserved_before"],
            placement_equity_after=row["equity_before"],
            placement_reserved_after=row["reserved_after"],
            placement_available_after=row["equity_before"] - row["reserved_after"],
            settlement_equity_after=settled["equity"],
            settlement_reserved_after=settled["reserved"],
            settlement_available_after=settled["equity"] - settled["reserved"],
            realized_pnl=settled["pnl"],
            policy_state_before=json_decimal(row["state_before"]),
            policy_state_after=json_decimal(settled["state_after"]),
            cap_hit=row["request"].cap_hit,
            shortfall=row["request"].shortfall,
            practical_ruin=settled["practical_ruin"],
            termination_reason=settled["termination_reason"],
            debt_status=CapitalPosition.DebtStatus.RESOLVED,
        )
        placements[candidate.decision.pk] = position
        CapitalExecutionState.objects.create(
            config=config,
            match=candidate.decision.match,
            status=CapitalExecutionState.Status.PLACED,
            execution_basis=basis,
            position=position,
        )
    return config
