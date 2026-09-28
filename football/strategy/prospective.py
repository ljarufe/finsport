"""Only real governed prospective captures feed automatic #209 evaluation."""

import hashlib
import json
from datetime import timedelta
from decimal import Decimal
from zoneinfo import ZoneInfo

from django.conf import settings
from django.db import transaction

from football.capital.runtime import ACCEPTED_CAPTURE_STATUSES, ExecutionCandidate
from football.models import (
    CapitalDeployment,
    CaptureWorkItem,
    Decision,
    PredictionExperiment,
)
from football.prediction.contracts import ProbabilityResult
from football.prediction.evaluation import _persist_policy_decision, _persist_prediction
from football.prediction.market import (
    MarketConsensusAdapter,
    market_selection_as_of,
)
from football.prediction.policies import selective_confidence

from . import clock


def evidence_identity(work):
    return hashlib.sha256(
        json.dumps(
            dict(
                work_identity=work.logical_identity,
                run_id=work.run_id,
                executed_at=work.executed_at.isoformat(),
                cutoff=work.run.completed_at.isoformat(),
            ),
            sort_keys=True,
        ).encode()
    ).hexdigest()


def capture_reason(work, deployment):
    if not work.match.competition.enabled:
        return "INELIGIBLE"
    if work.status == CaptureWorkItem.Status.MISSED_WINDOW:
        return "MISSED_EXECUTION_WINDOW"
    if (
        work.purpose != CaptureWorkItem.Purpose.ODDS_CAPTURE
        or work.intended_window != "market-t30m"
        or work.status not in ACCEPTED_CAPTURE_STATUSES
        or not work.executed_at
        or not work.completed_at
        or not work.run.completed_at
    ):
        return "NO_EXECUTION_PRICE"
    if not (
        work.not_before
        and work.not_after
        and work.target_at
        and work.target_at == work.match.kickoff - timedelta(minutes=30)
        and work.not_before <= work.executed_at <= work.not_after
        and work.executed_at
        <= work.completed_at
        <= work.run.completed_at
        < work.match.kickoff
    ):
        return "INELEGIBLE_EXECUTION_QUOTE"
    if deployment.activated_at is None or work.executed_at < deployment.activated_at:
        return "PRE_GLOBAL"
    return ""


def live_quotes(work, deployment):
    """Same v2 mathematics as #209; all canonical live API-Football books; acquisition is PROSPECTIVE_ACTUAL.

    Provider createdAt reconstruction is intentionally never applied to live
    observations. The batch execution lower bound excludes stale/past captures.
    Each raw 1/X/2 row is one complete bookmaker, never a stitched triplet.
    """
    selection = live_selection(work)
    return selection.quotes


def live_selection(work):
    return market_selection_as_of(
        work.match,
        work.run.completed_at,
        not_before=work.executed_at,
        capture_work=work,
    )


