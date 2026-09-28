"""Material FS-021 selection binding, retained locally for ordinary restarts."""

import hashlib
import json
from pathlib import Path

from django.conf import settings

from football.capital.policies import POLICY_VERSIONS
from football.prediction.constants import (
    MARKET_CONSENSUS_VERSION,
    SELECTIVE_CONFIDENCE_VERSION,
)

EXECUTION_ID = "fcd8ce16950e02589d25ddf6bcd9953cce2e663f2f14c63e7f8a1f4487d97372"
BINDING_SHA = "fa6e9f95d8605b66ecb2d4d4acc7f3488183a77ce4f3742c44995670f10275ec"
BINDING_PATH = f"docs/experiments/FS-021/{EXECUTION_ID}/prospective_binding_v1.json"


class AuthorityError(RuntimeError):
    pass


def resolve_authority(*, base=None):
    root = Path(base or settings.BASE_DIR)
    try:
        raw = (root / BINDING_PATH).read_bytes()
        if hashlib.sha256(raw).hexdigest() != BINDING_SHA:
            raise AuthorityError("FS022_BINDING_INTEGRITY")
        binding = json.loads(raw)
        index = json.loads(
            (
                root / f"docs/experiments/FS-021/{EXECUTION_ID}/economic_v1_1.json"
            ).read_text()
        )
        original = json.loads(
            (
                root / f"docs/experiments/FS-021/{EXECUTION_ID}/original_v1.json"
            ).read_text()
        )
    except (OSError, ValueError) as error:
        raise AuthorityError("FS022_AUTHORITY_INACCESSIBLE") from error
    try:
        pd = binding["winner_candidate"]["prediction_decision"]
        capital = binding["winner_candidate"]["capital"]
        if not (
            binding["winner"] == index["winner"] == 209
            and binding["execution_id"] == index["execution_id"] == EXECUTION_ID
            and binding["manifest_sha256"] == index["manifest_sha256"]
            and binding["selector_spec_sha"] == index["selector_spec_sha"]
            and original["selection_index"] == 60
            and original["activation"] is False
            and index["activation"] is False
            and binding["activation"]
            == {"automatic_operational_routing": False, "real_betting": False}
            and binding["prospective_prediction_config_identity"]
            == hashlib.sha256(
                json.dumps(
                    binding["prospective_prediction_effective_config"],
                    sort_keys=True,
                    separators=(",", ":"),
                ).encode()
            ).hexdigest()
            and binding["mode"] == "PRACTICAL_BASELINE_SIMULATION_ONLY"
            and pd["prediction_version"] == MARKET_CONSENSUS_VERSION
            and pd["decision_policy_version"] == SELECTIVE_CONFIDENCE_VERSION
            and capital["version"] == POLICY_VERSIONS["FRACTIONAL_KELLY"]
        ):
            raise AuthorityError("FS022_AUTHORITY_CONTRACT_DRIFT")
    except (KeyError, TypeError) as error:
        raise AuthorityError("FS022_AUTHORITY_CONTRACT_DRIFT") from error
    return binding
