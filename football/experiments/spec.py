"""A deeply immutable snapshot of the approved FS-018 contract."""

import platform
import subprocess
from dataclasses import dataclass
from importlib.metadata import version
from pathlib import Path

from football.prediction.readiness import active_profile
from football.prediction.service import latest_selected_config

from .mapping import MAPPING_POLICY
from .storage import atomic_json, canonical, identity, instant, lock, read_json, roots

MODELS = {
    "DIXON_COLES": "fs011-dixon-coles-v2",
    "INDEPENDENT_POISSON": "fs003-independent-poisson-v1",
    "ELO_MULTINOMIAL_LOGIT": "fs003-elo-multinomial-logit-v1",
    "MARKET_CONSENSUS": "fs013-market-consensus-v2",
}
TOURNAMENTS = {
    1270: 34,
    1272: 325,
    1273: 17,
    1274: 35,
    1275: 23,
    1276: 37,
    1277: 238,
    1278: 8,
    1325: 52,
    1459: 155,
}
BOOKMAKERS = ("pinnacle", "bet365", "unibet")
PROFILE = "ODDSPAPI_RECONSTRUCTED_T30_V1"
CONTRACT = {
    "spec_version": "fs018-v1",
    "artifact_schema_version": "fs018-artifacts-v1",
    "mapping_policy": MAPPING_POLICY,
    "changed_layer": "Prediction",
    "models": MODELS,
    "evidence_profile": PROFILE,
    "evidence_class": "HISTORICAL_RESEARCH",
    "bookmakers": list(BOOKMAKERS),
    "minimum_books": 2,
    "de_vig_method": "multiplicative",
    "consensus_method": "equal_weight_arithmetic_mean",
    "t30": "latest-active-valid-createdAt<=canonical-kickoff-minus-30m",
    "sporting_replay": "expanding-strict-prior-America/Lima-day",
    "cohorts": {"primary": "COMMON", "secondary": "NATURAL"},
    "primary_metric": "equal-league-COMMON-log-loss",
    "metrics": [
        "log_loss",
        "multiclass_brier",
        "rps",
        "accuracy",
        "calibration",
        "coverage",
        "failure_unavailability",
    ],
    "bootstrap": {
        "block": "Competition×Lima-ISO-week",
        "replicates": 5000,
        "seed": 18092026,
        "interval": 0.95,
        "stratified": True,
    },
    "selection_rule": "coverage,league-time-stability,failures,dependencies,resources,identity-v1",
    "stability_rule": "lexicographic-population-SD-NATURAL-league-logloss-then-Lima-week-logloss",
    "guardrail_rule": "clear-winner-must-not-lose-coverage-stability-or-failure-count",
}


@dataclass(frozen=True)
class ExperimentSpec:
    # JSON string deliberately prevents mutation through nested dicts/lists.
    serialized: str

    def __post_init__(self):
        import json

        data = json.loads(self.serialized)
        if any(data.get(key) != value for key, value in CONTRACT.items()):
            raise ValueError("Frozen methodology mismatch")
        ids = data["competition_ids"]
        if not ids or ids != sorted(set(ids)) or set(ids) - TOURNAMENTS.keys():
            raise ValueError("Invalid competition scope")
        if data["tournament_map"] != {str(i): TOURNAMENTS[i] for i in ids}:
            raise ValueError("Frozen tournament mapping mismatch")
        if not instant(data["window_start"]) < instant(data["data_cutoff"]):
            raise ValueError("Invalid frozen window")
        if instant(data["window_start"]).isoformat() != "2026-01-01T00:00:00+00:00":
            raise ValueError("FS-018 window must start at 2026-01-01 UTC")
        if set(data["configs"]) != {str(i) for i in ids}:
            raise ValueError("Missing CURRENT config")
        acquisition = data.get("acquisition", {"mode": "STANDARD"})
        if acquisition.get("mode") not in {"STANDARD", "RECOVERY_V1"}:
            raise ValueError("Invalid acquisition mode")
        if acquisition["mode"] == "RECOVERY_V1" and not all(
            acquisition.get(k) for k in ("source_spec_id", "source_run_id")
        ):
            raise ValueError("Missing recovery lineage")
        if acquisition["mode"] == "RECOVERY_V1" and set(ids) != set(TOURNAMENTS):
            raise ValueError("Recovery requires all ten competitions")
        for config in data["configs"].values():
            if config["identity"] != identity(config["selected"]):
                raise ValueError("Invalid config identity")
            if set(config["executable"]) != MODELS.keys() - {"MARKET_CONSENSUS"}:
                raise ValueError("Missing frozen executable config")
            for code in MODELS.keys() - {"MARKET_CONSENSUS"}:
                if code.lower() not in config["selected"]:
                    raise ValueError("Missing sporting config")
                if config["executable"][code] != executable_config(
                    code, config["selected"][code.lower()]
                ):
                    raise ValueError("Frozen executable config mismatch")
        object.__setattr__(self, "serialized", canonical(data))

    @property
    def data(self):
        import json

        return json.loads(self.serialized)

    @property
    def id(self):
        return identity(self.data)

    def save(self, path):
        with lock(path.with_suffix(".lock")):
            if path.exists() and read_json(path) != self.data:
                raise ValueError("Refusing to overwrite frozen spec")
            atomic_json(path, self.data)

    @classmethod
    def load(cls, path):
        return cls(canonical(read_json(path)))


