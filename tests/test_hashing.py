from app.intake.hashing import compute_content_hash


def test_same_job_same_hash_even_with_case_and_spaces():
    a = compute_content_hash("Acme", "Java Developer", "We need   Java and Spring Boot.")
    b = compute_content_hash("  acme ", "java developer", "we need java and\nspring boot.")
    assert a == b


def test_different_company_different_hash():
    a = compute_content_hash("Acme", "Java Developer", "Same text")
    b = compute_content_hash("Other", "Java Developer", "Same text")
    assert a != b


def test_hash_is_64_hex_chars():
    h = compute_content_hash("a", "b", "c")
    assert len(h) == 64 and int(h, 16) >= 0
