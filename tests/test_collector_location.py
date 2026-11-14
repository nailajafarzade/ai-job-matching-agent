import pytest

from app.collectors.location import parse_location


@pytest.mark.parametrize(
    ("text", "countries", "certain"),
    [
        ("Worldwide", ["Worldwide"], True),
        ("Anywhere", ["Worldwide"], True),
        ("Global", ["Worldwide"], True),
        ("USA Only", ["USA"], True),
        ("US only", ["USA"], True),
        ("United States", ["USA"], True),
        ("Germany, Poland / Spain", ["Germany", "Poland", "Spain"], True),
        ("Canada and United Kingdom", ["Canada", "United Kingdom"], True),
        ("Europe", [], False),
        ("EMEA", [], False),
        ("Americas", [], False),
        ("UTC-5 to UTC+1", [], False),
        ("", [], False),
    ],
)
def test_parse_location(text, countries, certain):
    assert parse_location(text) == (countries, certain)