def executable_config(code, selected):
    """Keep CURRENT selection metadata intact; extract only adapter inputs."""
    if selected.get("status") == "UNAVAILABLE":
        return {"status": "UNAVAILABLE", "reason": selected["reason"]}
    keys = {
        "DIXON_COLES": ("xi",),
        "INDEPENDENT_POISSON": ("xi",),
        "ELO_MULTINOMIAL_LOGIT": ("k", "C"),
    }[code]
    return {key: selected[key] for key in keys}


def _runtime_identity():
    try:
        revision = subprocess.check_output(
            ["git", "rev-parse", "HEAD"], text=True, stderr=subprocess.DEVNULL
        ).strip()
        dirty = bool(
            subprocess.check_output(
                ["git", "status", "--porcelain"], text=True, stderr=subprocess.DEVNULL
            ).strip()
        )
    except (OSError, subprocess.CalledProcessError):
        revision, dirty = "unavailable", None
    package = Path(__file__).resolve().parents[1]
    sources = [
        path
        for directory in (package / "experiments", package / "prediction")
        for path in directory.glob("*.py")
    ]
    sources += [package / "providers" / "oddspapi.py", package / "reconciliation.py"]
    code_identity = identity(
        {str(path.relative_to(package)): path.read_text() for path in sorted(sources)}
    )
    return {
        "name": "finsport-dev",
        "python": platform.python_version(),
        "git_revision": revision,
        "dirty": dirty,
        "code_identity": code_identity,
        "dependencies": {
            name: version(name)
            for name in ("penaltyblog", "numpy", "scikit-learn", "Django")
        },
    }


def freeze_recovery_spec(source_path):
    """Freeze a new policy identity while retaining the original scientific inputs."""
    source = read_json(source_path)
    source_id = identity(source)
    source_run_id = identity({"spec_id": source_id, "pilot": False})
    checkpoint = roots()[1] / source_run_id / "backfill.json"
    if not checkpoint.exists():
        raise ValueError("RECOVERY_SOURCE_CHECKPOINT_REQUIRED")
    state = read_json(checkpoint)
    if state["spec_id"] != source_id or state["status"] not in {"COMPLETE", "PARTIAL"}:
        raise ValueError("RECOVERY_SOURCE_NOT_TERMINAL")
    if set(source["competition_ids"]) != set(TOURNAMENTS):
        raise ValueError("RECOVERY_REQUIRES_FULL_SCOPE")
    for key, value in CONTRACT.items():
        if key != "mapping_policy" and source.get(key) != value:
            raise ValueError("RECOVERY_SCIENTIFIC_CONTRACT_MISMATCH")
    return ExperimentSpec(
        canonical(
            {
                **source,
                **CONTRACT,
                "runtime": _runtime_identity(),
                "acquisition": {
                    "mode": "RECOVERY_V1",
                    "source_spec_id": source_id,
                    "source_run_id": source_run_id,
                },
            }
        )
    )


def freeze_spec(competitions, cutoff):
    from .replay import adapter_for

    configs = {}
    for competition in sorted(competitions, key=lambda c: c.pk):
        selected, source = latest_selected_config(competition)
        for code in MODELS.keys() - {"MARKET_CONSENSUS"}:
            config = selected[code.lower()]
            execution = executable_config(code, config)
            if execution.get("status") == "UNAVAILABLE":
                continue
            adapter = adapter_for(code, execution)
            if any(adapter.config.get(k) != v for k, v in execution.items()):
                raise ValueError("CURRENT_CONFIG_NOT_REPRODUCIBLE_BY_ADAPTER")
        profiles = {}
        for code in MODELS.keys() - {"MARKET_CONSENSUS"}:
            profile = active_profile(competition, model_code=code)
            profiles[code] = (
                {
                    "id": profile.pk,
                    "version": profile.version,
                    "model_version": profile.model_version,
                    "model_config": profile.model_config,
                    "approved": profile.approved,
                    "requirements": profile.requirements,
                    "basis_identity": profile.basis_identity,
                }
                if profile
                else None
            )
        configs[str(competition.pk)] = {
            "selected": selected,
            "executable": {
                code: executable_config(code, selected[code.lower()])
                for code in MODELS.keys() - {"MARKET_CONSENSUS"}
            },
            "source": source,
            "identity": identity(selected),
            "readiness_profiles": profiles,
        }
    ids = sorted(map(int, configs))
    return ExperimentSpec(
        canonical(
            {
                **CONTRACT,
                "competition_ids": ids,
                "configs": configs,
                "tournament_map": {str(i): TOURNAMENTS[i] for i in ids},
                "window_start": "2026-01-01T00:00:00+00:00",
                "data_cutoff": instant(cutoff).isoformat(),
                "runtime": _runtime_identity(),
                "acquisition": {"mode": "STANDARD"},
            }
        )
    )