@transaction.atomic
def evaluate_work(work, *, at):
    deployment = CapitalDeployment.objects.select_for_update().get(pk=1)
    from .deployment import admission_reason

    reason = (
        admission_reason(deployment, deployment.config)
        if deployment.config_id
        else "STRATEGY_DRAINING"
    )
    reason = reason or capture_reason(work, deployment)
    if reason:
        return None, reason
    if clock.effective_now(planning_at=at) >= work.match.kickoff:
        return None, "MISSED_EXECUTION_WINDOW"
    selection = live_selection(work)
    quotes = selection.quotes
    spec = deployment.selection["prospective_prediction_effective_config"]
    if len(quotes) < spec["minimum_books"]:
        return None, "INPUT_QUOTES_MISSING"
    at = clock.effective_now(planning_at=at)
    if at >= work.match.kickoff:
        return None, "MISSED_EXECUTION_WINDOW"
    identity = evidence_identity(work)
    logical = f"fs022:{deployment.cutover_id}:{work.logical_identity}"
    experiment, created = PredictionExperiment.objects.get_or_create(
        competition=work.match.competition,
        mode=PredictionExperiment.MODE_PROSPECTIVE,
        logical_identity=logical,
        defaults=dict(
            period_start=work.match.kickoff.astimezone(
                ZoneInfo(settings.TIME_ZONE)
            ).date(),
            period_end=work.match.kickoff.astimezone(
                ZoneInfo(settings.TIME_ZONE)
            ).date(),
            intended_window=work.intended_window,
            target_at=work.target_at,
            config=dict(
                selection=deployment.selection,
                capture_evidence_identity=identity,
                work_id=work.pk,
                real_betting=False,
            ),
        ),
    )
    if not created:
        decision = experiment.decisions.select_related(
            "prediction", "selected_odds_observation"
        ).get()
        return decision, ""
    adapter = MarketConsensusAdapter()
    adapter.config = dict(
        adapter.config,
        **spec,
        prospective_config_identity=deployment.selection[
            "prospective_prediction_config_identity"
        ],
        scientific_selection_config_identity=deployment.selection[
            "prediction_config_identity"
        ],
    )
    probability = adapter.predict_selection(selection)
    probability = ProbabilityResult(
        probability.p_home,
        probability.p_draw,
        probability.p_away,
        diagnostics=dict(
            probability.diagnostics,
            capture_evidence_identity=identity,
            prospective_config_identity=deployment.selection[
                "prospective_prediction_config_identity"
            ],
            scientific_selection_config_identity=deployment.selection[
                "prediction_config_identity"
            ],
            evidence_class="PROSPECTIVE_ACTUAL",
            capture_work_item_id=work.pk,
            capture_run_id=work.run_id,
            capture_source_id=work.source_id,
            capture_market_id=work.market_id,
            capture_executed_at=work.executed_at.isoformat(),
            evidence_not_before=work.executed_at.isoformat(),
            evidence_cutoff=work.run.completed_at.isoformat(),
            quote_ids=[q.observation.pk for q in quotes],
            scientific_disposition="UNSTABLE",
        ),
    )
    prediction = _persist_prediction(
        experiment,
        work.match,
        adapter,
        probability,
        work.run.completed_at,
        evidence_identity=identity,
    )
    prices = {
        outcome: (q.observation, getattr(q.observation, outcome.lower()))
        for i, outcome in enumerate(("HOME", "DRAW", "AWAY"))
        for q in [max(quotes, key=lambda candidate: candidate.prices[i])]
    }
    result = selective_confidence(probability, 0.45, prices)
    decision = _persist_policy_decision(
        experiment, work.match, prediction, "SELECTIVE_CONFIDENCE", "0.45", result, at
    )
    experiment.completed_at = at
    experiment.summary = dict(target_count=1, prediction_count=1, decision_count=1)
    experiment.save()
    return decision, ""


def frozen_candidate(work, decision):
    from football.prediction.policies import PolicyResult

    observation = decision.selected_odds_observation
    result = PolicyResult(
        decision.action,
        decision.reason,
        decision.model_probability,
        observation,
        decision.selected_price,
        decision.expected_value,
        decision.policy_config,
    )
    return ExecutionCandidate(
        work,
        decision,
        result,
        decision.selected_price,
        observation.pk if observation else None,
        (
            Decimal(str(decision.model_probability))
            if decision.model_probability is not None
            else None
        ),
        (
            Decimal(str(decision.expected_value))
            if decision.expected_value is not None
            else None
        ),
    )


