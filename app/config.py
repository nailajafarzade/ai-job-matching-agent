"""Central settings. All numbers that change the decision live here."""
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = BASE_DIR / "data"
CV_REGISTRY_PATH = DATA_DIR / "cvs.yaml"
TEMPLATES_DIR = BASE_DIR / "templates"

PROFILE_PATH = DATA_DIR / "profile.yaml"
SKILLS_PATH = DATA_DIR / "skills.yaml"
DATABASE_URL = f"sqlite:///{BASE_DIR / 'job_agent.db'}"

# Embedding model (kept behind an interface, so we can swap it later).
# The model is loaded ONCE when the app starts, not on every request.
EMBEDDING_MODEL = "all-MiniLM-L6-v2"
# For Azerbaijani or Russian job texts use:
# EMBEDDING_MODEL = "paraphrase-multilingual-MiniLM-L12-v2"

# Saved with every match, so old results can be recalculated later.
MATCHER_VERSION = "0.1"
ANALYZER_VERSION = "0.1"

# Final score = weighted sum of the three parts (weights must sum to 1.0).
WEIGHTS = {
    "skill": 0.45,
    "semantic": 0.35,
    "title": 0.20,
}
assert abs(sum(WEIGHTS.values()) - 1.0) < 1e-9, "WEIGHTS must sum to 1.0"

# Required skills count more than "nice to have" skills.
REQUIRED_SKILL_FACTOR = 1.0
NICE_TO_HAVE_SKILL_FACTOR = 0.4

# A skill I only studied (level "studied") gives part of the credit.
STUDIED_SKILL_CREDIT = 0.5

# Cosine similarity is turned into a 0-100 score with a straight line:
# <= FLOOR gives 0, >= CEIL gives 100. These numbers are a first guess.
# They must be tuned later with real jobs that I label myself.
SEMANTIC_FLOOR = 0.15
SEMANTIC_CEIL = 0.60
TITLE_FLOOR = 0.30
TITLE_CEIL = 0.90

# Target role priority lowers the title score for less wanted roles.
ROLE_PRIORITY_FACTOR = {"high": 1.0, "medium": 0.85, "secondary": 0.70}

# The embedding model reads only the first ~256 word pieces, so the job text
# is cut here (about 1200 characters).
MAX_JOB_TEXT_CHARS = 1200

# Jobs with a final score below this are not queued.
MIN_SCORE_TO_QUEUE = 60

# Public collector requests are intentionally limited to avoid overloading sources.
MAX_RUNS_PER_DAY = 4
MIN_SECONDS_BETWEEN_RUNS = 60

MAX_LETTER_WORDS = 200
CV_TITLE_BONUS = 1.0
