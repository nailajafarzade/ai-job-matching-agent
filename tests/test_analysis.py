import pytest

from app.analysis.analyzer import JobAnalyzer, get_analyzer
from app.analysis.experience import extract_min_years
from app.analysis.sections import Segment, split_into_segments
from app.analysis.seniority import detect_seniority
from app.analysis.vocabulary import get_vocabulary
from app.schemas.enums import Seniority


@pytest.fixture(scope="module")
def vocab():
    return get_vocabulary()


# ---------- skill finder ----------

def test_synonyms_map_to_canonical(vocab):
    found = vocab.find("We use springboot, Postgres, k8s and amazon web services.")
    assert found == ["Spring Boot", "PostgreSQL", "Kubernetes", "AWS"]


def test_spring_alone_is_spring_framework_not_spring_boot(vocab):
    assert vocab.find("Experience with Spring is required.") == ["Spring Framework"]
    assert vocab.find("Experience with Spring Boot is required.") == ["Spring Boot"]


def test_java_is_not_found_inside_javascript(vocab):
    assert vocab.find("Strong JavaScript skills") == ["JavaScript"]
    assert vocab.find("Java and JavaScript") == ["Java", "JavaScript"]


def test_longest_name_wins_docker_compose(vocab):
    assert vocab.find("We use Docker Compose.") == ["Docker Compose"]


def test_related_terms_are_not_synonyms(vocab):
    assert vocab.find("We use Jenkins pipelines") == ["Jenkins"]          # not CI/CD
    assert vocab.find("Write a Dockerfile") == ["Dockerfile"]             # not Docker
    assert vocab.find("Strong Bash scripting") == ["Bash"]                # not Linux
    assert vocab.find("Hexagonal architecture") == ["Hexagonal Architecture"]  # not Clean Architecture


def test_case_sensitive_ambiguous_words(vocab):
    assert vocab.find("Build REST services") == ["REST API"]
    assert vocab.find("Help the rest of the team") == []
    assert vocab.find("You will react quickly to incidents") == []
    assert vocab.find("Frontend in React and TypeScript") == ["React", "TypeScript"]


def test_spring_season_is_not_a_skill(vocab):
    assert vocab.find("Spring 2026 internship program") == []


def test_special_characters(vocab):
    assert vocab.find("CI/CD with Node.js and scikit-learn") == ["CI/CD", "Node.js", "scikit-learn"]


def test_no_duplicates_and_keeps_order(vocab):
    assert vocab.find("Python, Java, python again, JAVA") == ["Python", "Java"]


# ---------- sections ----------

def test_headings_set_the_kind():
    text = "Requirements:\n- Java\n\nNice to have:\n- Docker\n\nAbout us\nWe love Python."
    kinds = [(s.text, s.kind) for s in split_into_segments(text)]
    assert kinds == [("Java", "required"), ("Docker", "nice"), ("We love Python.", "ignore")]


def test_heading_with_text_on_same_line():
    segments = split_into_segments("Nice to have: Docker, Kafka")
    assert [(s.text, s.kind) for s in segments] == [("Docker, Kafka", "nice")]


def test_inline_nice_marker_only_changes_that_sentence():
    segments = split_into_segments("Java is required. Docker is a plus. Spring Boot is needed.")
    assert [s.kind for s in segments] == ["required", "nice", "required"]


def test_sentence_starting_with_you_have_is_not_a_heading():
    segments = split_into_segments("You have 2 years of experience with Java.")
    assert segments == [Segment("You have 2 years of experience with Java.", "required")]


# ---------- years ----------

def years(text: str):
    return extract_min_years(split_into_segments(text))


def test_years_forms():
    assert years("2+ years of experience with Java") == 2
    assert years("1-2 years of experience") == 1          # lower bound
    assert years("At least three years of experience") == 3
    assert years("3 to 5 yrs experience in backend") == 3


def test_years_takes_the_biggest_requirement():
    assert years("5+ years of experience with Java.\n2 years of experience with Docker.") == 5


def test_years_ignores_nice_to_have_and_non_experience():
    assert years("Nice to have:\n- 5+ years of experience with AWS") is None
    assert years("We were founded 10 years ago and hire people.") is None
    assert years("Looking for experience, candidates must be 18 years old.") is None
    assert years("Less than 1 year of experience is fine.") is None


def test_no_experience_required_is_zero():
    assert years("No prior experience required.") == 0
    assert years("No experience required, but 2 years of experience is preferred.") == 0


def test_no_years_stated():
    assert years("We need a good Java developer.") is None


# ---------- seniority ----------

@pytest.mark.parametrize(
    "title, expected",
    [
        ("Senior Java Developer", Seniority.senior),
        ("Sr. Backend Engineer", Seniority.senior),
        ("Junior Python Developer", Seniority.junior),
        ("Software Engineering Intern", Seniority.intern),
        ("Tech Lead", Seniority.lead),
        ("Staff Engineer", Seniority.staff),
        ("Principal Engineer", Seniority.principal),
        ("Engineering Manager", Seniority.manager),
        ("Mid-level Java Developer", Seniority.mid),
        ("Backend Developer", Seniority.unknown),
        ("Internal Tools Developer", Seniority.unknown),  # "Internal" is not "Intern"
    ],
)
def test_seniority_from_title(title, expected):
    assert detect_seniority(title) == expected


def test_seniority_from_description_is_careful():
    assert detect_seniority("Java Developer", "This is an entry-level position.") == Seniority.junior
    assert detect_seniority("Java Developer", "You will mentor junior developers.") == Seniority.unknown
    assert detect_seniority("Java Developer", "We are looking for a senior engineer.") == Seniority.senior


# ---------- whole analyzer ----------

JOB = """Junior Java Backend Developer

About us:
We are a fintech startup in Baku. We love Python internally.

Requirements:
- 1-2 years of experience with Java and Spring Boot
- Knowledge of PostgreSQL and REST APIs
- Basic understanding of Docker

Nice to have:
- Kafka
- Kubernetes
- Experience with AWS (5+ years)

What we offer:
- Free lunch. Python workshops.
"""


def test_full_job_analysis():
    result = get_analyzer().analyze("Junior Java Backend Developer", JOB)
    assert result.required_skills == ["Java", "Spring Boot", "PostgreSQL", "REST API", "Docker"]
    assert result.nice_to_have_skills == ["Kafka", "Kubernetes", "AWS"]
    assert "Python" not in result.required_skills + result.nice_to_have_skills  # only in "About us"
    assert result.min_years == 1
    assert result.seniority == Seniority.junior


def test_required_wins_over_nice():
    text = "Requirements:\n- Docker\n\nNice to have:\n- Docker\n- Kafka"
    result = get_analyzer().analyze("Developer", text)
    assert result.required_skills == ["Docker"]
    assert result.nice_to_have_skills == ["Kafka"]


def test_title_skills_are_required():
    result = get_analyzer().analyze("Python Developer", "Nice to have: Docker")
    assert result.required_skills == ["Python"]
    assert result.nice_to_have_skills == ["Docker"]


def test_analyzer_uses_given_vocabulary(vocab):
    assert JobAnalyzer(vocab).analyze("Java Developer", "Spring Boot").required_skills == ["Java", "Spring Boot"]
