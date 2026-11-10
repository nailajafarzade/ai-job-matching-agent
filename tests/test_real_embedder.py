"""Smoke test with the real model. Skipped when the model cannot be loaded
(no internet, first download not done). Run it on your own computer."""
import pytest

pytestmark = pytest.mark.real_model


@pytest.fixture(scope="module")
def real_embedder():
    try:
        from app.matching.embeddings import SentenceTransformerEmbedder

        return SentenceTransformerEmbedder()
    except Exception as error:  # no model, no network, missing package
        pytest.skip(f"real embedding model not available: {type(error).__name__}")


def test_related_titles_are_closer_than_unrelated(real_embedder):
    vectors = real_embedder.embed(["Java Backend Developer", "Spring Boot Java Engineer", "Sales Manager"])
    assert vectors.shape == (3, 384)
    related = float(vectors[0] @ vectors[1])
    unrelated = float(vectors[0] @ vectors[2])
    assert related > unrelated


def test_vectors_are_normalized(real_embedder):
    vector = real_embedder.embed(["any text"])[0]
    assert float(vector @ vector) == pytest.approx(1.0, abs=1e-4)
