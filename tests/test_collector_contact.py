import pytest

from app.collectors.contact import find_apply_email


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("To apply, email your CV to jobs@example.com.", "jobs@example.com"),
        ("Please send your resume.\nContact: hiring@example.com", "hiring@example.com"),
        ("Send your CV to APPLY@example.com", "APPLY@example.com"),
    ],
)
def test_find_apply_email_requires_nearby_application_wording(text, expected):
    assert find_apply_email(text) == expected


@pytest.mark.parametrize(
    "email",
    ["support@example.com", "info@example.com", "noreply@example.com", "no-reply@example.com"],
)
def test_find_apply_email_ignores_service_addresses(email):
    assert find_apply_email(f"Apply by emailing {email}") is None


def test_find_apply_email_ignores_about_and_press_contact_lines():
    text = "About us: email info@example.com\nContact for press: press@example.com\nApply today"
    assert find_apply_email(text) is None


def test_find_apply_email_returns_none_for_ambiguous_candidates():
    text = "Apply by emailing jobs@example.com or hiring@example.com"
    assert find_apply_email(text) is None


def test_find_apply_email_requires_apply_wording():
    assert find_apply_email("Questions? Contact jobs@example.com") is None