def validate_candidate(candidate, deployment, *, basis=None):
    work, decision = candidate.work_item, candidate.decision
    reason = capture_reason(work, deployment)
    if reason:
        return reason
    if decision is None:
        return "INPUT_QUOTES_MISSING"
    pd = deployment.selection["winner_candidate"]["prediction_decision"]
    prediction = decision.prediction
    if not (
        decision.match_id == work.match_id
        and candidate.result.action == decision.action
        and prediction.match_id == work.match_id
        and decision.policy_code == pd["decision_policy"]
        and decision.policy_variant == pd["decision_variant"]
        and decision.policy_version == pd["decision_policy_version"]
        and decision.policy_config == pd["decision_config"]
        and prediction.model_code == pd["prediction_code"]
        and prediction.model_version == pd["prediction_version"]
        and prediction.evidence_identity == evidence_identity(work)
        and prediction.model_config.get("prospective_config_identity")
        == deployment.selection["prospective_prediction_config_identity"]
        and prediction.cutoff
        == work.run.completed_at
        <= decision.decision_time
        < work.match.kickoff
    ):
        return "AUTHORITY_EVIDENCE_MISMATCH"
    if basis is not None and not (
        basis.provenance.get("prospective_config_identity")
        == deployment.selection["prospective_prediction_config_identity"]
        and basis.provenance.get("quote_ids") == prediction.diagnostics.get("quote_ids")
        and basis.provenance.get("source_id") == work.source_id
        and basis.provenance.get("market_id") == work.market_id
    ):
        return "AUTHORITY_EVIDENCE_MISMATCH"
    if candidate.result.action == Decision.ACTION_NO_BET:
        return ""
    quotes = live_quotes(work, deployment)
    if [q.observation.pk for q in quotes] != prediction.diagnostics.get("quote_ids"):
        return "AUTHORITY_EVIDENCE_MISMATCH"
    observation = next(
        (
            q.observation
            for q in quotes
            if q.observation.pk == candidate.selected_observation_id
        ),
        None,
    )
    if not observation or candidate.result.action not in ("HOME", "DRAW", "AWAY"):
        return "INELEGIBLE_EXECUTION_QUOTE"
    if not (
        len(quotes)
        >= deployment.selection["prospective_prediction_effective_config"][
            "minimum_books"
        ]
        and candidate.selected_price
        == getattr(observation, candidate.result.action.lower())
        and candidate.selected_price == decision.selected_price
        and candidate.selected_observation_id == decision.selected_odds_observation_id
        and candidate.result.action == decision.action
        and candidate.model_probability.quantize(Decimal("0.000000000001"))
        == Decimal(str(decision.model_probability)).quantize(Decimal("0.000000000001"))
    ):
        return "EXECUTION_PRICE_MISMATCH"
    return ""


