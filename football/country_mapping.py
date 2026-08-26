import re
import unicodedata

from django.utils.translation import override
from django_countries import countries

PROVIDER_COUNTRY_OVERRIDES = {
    "congo dr": "CD",
    "crimea": "",
}


def normalized_text(value):
    decomposed = unicodedata.normalize("NFKD", str(value or ""))
    ascii_value = "".join(
        character for character in decomposed if not unicodedata.combining(character)
    )
    return " ".join(re.sub(r"[^a-z0-9]+", " ", ascii_value.casefold()).split())


def country_code(name="", code=""):
    normalized_name = normalized_text(name)

    if normalized_name in PROVIDER_COUNTRY_OVERRIDES:
        return PROVIDER_COUNTRY_OVERRIDES[normalized_name]

    for language in ("en", "es"):
        matched = countries.by_name(name, language=language) if name else ""
        if matched:
            return matched

    normalized_code = _normalized_library_country_code(name)
    if normalized_code:
        return normalized_code

    provider_code = str(code or "").strip().upper()
    return provider_code if provider_code in countries else ""


def country_name_prefixes(country):
    if not country:
        return ()

    names = set()

    for language in ("en", "es"):
        with override(language):
            names.add(normalized_text(countries.name(country.code)))

    for alias, code in PROVIDER_COUNTRY_OVERRIDES.items():
        if code and code == country.code:
            names.add(alias)

    return tuple(name for name in names if name)


def _normalized_library_country_code(value):
    target = normalized_text(value)
    if not target:
        return ""

    for language in ("en", "es"):
        with override(language):
            matches = {
                code for code, name in countries if normalized_text(name) == target
            }

        if len(matches) == 1:
            return matches.pop()

    return ""
