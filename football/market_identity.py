"""Governed raw-provider mappings for Market Consensus statistical identity."""

from django.db import transaction

from football.models import (
    BookmakerCanonicalRef,
    CanonicalBookmaker,
    CanonicalOddsMarket,
    OddsMarketCanonicalRef,
    ReconciliationStatus,
)

MAPPING_VERSION = "fs013-governed-v1"
CANONICAL_1X2_CODE = "1x2"

# Names are descriptive only. The source/external-id tuple is the authority.
BOOKMAKER_MAPPINGS = {
    ("api_football", "1"): ("10bet", "10Bet"),
    ("api_football", "2"): ("marathonbet", "Marathonbet"),
    ("api_football", "3"): ("betfair", "Betfair"),
    ("api_football", "4"): ("pinnacle", "Pinnacle"),
    ("api_football", "5"): ("sbo", "SBO"),
    ("api_football", "7"): ("william-hill", "William Hill"),
    ("api_football", "8"): ("bet365", "Bet365"),
    ("api_football", "9"): ("dafabet", "Dafabet"),
    ("api_football", "11"): ("1xbet", "1xBet"),
    ("api_football", "16"): ("unibet", "Unibet"),
    ("api_football", "21"): ("888sport", "888Sport"),
    ("api_football", "32"): ("betano", "Betano"),
    ("api_football", "34"): ("superbet", "Superbet"),
    ("api_football", "36"): ("betvictor", "BetVictor"),
    ("inkabet", "inkabet"): ("inkabet", "Inkabet"),
}

MARKET_MAPPINGS = {
    ("api_football", "1"): (CANONICAL_1X2_CODE, "1X2"),
    ("inkabet", "MW3W"): (CANONICAL_1X2_CODE, "1X2"),
}


def _mapping_key(raw):
    return raw.source.code, str(raw.external_id)


@transaction.atomic
def reconcile_bookmaker_identity(bookmaker):
    mapping = BOOKMAKER_MAPPINGS.get(_mapping_key(bookmaker))
    defaults = {
        "mapping_version": MAPPING_VERSION,
        "context": {
            "authority": "governed_source_external_id_registry",
            "raw_name": bookmaker.name,
        },
    }
    if mapping is None:
        ref, _ = BookmakerCanonicalRef.objects.get_or_create(
            bookmaker=bookmaker,
            defaults={
                **defaults,
                "reconciliation_status": ReconciliationStatus.PENDING,
                "reason": "UNMAPPED_SOURCE_EXTERNAL_ID",
            },
        )
        return ref
    code, name = mapping
    canonical, _ = CanonicalBookmaker.objects.get_or_create(
        code=code, defaults={"name": name}
    )
    ref, _ = BookmakerCanonicalRef.objects.update_or_create(
        bookmaker=bookmaker,
        defaults={
            **defaults,
            "canonical_bookmaker": canonical,
            "reconciliation_status": ReconciliationStatus.RESOLVED,
            "reason": "GOVERNED_MAPPING",
        },
    )
    return ref


@transaction.atomic
def reconcile_market_identity(market):
    mapping = MARKET_MAPPINGS.get(_mapping_key(market))
    defaults = {
        "mapping_version": MAPPING_VERSION,
        "context": {
            "authority": "governed_source_external_id_registry",
            "raw_name": market.name,
        },
    }
    if mapping is None:
        ref, _ = OddsMarketCanonicalRef.objects.get_or_create(
            market=market,
            defaults={
                **defaults,
                "reconciliation_status": ReconciliationStatus.PENDING,
                "reason": "UNMAPPED_SOURCE_EXTERNAL_ID",
            },
        )
        return ref
    code, name = mapping
    canonical, _ = CanonicalOddsMarket.objects.get_or_create(
        code=code, defaults={"name": name}
    )
    ref, _ = OddsMarketCanonicalRef.objects.update_or_create(
        market=market,
        defaults={
            **defaults,
            "canonical_market": canonical,
            "reconciliation_status": ReconciliationStatus.RESOLVED,
            "reason": "GOVERNED_MAPPING",
        },
    )
    return ref