@transaction.atomic
def reconcile_global(capture_run_id, *, at):
    from football.capital.runtime import (
        RuntimeResult,
        _candidate_from_basis,
        _terminal_state,
        place_candidate,
    )
    from football.models import CapitalEvaluation, CapitalExecutionState

    from .deployment import locked_deployment, provision
    from .recovery import evaluation_work, receipt_row, save_receipt

    configs = provision(at=at)
    deployment = locked_deployment()
    config = configs[0] if configs else None
    placed = rejected = pending = 0
    evaluations = []
    if config:
        for state in config.execution_states.filter(
            status=CapitalExecutionState.Status.PENDING_CAPACITY
        ).select_related(
            "execution_basis__capture_work_item__run",
            "execution_basis__capture_work_item__match",
            "execution_basis__originating_decision__prediction",
            "execution_basis__selected_odds_observation",
        ):
            outcome = place_candidate(
                config.pk, _candidate_from_basis(state.execution_basis), at=at
            )
            placed += int(outcome == "PLACED")
            rejected += int(outcome == "NOT_PLACED")
    for work in evaluation_work(deployment, capture_run_id=capture_run_id, at=at):
        evaluation_at = max(clock.effective_now(planning_at=at), work.run.completed_at)
        receipt = CapitalEvaluation.objects.filter(
            deployment=deployment, work=work
        ).first()
        if receipt and not receipt.retryable:
            evaluations.append(receipt_row(receipt, reused=True))
            continue
        existing = (
            config.execution_states.filter(match=work.match)
            .select_related("execution_basis__originating_decision__experiment")
            .first()
            if config
            else None
        )
        if existing:
            decision = (
                existing.execution_basis.originating_decision
                if existing.execution_basis_id
                else None
            )
            known_reason = existing.non_placement_reason
            known_status = (
                (
                    "NO_BET"
                    if known_reason == "NO_BET"
                    else (
                        "MISSED_WINDOW"
                        if known_reason
                        in {"MISSED_EXECUTION_WINDOW", "EXPIRED_CAPACITY"}
                        else (
                            "BLOCKED"
                            if known_reason
                            in {
                                "STRATEGY_STOPPED",
                                "STRATEGY_DRAINING",
                                "PRE_GLOBAL",
                                "OPERATIONAL_DEPLETION",
                                "AWAITING_FINAL_OPEN_SETTLEMENT",
                                "AUTHORITY_EVIDENCE_MISMATCH",
                            }
                            else "UNAVAILABLE"
                        )
                    )
                )
                if known_reason
                else "DUPLICATE"
            )
            evaluations.append(
                save_receipt(
                    deployment,
                    work,
                    status=known_status,
                    reason=known_reason or "MATCH_ALREADY_CLASSIFIED",
                    at=evaluation_at,
                    experiment=decision.experiment if decision else None,
                    details={"execution_state_id": existing.pk},
                )
            )
            continue
        try:
            with transaction.atomic():
                already_evaluated = PredictionExperiment.objects.filter(
                    logical_identity=f"fs022:{deployment.cutover_id}:{work.logical_identity}"
                ).exists()
                decision, reason = evaluate_work(work, at=evaluation_at)
                if reason:
                    if reason == "MISSED_EXECUTION_WINDOW":
                        status = "MISSED_WINDOW"
                    elif reason in {
                        "STRATEGY_DRAINING",
                        "STRATEGY_STOPPED",
                        "AWAITING_FINAL_OPEN_SETTLEMENT",
                        "OPERATIONAL_DEPLETION",
                        "PRE_GLOBAL",
                    }:
                        status = "BLOCKED"
                    else:
                        status = "UNAVAILABLE"
                    diagnostics = (
                        live_selection(work).diagnostics
                        if reason == "INPUT_QUOTES_MISSING"
                        else {}
                    )
                    if config:
                        _, created = _terminal_state(
                            config,
                            work.match,
                            reason,
                            evaluation_at,
                            diagnostics=dict(
                                capture_work_item_id=work.pk, **diagnostics
                            ),
                        )
                        rejected += int(created)
                    evaluations.append(
                        save_receipt(
                            deployment,
                            work,
                            status=status,
                            reason=reason,
                            at=evaluation_at,
                            details=diagnostics,
                        )
                    )
                    continue
                outcome = place_candidate(
                    config.pk, frozen_candidate(work, decision), at=evaluation_at
                )
                placed += int(outcome == "PLACED")
                rejected += int(outcome == "NOT_PLACED")
                pending += int(outcome == "PENDING_CAPACITY")
                # Creation and its receipt share this transaction; a crash cannot
                # leave half an evaluation that has to be fabricated on restart.
                evaluations.append(
                    save_receipt(
                        deployment,
                        work,
                        status="NO_BET" if decision.action == "NO_BET" else "COMPLETED",
                        reason=decision.reason,
                        at=evaluation_at,
                        experiment=decision.experiment,
                        details=dict(
                            created_experiment=not already_evaluated,
                            selected_observation_id=decision.selected_odds_observation_id,
                            selected_price=(
                                str(decision.selected_price)
                                if decision.selected_price is not None
                                else None
                            ),
                            placement_outcome=outcome,
                            **decision.prediction.diagnostics,
                        ),
                    )
                )
        except Exception as error:
            from football.observability.events import sanitize_text

            evaluations.append(
                save_receipt(
                    deployment,
                    work,
                    status="FAILED",
                    reason="EVALUATION_ERROR",
                    at=evaluation_at,
                    retryable=True,
                    details={"error": sanitize_text(error, 500)},
                )
            )
    failures = tuple(
        row["details"]["error"] for row in evaluations if row["status"] == "FAILED"
    )
    return RuntimeResult(
        (
            "DEGRADED"
            if failures
            else ("PRODUCED" if placed or rejected or pending else "NO_WORK")
        ),
        configs=len(configs),
        config_ids=tuple(c.pk for c in configs),
        placed=placed,
        not_placed=rejected,
        pending_capacity=pending,
        evaluations=tuple(evaluations),
        errors=failures,
    )
