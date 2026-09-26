"""Authenticate retained V2R, then compare synthetic causal events with CURRENT."""

import importlib.util
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from pathlib import Path

from .capital_events import Opportunity, run_event_path
from .capital_runner import CANDIDATES
from .integrated_inputs import require


def compare_reference(path, base):
    # Reference is locally supplied by the maintainer. The executable oracle is
    # the 21-cell event/request/state comparison below, not a pinned file SHA.
    require(Path(path).is_file(), "V2R_REFERENCE_MISSING")
    module_spec = importlib.util.spec_from_file_location(
        "fs021_authenticated_v2r", path
    )
    ref = importlib.util.module_from_spec(module_spec)
    module_spec.loader.exec_module(ref)
    ref._ensure_policy_import(Path(base))
    at = datetime(2026, 1, 12, 20, tzinfo=timezone.utc)
    cells = []
    for index, capital in enumerate(CANDIDATES):
        for lag in (120, 130, 150):
            rows, opportunities = [], []
            for i in range(24):
                kickoff = at + timedelta(minutes=(i // 12) * 180 + i % 3)
                execution = kickoff - timedelta(minutes=30)
                probability = "0.1" if i == 11 else "0.6"
                action = "NO_BET" if i == 23 else "BET"
                row = dict(
                    candidate_id="SYNTHETIC",
                    candidate_index=0,
                    match_id=i + 1,
                    competition_id=1,
                    kickoff=kickoff.isoformat(),
                    execution_at=execution.isoformat(),
                    action=action,
                    selected_outcome="HOME" if action == "BET" else None,
                    model_probability=probability,
                    selected_price="2",
                    price_evidence_identity=None,
                    provider_fixture_id=None,
                    fs018_evidence_id=None,
                    raw_cache_hash=None,
                )
                rows.append(row)
                opportunities.append(
                    Opportunity(
                        str(i + 1),
                        i + 1,
                        1,
                        kickoff,
                        execution,
                        action,
                        row["selected_outcome"],
                        ref.synthetic_outcome(i + 1),
                        Decimal("2") if action == "BET" else None,
                        Decimal(probability) if action == "BET" else None,
                    )
                )
            events = []

            def recorder():
                def record(kind, payload):
                    events.append(dict(kind=kind, **ref._normalize(payload)))

                return record, lambda: ("SYNTHETIC", len(events))

            ref._event_digest_recorder = recorder
            arm = dict(
                capital_code=capital.code,
                config=capital.data()["config"],
                max_lanes=capital.max_lanes,
                pd_candidate_id="SYNTHETIC",
                integrated_index=index,
                integrated_id="SYNTHETIC",
            )
            reference = ref.run_arm(arm, rows, lag)
            current = run_event_path(opportunities, capital, lag, trace=True)
            # Compare order, request arithmetic, time and state, not only end equity.
            kinds = {
                "POLICY_REQUEST",
                "PLACEMENT",
                "SETTLEMENT",
                "PENDING_RETRY",
                "ZERO_STAKE",
                "POLICY_TERMINATION",
            }
            a = [
                (e["kind"], e["at"], str(e["match_id"]))
                for e in events
                if e["kind"] in kinds
            ]
            b = [
                (e["kind"], e["at"], e["opportunity"])
                for e in current["ledger"]
                if e["kind"] in kinds
            ]
            require(a == b, f"V2R_CAUSAL_EVENTS:{index}:{lag}")
            causal_count = len(a)
            requests = [e for e in events if e["kind"] == "POLICY_REQUEST"]
            product_requests = [
                e for e in current["ledger"] if e["kind"] == "POLICY_REQUEST"
            ]
            for a, b in zip(requests, product_requests, strict=True):
                require(
                    a["request"]["requested"] == b["request"]["requested"]
                    and a["request"]["applied"] == b["request"]["applied"]
                    and a["state"] == b["policy_state"],
                    "V2R_REQUEST_STATE",
                )
            require(
                reference["final_open_count"] == reference["final_pending_count"] == 0,
                "V2R_INCOMPLETE",
            )
            cells.append(
                dict(
                    capital=capital.code,
                    lag=lag,
                    causal_events=causal_count,
                    status="PASS",
                )
            )
    return dict(reference=str(Path(path).name), cells=cells, status="PASS")
