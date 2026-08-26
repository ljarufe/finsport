import pytest
from django_countries.fields import Country

from football.country_mapping import country_code, country_name_prefixes


@pytest.mark.parametrize(
    ("name", "provider_code", "expected"),
    [
        ("Germany", "DE", "DE"),
        ("Alemania", "DE", "DE"),
        ("Spain", "ES", "ES"),
        ("España", "ES", "ES"),
        ("espana", "", "ES"),
        ("Brazil", "BR", "BR"),
        ("Brasil", "BR", "BR"),
        ("Denmark", "DK", "DK"),
        ("Dinamarca", "DK", "DK"),
        ("Argentina", "AR", "AR"),
        ("Peru", "PE", "PE"),
        ("Perú", "PE", "PE"),
    ],
)
def test_standard_and_localized_country_names(name, provider_code, expected):
    assert country_code(name, provider_code) == expected


@pytest.mark.parametrize(
    ("name", "provider_code", "expected"),
    [
        ("Congo-DR", "CG", "CD"),
        ("Congo", "CD", "CG"),
        ("Crimea", "UA", ""),
    ],
)
def test_provider_name_overrides_observed_bad_codes(
    name,
    provider_code,
    expected,
):
    assert country_code(name, provider_code) == expected


@pytest.mark.parametrize(
    ("name", "expected"),
    [
        ("England", "EN"),
        ("Scotland", "CT"),
        ("Wales", "WA"),
        ("Northern Ireland", "ND"),
    ],
)
def test_domestic_football_country_codes_are_preserved(name, expected):
    assert country_code(name, "GB") == expected


@pytest.mark.parametrize(
    ("code", "expected_prefixes"),
    [
        ("DE", {"germany", "alemania"}),
        ("ES", {"spain", "espana"}),
        ("BR", {"brazil", "brasil"}),
        ("DK", {"denmark", "dinamarca"}),
    ],
)
def test_country_prefixes_cover_provider_localized_names(
    code,
    expected_prefixes,
):
    assert expected_prefixes <= set(country_name_prefixes(Country(code)))


def test_provider_specific_country_prefix_is_preserved():
    assert "congo dr" in set(country_name_prefixes(Country("CD")))


def test_valid_provider_code_is_the_final_fallback():
    assert country_code("Provider-only label", "NZ") == "NZ"
    assert country_code("Provider-only label", "not-iso") == ""
