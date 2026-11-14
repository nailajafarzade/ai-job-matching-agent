"""Parse explicit job location restrictions without guessing regions."""
import re


_WORLDWIDE = {"worldwide", "anywhere", "global", "international", "any country", "all countries"}
_USA = {"usa", "us", "u.s.", "united states", "united states of america", "america"}
_COUNTRIES = {
    "Albania", "Argentina", "Armenia", "Australia", "Austria", "Azerbaijan", "Bangladesh",
    "Belgium", "Bolivia", "Bosnia and Herzegovina", "Brazil", "Bulgaria", "Cambodia", "Cameroon",
    "Canada", "Chile", "China", "Colombia", "Costa Rica", "Croatia", "Cyprus", "Czechia",
    "Czech Republic", "Denmark", "Dominican Republic", "Ecuador", "Egypt", "Estonia", "Ethiopia",
    "Finland", "France", "Georgia", "Germany", "Ghana", "Greece", "Hungary", "Iceland", "India",
    "Indonesia", "Ireland", "Israel", "Italy", "Japan", "Jordan", "Kazakhstan", "Kenya", "Latvia",
    "Lebanon", "Lithuania", "Luxembourg", "Malaysia", "Malta", "Mexico", "Moldova", "Montenegro",
    "Morocco", "Nepal", "Netherlands", "New Zealand", "Nigeria", "North Macedonia", "Norway", "Pakistan",
    "Panama", "Peru", "Philippines", "Poland", "Portugal", "Romania", "Saudi Arabia", "Serbia",
    "Singapore", "Slovakia", "Slovenia", "South Africa", "South Korea", "Spain", "Sri Lanka", "Sweden",
    "Switzerland", "Taiwan", "Thailand", "Tunisia", "Turkey", "Türkiye", "Ukraine", "United Arab Emirates",
    "United Kingdom", "Uruguay", "Vietnam", "Zimbabwe",
}
_COUNTRY_LOOKUP = {country.lower(): country for country in _COUNTRIES}
_COUNTRY_LOOKUP.update({"uk": "United Kingdom", "uae": "United Arab Emirates", "czech republic": "Czechia"})
_COUNTRY_LOOKUP.update({alias: "USA" for alias in _USA})


def parse_location(text: str | None) -> tuple[list[str], bool]:
    """Return explicit eligible countries, or an empty uncertain result."""
    if not text or re.search(r"\b(?:UTC|GMT)\s*[+-]?\d", text, re.IGNORECASE):
        return [], False

    value = re.sub(r"\s+", " ", text.strip()).rstrip(".! ").lower()
    value = re.sub(r"\s+only$", "", value)
    if value in _WORLDWIDE:
        return ["Worldwide"], True
    if value in _USA:
        return ["USA"], True

    parts = re.split(r"\s*(?:,|/|\band\b)\s*", value)
    countries = []
    for part in parts:
        part = part.strip().removesuffix(" only").strip()
        country = _COUNTRY_LOOKUP.get(part)
        if country is None:
            return [], False
        if country not in countries:
            countries.append(country)
    return (countries, True) if countries else ([], False)
