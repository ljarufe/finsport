"""Manual, resumable acquisition. Durable state is private filesystem JSON."""

import logging
import math
from collections import Counter

from football.models import Competition

from .mapping import map_fixture
from .market import reconstruct
from .provider import OddsPapiClient, ProviderError, empty_traffic_audit
from .spec import ExperimentSpec
from .storage import atomic_json, identity, instant, lock, read_json, require_dev, roots

TERMINAL_FIXTURES = {"UNMATCHED", "AMBIGUOUS", "NO_USABLE_T30", "RECONSTRUCTED"}
logger = logging.getLogger(__name__)


def audit_snapshot(state, directory):
    """Derive fixture/evidence counts from checkpoints; retain physical attempts."""
    traffic_path = directory / "traffic-audit.json"
    traffic = (
        read_json(traffic_path) if traffic_path.exists() else empty_traffic_audit()
    )
    statuses, acquisitions, books, ages = Counter(), Counter(), Counter(), []
    for league in state["leagues"].values():
        for item in league["fixtures"].values():
            statuses[item["status"]] += 1
            if item.get("acquisition"):
                acquisitions[item["acquisition"]] += 1
            evidence = item.get("evidence")
            if evidence:
                books[str(evidence["book_count"])] += 1
                ages.extend(
                    leg["quote_age_seconds"]
                    for book in evidence["books"].values()
                    for leg in book["legs"]
                )
    ages.sort()
    return {
        "physical_calls": traffic["physical_calls"],
        "http_status_counts": traffic["http_status_counts"],
        "http_429": traffic["http_429"],
        "network_errors": traffic["network_errors"],
        "retries": traffic["retries"],
        "in_flight": traffic["in_flight"],
        "cache_hits": traffic["cache_hits"],
        "matched": statuses["RECONSTRUCTED"]
        + statuses["NO_USABLE_T30"]
        + statuses["MATCHED"]
        + statuses["CACHED"]
        + statuses["FETCHED"]
        + sum(
            item.get("mapping", {}).get("status") == "MATCHED"
            for league in state["leagues"].values()
            for item in league["fixtures"].values()
            if item["status"] == "FAILED"
        ),
        "unmatched": statuses["UNMATCHED"],
        "ambiguous": statuses["AMBIGUOUS"],
        "cached": acquisitions["CACHED"],
        "fetched": acquisitions["FETCHED"],
        "skipped": statuses["UNMATCHED"] + statuses["AMBIGUOUS"],
        "fixture_status_counts": dict(sorted(statuses.items())),
        "complete_book_counts": dict(sorted(books.items())),
        "quote_age_seconds": {
            "count": len(ages),
            "min": ages[0] if ages else None,
            "median": (
                (ages[(len(ages) - 1) // 2] + ages[len(ages) // 2]) / 2
                if ages
                else None
            ),
            "p95": ages[max(0, math.ceil(0.95 * len(ages)) - 1)] if ages else None,
            "max": ages[-1] if ages else None,
        },
    }


def backfill(spec, *, client=None, pilot=False):
    require_dev()
    data = spec.data
    if pilot and data["competition_ids"] != [1278]:
        raise ValueError("Pilot requires a La Liga-only spec")
    recovery = data.get("acquisition", {}).get("mode") == "RECOVERY_V1"
    if recovery and pilot:
        raise ValueError("Recovery requires full scope")
    source = None
    if recovery:
        source_run_id = data["acquisition"]["source_run_id"]
        source = read_json(roots()[1] / source_run_id / "backfill.json")
        if (
            source["run_id"] != source_run_id
            or source["spec_id"] != data["acquisition"]["source_spec_id"]
        ):
            raise ValueError("RECOVERY_SOURCE_MISMATCH")
    run_id = identity({"spec_id": spec.id, "pilot": pilot})
    directory = roots()[1] / run_id
    client = client or OddsPapiClient(audit_path=directory / "traffic-audit.json")
    path = directory / "backfill.json"
    with lock(directory / "backfill.lock"):
        state = (
            read_json(path)
            if path.exists()
            else {
                "run_id": run_id,
                "spec_id": spec.id,
                "pilot": pilot,
                "recovery_source_run_id": source_run_id if recovery else None,
                "status": "PENDING",
                "leagues": {},
            }
        )

        def checkpoint():
            state["audit"] = audit_snapshot(state, directory)
            atomic_json(path, state)

        checkpoint()
        state["status"] = "RUNNING"
        checkpoint()
        try:
            for competition_id in data["competition_ids"]:
                key = str(competition_id)
                league = state["leagues"].setdefault(
                    key, {"status": "PENDING", "fixtures": {}}
                )
                try:
                    competition = Competition.objects.get(pk=competition_id)
                    if "discovery_hash" not in league:
                        fixture_args = (
                            data["tournament_map"][key],
                            data["window_start"],
                            data["data_cutoff"],
                        )
                        fixtures, acquisition = (
                            client.fixtures(*fixture_args, refresh_revision=spec.id)
                            if recovery
                            else client.fixtures(*fixture_args)
                        )
                        if pilot:
                            fixtures = [
                                f
                                for f in fixtures
                                if f["fixture_id"] == "id1000000872478570"
                            ]
                            if not fixtures:
                                raise ProviderError("PILOT_FIXTURE_NOT_DISCOVERED")
                        discovery_fields = {}
                        if recovery:
                            refreshed_fixtures = list(fixtures)
                            source_fixtures = (
                                source["leagues"].get(key, {}).get("fixtures", {})
                            )
                            fixture_by_id = {f["fixture_id"]: f for f in fixtures}
                            for fixture_id, previous in source_fixtures.items():
                                if fixture_id in fixture_by_id:
                                    continue
                                previous_fixture = previous.get("fixture")
                                if not previous_fixture:
                                    raise ProviderError(
                                        "RECOVERY_SOURCE_FIXTURE_MISSING"
                                    )
                                fixture_by_id[fixture_id] = previous_fixture
                            fixtures = [
                                fixture_by_id[fixture_id]
                                for fixture_id in sorted(fixture_by_id)
                            ]
                            discovery_fields = {
                                "refreshed_discovery_hash": identity(
                                    refreshed_fixtures
                                ),
                                "refreshed_discovered_count": len(refreshed_fixtures),
                                "source_discovered_count": len(source_fixtures),
                            }
                        discovery_hash, discovered_count = identity(fixtures), len(
                            fixtures
                        )
                        league.update(
                            discovery_hash=discovery_hash,
                            discovery_state=acquisition,
                            discovery_revision=spec.id if recovery else None,
                            discovered_count=discovered_count,
                            **discovery_fields,
                        )
                        league["fixtures"] = {
                            f["fixture_id"]: {"fixture": f, "status": "DISCOVERED"}
                            for f in fixtures
                        }
                        checkpoint()
                    league["status"] = "RUNNING"
                    league.pop("reason", None)
                    for fixture_id, item in sorted(league["fixtures"].items()):
                        if item["status"] in TERMINAL_FIXTURES:
                            continue
                        try:
                            previous = (
                                source["leagues"]
                                .get(key, {})
                                .get("fixtures", {})
                                .get(fixture_id)
                                if recovery
                                else None
                            )
                            refresh_kind = (
                                previous["status"]
                                if previous
                                and previous["status"] in {"FAILED", "NO_USABLE_T30"}
                                else None
                            )
                            if refresh_kind and item.get("recovery_attempted"):
                                has_cache = getattr(
                                    client, "has_historical_cache", None
                                )
                                if not has_cache or not has_cache(
                                    fixture_id, refresh_revision=spec.id
                                ):
                                    item.update(
                                        status="FAILED",
                                        reason="RECOVERY_REFRESH_ALREADY_ATTEMPTED",
                                    )
                                    checkpoint()
                                    continue
                            mapping = item.get("mapping") or map_fixture(
                                competition, item["fixture"]
                            )
                            item["mapping"] = mapping
                            item["status"] = mapping["status"]
                            checkpoint()
                            if mapping["status"] != "MATCHED":
                                continue
                            if previous and previous["status"] == "RECONSTRUCTED":
                                has_cache = getattr(
                                    client, "has_historical_cache", None
                                )
                                if has_cache and not has_cache(fixture_id):
                                    raise ProviderError("MISSING_SUCCESSFUL_RAW_CACHE")
                            if refresh_kind:
                                item.update(
                                    recovery_refresh_kind=refresh_kind,
                                    recovery_attempted=True,
                                )
                                checkpoint()
                                payload, acquisition = client.historical(
                                    fixture_id, refresh_revision=spec.id
                                )
                            else:
                                payload, acquisition = client.historical(fixture_id)
                            item.update(status=acquisition, acquisition=acquisition)
                            checkpoint()
                            evidence = reconstruct(
                                payload,
                                fixture_id=fixture_id,
                                match_id=mapping["match_id"],
                                kickoff=instant(mapping["canonical_kickoff"]),
                            )
                            item.update(
                                evidence=evidence,
                                status=(
                                    "RECONSTRUCTED"
                                    if evidence["status"] == "PRODUCED"
                                    else "NO_USABLE_T30"
                                ),
                            )
                            item.pop("reason", None)
                        except Exception as error:
                            item.update(status="FAILED", reason=_safe_reason(error))
                            if _contradiction(error):
                                raise
                        finally:
                            league["counts"] = dict(
                                Counter(
                                    i["status"] for i in league["fixtures"].values()
                                )
                            )
                            checkpoint()
                            logger.info(
                                "FS018 run=%s competition=%s fixture=%s status=%s acquisition=%s books=%s",
                                run_id,
                                key,
                                fixture_id,
                                item["status"],
                                item.get("acquisition", ""),
                                item.get("evidence", {}).get("book_count", 0),
                            )
                    league["counts"] = dict(
                        Counter(i["status"] for i in league["fixtures"].values())
                    )
                    league["status"] = (
                        "PARTIAL" if league["counts"].get("FAILED") else "COMPLETE"
                    )
                except Exception as error:
                    league.update(status="FAILED", reason=_safe_reason(error))
                    if _contradiction(error):
                        raise
                finally:
                    checkpoint()
            statuses = [league["status"] for league in state["leagues"].values()]
            state["status"] = (
                "COMPLETE"
                if all(s == "COMPLETE" for s in statuses)
                else "FAILED" if all(s == "FAILED" for s in statuses) else "PARTIAL"
            )
        except BaseException:
            state["status"] = "FAILED"
            checkpoint()
            raise
        checkpoint()
    return {
        "run_id": run_id,
        "status": state["status"],
        "checkpoint": str(path),
        "audit": state["audit"],
        "leagues": {
            k: {"status": v["status"], "counts": v.get("counts", {})}
            for k, v in state["leagues"].items()
        },
    }


def _safe_reason(error):
    return str(error) if isinstance(error, ProviderError) else type(error).__name__


def _contradiction(error):
    return (
        isinstance(error, ProviderError)
        and (
            "SHAPE_MISMATCH" in str(error)
            or str(error)
            in {
                "ACCESS_DENIED",
                "DUPLICATE_FIXTURE_ID",
                "RATE_LIMITED",
                "NETWORK_ERROR",
            }
        )
        or isinstance(error, ValueError)
        and "HISTORICAL_" in str(error)
    )


def execute_backfill(spec_path, *, pilot=False):
    from .storage import local_spec_path

    require_dev()
    return backfill(ExperimentSpec.load(local_spec_path(spec_path)), pilot=pilot)
